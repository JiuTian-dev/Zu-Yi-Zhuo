"""Small deterministic theme extraction for viewer-owned context."""

from collections import Counter
import re
from collections.abc import Iterable

from app.domain import PersonalContextPreview, PersonalContextSignal

_CJK = re.compile(r"[\u4e00-\u9fff]+")
_WORD = re.compile(r"[a-z0-9]{2,}")


def _terms(text: str) -> Iterable[str]:
    for word in _WORD.findall(text.lower()):
        yield word
    for chunk in _CJK.findall(text):
        yield from (chunk[index : index + 2] for index in range(len(chunk) - 1))


def build_personal_context_preview(
    viewer_id: str,
    query: str,
    signals: Iterable[PersonalContextSignal],
) -> PersonalContextPreview:
    rows = list(signals)
    query_terms = set(_terms(query))
    counts = Counter(
        term
        for signal in rows
        for term in _terms(" ".join(filter(None, (signal.title, signal.excerpt, signal.private_stance))))
        if term not in query_terms
    )
    themes = [term for term, _count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:5]]
    return PersonalContextPreview(
        viewer_id=viewer_id,
        query=query,
        signals=rows,
        themes=themes,
    )
