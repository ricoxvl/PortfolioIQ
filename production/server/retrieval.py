"""Bounded SEC filing retrieval with local BM25 and explicit opt-in embedding rerank.

This module never fetches the web, stores embeddings, or treats retrieved source text
as instructions. Embeddings are an optional, billable external API request. They
rerank an identified *candidate subset*, not a complete long-filing vector index.
"""
from __future__ import annotations

from collections import Counter
from math import isfinite, log, sqrt
import os
import re

STOP = frozenset({"and", "the", "for", "are", "was", "that", "with", "from",
                  "this", "about", "what", "show", "report", "filing", "company",
                  "have", "your", "does", "how", "its", "their", "can", "which",
                  "tell", "give", "please", "most", "some", "more", "item"})
TOKEN = re.compile(r"[a-z]{3,}")
SECTION = re.compile(r"^\s*(?:item\s+\d{1,2}[a-z]?\s*[.:\-—]\s*|part\s+[ivx]+\s*$)", re.I)
MAX_CHUNKS = 10000
MAX_EMBED_CANDIDATES = 48


def tokens(text: str) -> list[str]:
    return [word for word in TOKEN.findall(text.casefold()) if word not in STOP]


def chunk_text(text: str) -> list[dict]:
    """Bounded, partly overlapping text windows with filing section labels."""
    chunks = []
    section = "Filing body"
    for block in re.split(r"\n", text):
        block = block.strip()
        if not block:
            continue
        if len(block) < 160 and SECTION.match(block):
            section = block[:140]
        if len(block) < 45:
            continue
        for start in range(0, min(len(block), 180000), 640):
            passage = block[start:start + 850].strip()
            if len(passage) >= 55:
                chunks.append({"excerpt": passage, "section": section, "chunk_id": len(chunks)})
                if len(chunks) >= MAX_CHUNKS:
                    return chunks
            if start + 850 >= len(block):
                break
    return chunks


def lexical_rank(chunks: list[dict], question: str) -> list[dict]:
    """Finite deterministic BM25 on source text; zero-hit answers are unavailable."""
    query = list(dict.fromkeys(tokens(question)))
    if not query:
        raise ValueError("Use a specific research question, e.g. 'revenue growth' or 'risk factors'")
    if not chunks:
        return []
    corpus = [Counter(tokens(x["excerpt"])) for x in chunks]
    avg = max(1.0, sum(sum(c.values()) for c in corpus) / len(corpus))
    df = Counter()
    for c in corpus:
        for word in query:
            if c[word]:
                df[word] += 1
    scores = []
    for row, bag in zip(chunks, corpus):
        length = sum(bag.values())
        score = 0.0
        for term in query:
            freq = bag[term]
            if not freq:
                continue
            idf = log(1 + (len(chunks) - df[term] + .5) / (df[term] + .5))
            score += idf * freq * 2.2 / (freq + 1.2 * (.25 + .75 * length / avg))
        if score > 0:
            scores.append({**row, "lexical_score": round(score, 6)})
    return sorted(scores, key=lambda r: (-r["lexical_score"], r["chunk_id"]))


def embedding_enabled() -> bool:
    return (os.getenv("SEC_EMBEDDINGS_ENABLED", "").lower() == "true"
            and os.getenv("SEC_RESEARCH_ENABLED", "").lower() == "true"
            and os.getenv("BETA_DEMO_ONLY", "false").lower() != "true"
            and bool(os.getenv("OPENAI_API_KEY")))


def _cosine(v: list[float], w: list[float]) -> float:
    if len(v) != len(w) or not v or len(v) > 8192:
        raise ValueError("Embedding response has invalid dimensions")
    if not all(isfinite(float(x)) for x in v + w):
        raise ValueError("Embedding response contains non-finite values")
    dot = sum(a * b for a, b in zip(v, w))
    na = sqrt(sum(a * a for a in v))
    nb = sqrt(sum(b * b for b in w))
    if na <= 0 or nb <= 0:
        raise ValueError("Embedding response contains a zero vector")
    return dot / (na * nb)


def rank_passages(text: str, question: str, *, use_embeddings: bool = False,
                  embedding_client=None) -> dict:
    chunks = chunk_text(text)
    lexical = lexical_rank(chunks, question)
    if not use_embeddings:
        ranked = lexical
        method = "local_bm25"
    else:
        if not embedding_enabled():
            raise ValueError("External semantic reranking is disabled; no text was sent")
        # A bounded prefilter: retrieve high-lexical-score passages and
        # stratified candidates to avoid silently examining only the front.
        selected = list(lexical[:32])
        included = {row["chunk_id"] for row in selected}
        if chunks:
            stride = max(1, len(chunks) // 16)
            for chunk in chunks[::stride]:
                if chunk["chunk_id"] not in included:
                    selected.append(chunk)
                    included.add(chunk["chunk_id"])
                if len(selected) >= MAX_EMBED_CANDIDATES:
                    break
        selected = selected[:MAX_EMBED_CANDIDATES]
        if not selected:
            return {"passages": [], "method": "semantic_candidate_rerank",
                    "indexed_chunks": len(chunks), "semantic_candidates": 0}
        client = embedding_client
        if client is None:
            from openai import OpenAI
            client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=20.0, max_retries=0)
        model = "text-embedding-3-small"
        try:
            answer = client.embeddings.create(model=model,
                input=[question] + [row["excerpt"][:850] for row in selected])
            # SDK responses include an index for each embedded input. Reject
            # mismatched or duplicate indexes rather than attaching a vector
            # to the wrong filing excerpt.
            records = [(getattr(item, "index", i), item.embedding)
                       for i, item in enumerate(answer.data)]
        except Exception as exc:
            raise ValueError("External embedding provider unavailable; no semantic ranking produced") from exc
        if (len(records) != len(selected) + 1
                or sorted(i for i, _ in records) != list(range(len(records)))):
            raise ValueError("Embedding provider returned incomplete or misindexed vectors")
        vectors = [vector for _, vector in sorted(records, key=lambda item: item[0])]
        scored = []
        for row, vector in zip(selected, vectors[1:]):
            score = _cosine(vectors[0], vector)
            scored.append({**row, "semantic_score": round(score, 6)})
        ranked = sorted(scored, key=lambda r: (-r["semantic_score"], r["chunk_id"]))
        method = "semantic_candidate_rerank"
    # Don't show overlapping windows from the same paragraph as independent evidence.
    used = set()
    passages = []
    for row in ranked:
        i = row["chunk_id"]
        if any(abs(i - old) <= 1 for old in used):
            continue
        used.add(i)
        passages.append({
            "excerpt": row["excerpt"][:850], "section": row["section"],
            "chunk_id": row["chunk_id"], "rank": len(passages) + 1,
            "retrieval_method": method,
        })
        if len(passages) == 3:
            break
    return {"passages": passages, "method": method,
            "indexed_chunks": len(chunks),
            "semantic_candidates": min(MAX_EMBED_CANDIDATES, len(selected)) if use_embeddings else 0}
