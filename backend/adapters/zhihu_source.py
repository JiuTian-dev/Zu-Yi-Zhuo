"""Stdin/stdout wrapper between the Conversation Orchestrator backend and the
Zhihu open-platform content search API (developer.zhihu.com).

The backend spawns this script without a shell (CANDIDATE_SOURCE_COMMAND /
CONTENT_SIGNAL_SOURCE_COMMAND / PERSONAL_CONTEXT_SOURCE_COMMAND) and speaks
the bounded JSON contract from backend/README.md:

    stdin:  {"query": str, "limit": int}
            (personal mode adds "viewer_id" and "scopes")
    stdout: {"candidates": [...]} for the candidate source
            {"signals": [...]}    for the public content / personal source

Modes:
- signals / candidates: public content search, mapped onto ContentSignal /
  ParticipantSeed.
- personal: favorites / followees / own contents of the ONE Zhihu account
  linked via ZHIHU_PERSONAL_VIEWER_ID (participant_id of the account owner).
  Requests from any other viewer return zero signals — the credential is
  account-scoped and must never impersonate someone else's private data.
  Genuine multi-user authorization needs the Zhihu OAuth flow.

Pipes are UTF-8 on both sides (backend writes ensure_ascii=False UTF-8 bytes),
so this script reads/writes sys.stdin.buffer / sys.stdout.buffer directly and
never depends on the Windows console locale.

Zhihu credentials never appear here: the wrapper reads ZHIHU_ACCESS_SECRET
from its environment, and the backend never sees it.

Fail-closed notes:
- Any non-zero Zhihu Code, transport error, timeout or malformed item exits
  non-zero with details on stderr only; the backend turns that into 502.
- Items are skipped (not emitted) when they miss title/excerpt/url/author or
  have an unmappable ContentType, so one bad record cannot poison the batch.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from typing import Any

import httpx

API_URL = "https://developer.zhihu.com/api/v1"
HTTP_TIMEOUT_SECONDS = 3.5
TITLE_SUFFIX = " - 知乎"
# Participant id of the Zhihu account owner. The open-platform credential is
# account-scoped: user/* endpoints return the owner account's own favorites,
# followees and contents, so the personal mode serves exactly this one viewer
# and returns an empty signal list for everyone else (never someone else's
# data). True per-user authorization needs the OAuth flow.
PERSONAL_VIEWER_ENV = "ZHIHU_PERSONAL_VIEWER_ID"


def _clean(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _stable_id(*parts: str) -> str:
    digest = hashlib.md5("\x1f".join(parts).encode("utf-8")).hexdigest()
    return f"zhihu-{digest[:12]}"


def _api_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    secret = (os.environ.get("ZHIHU_ACCESS_SECRET") or "").strip()
    if not secret:
        raise RuntimeError("ZHIHU_ACCESS_SECRET is not configured")
    response = httpx.get(
        f"{API_URL}{path}",
        params=params,
        headers={
            "Authorization": f"Bearer {secret}",
            "X-Request-Timestamp": str(int(time.time())),
        },
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    code = payload.get("Code")
    if code != 0:
        raise RuntimeError(f"zhihu api code {code}: {payload.get('Message')}")
    return payload


def fetch_items(query: str, limit: int) -> list[dict[str, Any]]:
    bounded_limit = max(1, min(limit, 20))
    payload = _api_get(
        "/content/zhihu_search",
        {"Query": query, "Limit": bounded_limit},
    )
    items = ((payload.get("Data") or {}).get("Items")) or []
    return items[:bounded_limit]


def _common_fields(item: dict[str, Any]) -> dict[str, str] | None:
    """Fields shared by both output shapes; None when the item is unusable."""
    title = _clean(item.get("Title"), 240).removesuffix(TITLE_SUFFIX)
    excerpt = _clean(item.get("ContentText"), 1000)
    url = str(item.get("Url") or "").strip()
    author_name = _clean(item.get("AuthorName"), 120)
    content_id = str(item.get("ContentID") or "").strip()
    if not (title and excerpt and url and author_name and content_id):
        return None
    return {
        "title": title,
        "excerpt": excerpt,
        "url": url,
        "author_name": author_name,
        "content_id": content_id,
        "author_id": str(item.get("AuthorSignature") or "").strip()
        or _stable_id("author", author_name),
        "badge": _clean(item.get("AuthorBadgeText"), 80),
    }


def to_signal(item: dict[str, Any]) -> dict[str, Any] | None:
    common = _common_fields(item)
    if common is None:
        return None
    content_type = _clean(item.get("ContentType"), 20).lower()
    if content_type not in ("question", "answer", "article"):
        return None
    engagement = 0
    for key in ("VoteUpCount", "CommentCount"):
        try:
            engagement += max(0, int(item.get(key) or 0))
        except (TypeError, ValueError):
            pass
    return {
        "signal_id": common["content_id"],
        "content_type": content_type,
        "title": common["title"],
        "excerpt": common["excerpt"],
        "source_ref": common["url"],
        "author_id": common["author_id"],
        "author_name": common["author_name"],
        "author_role": common["badge"] or None,
        "public_stance": None,
        "engagement": engagement,
        "visibility": "public",
    }


def to_candidates(items: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Collapse search hits into one candidate seed per public author.

    declared_position is deliberately a neutral, provable statement ("has
    published on this topic"): the search API exposes no bio field, and the
    wrapper must not invent positions or experience.
    """
    seeds: dict[str, dict[str, Any]] = {}
    for item in items:
        common = _common_fields(item)
        if common is None:
            continue
        experience = {"text": common["excerpt"][:200], "source_ref": common["url"]}
        author = common["author_id"]
        seed = seeds.get(author)
        if seed is None:
            seeds[author] = {
                "participant_id": _stable_id("participant", author),
                "display_name": common["author_name"],
                "role": common["badge"] or "知乎作者",
                "declared_position": f"就「{query}」在知乎公开发表过内容",
                "relevant_experience": [experience],
                "roundtable_invite_preference": "few",
            }
        elif len(seed["relevant_experience"]) < 3:
            seed["relevant_experience"].append(experience)
    return list(seeds.values())


