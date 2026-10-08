"""RAG retrieval: lexical BM25 over active knowledge chunks.

There is no vector stack: library documents are short, Vietnamese questions overlap their
wording heavily, and BM25 runs on any database. Text is tokenized into lower-cased syllables,
syllable bigrams (Vietnamese words are mostly two syllables) and accent-stripped syllables
so questions typed without diacritics still match. The in-memory index is rebuilt only when
the set of active chunks changes.
"""
from __future__ import annotations

import math
import re
import threading
import unicodedata
from collections import Counter
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.schema import KnowledgeChunk, KnowledgeDocument

STOPWORDS = frozenset("""
là của và có không cho tôi bạn mình thì như thế nào gì được những các một để trong với ở tại về
mấy à nhé ơi hãy giúp xin chào vậy ạ em anh chị muốn hỏi biết cần làm sao đâu nhỉ hả này kia đó
ai bao nhiêu khi nếu thì rồi đã đang sẽ cũng rất nhiều ít hơn nhất bị bởi vì nên mà hay hoặc
""".split())
# Weights of the three token kinds in a query.
UNIGRAM_WEIGHT, BIGRAM_WEIGHT, STRIPPED_WEIGHT = 1.0, 1.5, 0.4
K1, B = 1.5, 0.75
MIN_COVERAGE = 0.4          # share of the question's content-word IDF that must appear in a chunk
RELATIVE_SCORE_CUTOFF = 0.4  # drop chunks scoring below this share of the best chunk


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: UUID
    document_id: UUID
    title: str
    text: str
    page_number: int | None
    sheet_name: str | None
    score: float

    def citation(self, index: int) -> dict:
        return {"index": index, "chunk_id": str(self.chunk_id), "document_id": str(self.document_id),
                "title": self.title, "page_number": self.page_number, "sheet_name": self.sheet_name}


def strip_accents(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    return "".join(ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn")


_WORD = re.compile(r"\w+", re.UNICODE)


def syllables(text: str) -> list[str]:
    return _WORD.findall(unicodedata.normalize("NFC", text).casefold())


def tokens(text: str) -> list[tuple[str, float]]:
    """(token, weight) pairs. Stopwords never stand alone but still link bigrams."""
    words = syllables(text)
    result: list[tuple[str, float]] = []
    for word in words:
        if word in STOPWORDS:
            continue
        result.append((word, UNIGRAM_WEIGHT))
        stripped = strip_accents(word)
        if stripped != word:
            result.append(("~" + stripped, STRIPPED_WEIGHT))
    for first, second in zip(words, words[1:]):
        if first in STOPWORDS and second in STOPWORDS:
            continue
        result.append((f"{first}_{second}", BIGRAM_WEIGHT))
    return result


def _query_terms(question: str) -> dict[str, float]:
    terms: dict[str, float] = {}
    for token, weight in tokens(question):
        terms[token] = max(terms.get(token, 0.0), weight)
    # A question typed without diacritics matches the accent-stripped form of the documents.
    for word in syllables(question):
        if word not in STOPWORDS and strip_accents(word) == word:
            terms.setdefault("~" + word, STRIPPED_WEIGHT)
    return terms


@dataclass
class _Entry:
    chunk: RetrievedChunk
    counts: Counter
    length: int


class _Index:
    def __init__(self, entries: list[_Entry]):
        self.entries = entries
        self.avg_length = sum(entry.length for entry in entries) / len(entries) if entries else 1.0
        document_frequency: Counter = Counter()
        for entry in entries:
            document_frequency.update(entry.counts.keys())
        n = len(entries)
        self.idf = {term: math.log(1 + (n - df + 0.5) / (df + 0.5)) for term, df in document_frequency.items()}
        self.missing_idf = math.log(1 + (n + 0.5) / 0.5)

    def search(self, question: str, top_k: int) -> list[RetrievedChunk]:
        terms = _query_terms(question)
        content = {term for term in terms if "_" not in term and not term.startswith("~")}
        if not content and terms:
            content = {term for term in terms if term.startswith("~")}
        if not self.entries or not content:
            return []
        content_idf = sum(self.idf.get(term, self.missing_idf) for term in content)
        scored = []
        for entry in self.entries:
            score = 0.0
            for term, weight in terms.items():
                tf = entry.counts.get(term)
                if tf:
                    norm = K1 * (1 - B + B * entry.length / self.avg_length)
                    score += weight * self.idf[term] * tf * (K1 + 1) / (tf + norm)
            if score <= 0:
                continue
            covered = sum(self.idf.get(term, self.missing_idf) for term in content
                          if entry.counts.get(term) or entry.counts.get("~" + strip_accents(term)))
            if covered / content_idf >= MIN_COVERAGE:
                scored.append((score, entry.chunk))
        scored.sort(key=lambda item: item[0], reverse=True)
        if not scored:
            return []
        best = scored[0][0]
        return [RetrievedChunk(**{**chunk.__dict__, "score": round(score, 4)})
                for score, chunk in scored[:top_k] if score >= best * RELATIVE_SCORE_CUTOFF]


_lock = threading.Lock()
_cached: tuple[tuple, _Index] | None = None


def _active_filter():
    return (KnowledgeDocument.is_active.is_(True), KnowledgeDocument.deleted_at.is_(None),
            KnowledgeDocument.processing_status == "processed")


def _fingerprint(db: Session) -> tuple:
    row = db.execute(select(func.count(KnowledgeChunk.id), func.max(KnowledgeChunk.created_at),
                            func.max(KnowledgeDocument.updated_at), func.count(func.distinct(KnowledgeDocument.id)))
                     .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
                     .where(*_active_filter())).one()
    return tuple(row)


def _build(db: Session) -> _Index:
    rows = db.execute(select(KnowledgeChunk.id, KnowledgeChunk.document_id, KnowledgeDocument.title,
                             KnowledgeChunk.chunk_text, KnowledgeChunk.page_number, KnowledgeChunk.sheet_name)
                      .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
                      .where(*_active_filter())).all()
    entries = []
    for chunk_id, document_id, title, text, page, sheet in rows:
        # The title is indexed with the body so "nội quy" finds the "Nội quy thư viện" document.
        counts = Counter(token for token, _ in tokens(f"{title}\n{text}"))
        entries.append(_Entry(RetrievedChunk(chunk_id, document_id, title, text, page, sheet, 0.0),
                              counts, sum(counts.values()) or 1))
    return _Index(entries)


def retrieve(db: Session, question: str, top_k: int | None = None) -> list[RetrievedChunk]:
    global _cached
    top_k = top_k or settings.rag_top_k
    fingerprint = _fingerprint(db)
    with _lock:
        if _cached is None or _cached[0] != fingerprint:
            _cached = (fingerprint, _build(db))
        index = _cached[1]
    return index.search(question, top_k)
