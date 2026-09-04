from __future__ import annotations

import pytest

from adapters import zhihu_source


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


def test_search_uses_official_count_parameter_and_ten_item_cap(monkeypatch) -> None:
    calls = []

    def fake_api_get(path, params):
        calls.append((path, params))
        return {"Data": {"Items": [{"ContentID": str(index)} for index in range(12)]}}

    monkeypatch.setattr(zhihu_source, "_api_get", fake_api_get)

    items = zhihu_source.fetch_items("休息", 20)

    assert len(items) == 10
    assert calls == [("/content/zhihu_search", {"Query": "休息", "Count": 10})]


def test_api_get_keeps_access_secret_in_server_headers(monkeypatch) -> None:
    observed = {}

    def fake_get(url, *, params, headers, timeout):
        observed.update(
            url=url,
            params=params,
            headers=headers,
            timeout=timeout,
        )
        return _Response({"Code": 0, "Message": "success", "Data": {}})

    monkeypatch.setenv("ZHIHU_ACCESS_SECRET", "server-only-secret")
    monkeypatch.setattr(zhihu_source.httpx, "get", fake_get)

    result = zhihu_source._api_get("/quota", {"APIIDs": "zhihu_search"})

    assert result["Code"] == 0
    assert observed["url"] == "https://developer.zhihu.com/api/v1/quota"
    assert observed["headers"]["Authorization"] == "Bearer server-only-secret"
    assert observed["headers"]["X-Request-Timestamp"].isdigit()
    assert "server-only-secret" not in str(observed["params"])


def test_api_get_fails_closed_without_access_secret(monkeypatch) -> None:
    monkeypatch.delenv("ZHIHU_ACCESS_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="ZHIHU_ACCESS_SECRET is not configured"):
        zhihu_source._api_get("/quota", {})


def test_public_content_scope_uses_all_official_content_types_once(monkeypatch) -> None:
    calls = []

    def fake_api_get(path, params):
        calls.append((path, params))
        return {
            "Data": {
                "Items": [
                    {
                        "ContentType": "question",
                        "Title": "怎样休息？",
                        "Summary": "一个公开问题",
                        "Url": "https://www.zhihu.com/question/1",
                    },
                    {
                        "ContentType": "zvideo",
                        "Title": "视频",
                        "Summary": "当前领域模型尚未表示视频",
                        "Url": "https://www.zhihu.com/zvideo/2",
                    },
                ]
            }
        }

    monkeypatch.setenv(zhihu_source.PERSONAL_VIEWER_ENV, "viewer-1")
    monkeypatch.setattr(zhihu_source, "_api_get", fake_api_get)

    signals = zhihu_source._personal_signals(
        "viewer-1", ["public_content"], limit=20
    )

    assert calls == [
        ("/user/contents", {"ContentType": "all", "Limit": 20})
    ]
    assert [signal["content_type"] for signal in signals] == ["question"]


def test_personal_source_never_uses_one_accounts_data_for_another_viewer(
    monkeypatch,
) -> None:
    monkeypatch.setenv(zhihu_source.PERSONAL_VIEWER_ENV, "viewer-1")

    def unexpected_call(*_args, **_kwargs):
        raise AssertionError("Zhihu API must not be called for an unlinked viewer")

    monkeypatch.setattr(zhihu_source, "_api_get", unexpected_call)

    assert zhihu_source._personal_signals(
        "viewer-2", ["favorites", "follows", "public_content"], limit=20
    ) == []