def _personal_signal(viewer_id: str, *, signal_id: str, content_type: str,
                     title: str, excerpt: str, source_ref: str) -> dict[str, Any]:
    return {
        "signal_id": signal_id,
        "owner_id": viewer_id,
        "content_type": content_type,
        "title": title,
        "excerpt": excerpt,
        "source_ref": source_ref,
        "private_stance": None,
        "visibility": "private",
    }


def _favorite_signals(items: list[dict[str, Any]], viewer_id: str) -> list[dict[str, Any]]:
    out = []
    for item in items:
        content_type = _clean(item.get("ContentType"), 20).lower()
        title = _clean(item.get("Title"), 240)
        excerpt = _clean(item.get("Summary"), 1000)
        url = str(item.get("Url") or "").strip()
        if content_type not in ("question", "answer", "article"):
            continue
        if not (title and excerpt and url):
            continue
        out.append(_personal_signal(
            viewer_id,
            signal_id="fav-" + hashlib.md5(url.encode("utf-8")).hexdigest()[:16],
            content_type=content_type,
            title=title,
            excerpt=excerpt,
            source_ref=url,
        ))
    return out


def _follow_signals(items: list[dict[str, Any]], viewer_id: str) -> list[dict[str, Any]]:
    out = []
    for item in items:
        title = _clean(item.get("Fullname"), 240)
        excerpt = _clean(item.get("Headline"), 1000)
        url = str(item.get("Url") or "").strip()
        if not (title and excerpt and url):
            continue
        out.append(_personal_signal(
            viewer_id,
            signal_id="follow-" + hashlib.md5(url.encode("utf-8")).hexdigest()[:16],
            content_type="follow",
            title=title,
            excerpt=excerpt,
            source_ref=url,
        ))
    return out


def _own_content_signals(items: list[dict[str, Any]], viewer_id: str) -> list[dict[str, Any]]:
    # Defensive mapping: the response schema is unverified (the linked demo
    # account has no own contents), unknown-shaped items are skipped.
    out = []
    for item in items:
        content_type = _clean(item.get("ContentType"), 20).lower()
        title = _clean(item.get("Title"), 240)
        excerpt = _clean(item.get("Summary") or item.get("Content") or item.get("Excerpt"), 1000)
        url = str(item.get("Url") or "").strip()
        if content_type not in ("question", "answer", "article"):
            continue
        if not (title and excerpt and url):
            continue
        out.append(_personal_signal(
            viewer_id,
            signal_id="own-" + hashlib.md5(url.encode("utf-8")).hexdigest()[:16],
            content_type=content_type,
            title=title,
            excerpt=excerpt,
            source_ref=url,
        ))
    return out


def _personal_signals(viewer_id: str, scopes: list[str], limit: int) -> list[dict[str, Any]]:
    """Favorites/follows/own contents of the linked Zhihu account owner.

    Another viewer_id (or an unset link) yields zero signals: the credential
    is account-scoped, so there is nothing this viewer has authorized.
    """
    linked = (os.environ.get(PERSONAL_VIEWER_ENV) or "").strip()
    if not linked or viewer_id != linked:
        return []
    per_scope_limit = max(1, min(limit, 20))
    signals: list[dict[str, Any]] = []
    errors: list[str] = []
    for scope in scopes:
        try:
            if scope == "favorites":
                payload = _api_get("/user/collections", {"Limit": per_scope_limit})
                signals.extend(_favorite_signals((payload.get("Data") or {}).get("Items") or [], viewer_id))
            elif scope == "follows":
                payload = _api_get("/user/followees", {"Limit": per_scope_limit})
                signals.extend(_follow_signals((payload.get("Data") or {}).get("Items") or [], viewer_id))
            elif scope == "public_content":
                for content_type in ("article", "answer"):
                    payload = _api_get("/user/contents", {"ContentType": content_type, "Limit": per_scope_limit})
                    signals.extend(_own_content_signals((payload.get("Data") or {}).get("Items") or [], viewer_id))
            else:
                print(f"zhihu_source: scope {scope!r} has no endpoint mapping; skipped", file=sys.stderr)
        except Exception as error:  # per-scope failure; fail closed only if all fail
            errors.append(f"{scope}: {error}")
    if errors and not signals:
        raise RuntimeError("; ".join(errors))
    for message in errors:
        print(f"zhihu_source: partial failure - {message}", file=sys.stderr)
    return signals[: max(1, min(limit, 20))]


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else ""
    if mode not in ("signals", "candidates", "personal"):
        print("usage: zhihu_source.py signals|candidates|personal", file=sys.stderr)
        return 2
    try:
        request = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        limit = int(request.get("limit") or 20)
        if mode == "personal":
            viewer_id = _clean(request.get("viewer_id"), 120)
            scopes = [str(scope) for scope in (request.get("scopes") or [])][:4]
            payload: dict[str, Any] = {"signals": _personal_signals(viewer_id, scopes, limit)}
        else:
            query = _clean(request.get("query"), 200)
            if not query:
                raise RuntimeError("query is required")
            items = fetch_items(query, limit)
            if mode == "signals":
                payload = {"signals": [s for s in map(to_signal, items) if s]}
            else:
                payload = {"candidates": to_candidates(items, query)}
        sys.stdout.buffer.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        return 0
    except Exception as error:  # fail closed: details go to stderr, never stdout
        print(f"zhihu_source: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
