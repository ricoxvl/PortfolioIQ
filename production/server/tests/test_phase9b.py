"""Phase 9B retrieval tests use fictional documents and fake embedding responses only."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("DATABASE_URL","sqlite:///"+str(Path(__file__).resolve().parent/"portfolioiq_v9b_test.sqlite3"))

from server import retrieval, filing_research
from server.app import app


SAMPLE = """
Item 1A. Risk Factors
Fictional issuer faces supplier disruption, logistics shortages, inventory risks and product demand uncertainty.
These sample statements are not company observations or real disclosures.

Item 7. Operating Results
Sample fictional revenue expanded after product adoption and higher customer retention.
Sample growth and margins are fabricated for evaluation fixtures only.

Item 8. Funding
Fake issuer funding policy emphasizes debt maturities and cash liquidity constraints.
Fictional liquidity may change under temporary funding disruption.
"""


class FakeEmbedding:
    """Mock scoring response with no network or paid API calls."""
    def __init__(self):
        self.calls=[]
        self.embeddings=SimpleNamespace(create=self.create)

    def create(self, *, model, input):
        self.calls.append({"model":model,"input":input})
        vectors=[]
        for phrase in input:
            t=phrase.lower()
            vectors.append([float("revenue" in t),float("supplier" in t),
                            float("liquidity" in t),.1])
        return SimpleNamespace(data=[SimpleNamespace(embedding=row) for row in vectors])


def test_local_bm25_retrieves_relevant_source_with_section_and_no_external_call(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY",raising=False)
    result=retrieval.rank_passages(SAMPLE,"supplier disruption")
    assert result["method"]=="local_bm25" and result["semantic_candidates"]==0
    assert result["passages"]
    assert "supplier" in result["passages"][0]["excerpt"].lower()
    assert result["passages"][0]["section"].startswith("Item 1A")
    assert result["passages"][0]["chunk_id"] >= 0


def test_no_lexical_match_returns_no_synthetic_claims():
    result=retrieval.rank_passages(SAMPLE,"antarctic meteor collision")
    assert result["passages"] == []
    assert result["method"] == "local_bm25"


def test_semantic_gate_fails_closed_without_auth_and_keeps_text_local(monkeypatch):
    monkeypatch.setenv("SEC_RESEARCH_ENABLED","true")
    monkeypatch.setenv("SEC_EMBEDDINGS_ENABLED","true")
    monkeypatch.setenv("BETA_DEMO_ONLY","true")
    monkeypatch.setenv("OPENAI_API_KEY","NOT_A_REAL_KEY")
    fake=FakeEmbedding()
    with pytest.raises(ValueError,match="disabled"):
        retrieval.rank_passages(SAMPLE,"revenue growth",use_embeddings=True,embedding_client=fake)
    assert fake.calls == []
    monkeypatch.setenv("BETA_DEMO_ONLY","false")
    monkeypatch.delenv("OPENAI_API_KEY")
    with pytest.raises(ValueError,match="disabled"):
        retrieval.rank_passages(SAMPLE,"revenue growth",use_embeddings=True,embedding_client=fake)
    assert fake.calls == []


def test_consented_embedding_reranks_bounded_candidates(monkeypatch):
    monkeypatch.setenv("SEC_RESEARCH_ENABLED","true")
    monkeypatch.setenv("SEC_EMBEDDINGS_ENABLED","true")
    monkeypatch.setenv("BETA_DEMO_ONLY","false")
    monkeypatch.setenv("OPENAI_API_KEY","NOT_A_REAL_KEY")
    fake=FakeEmbedding()
    result=retrieval.rank_passages(SAMPLE,"revenue",use_embeddings=True,embedding_client=fake)
    assert result["method"] == "semantic_candidate_rerank"
    assert 0 < result["semantic_candidates"] <= 48
    assert len(fake.calls) == 1
    assert fake.calls[0]["model"]=="text-embedding-3-small"
    assert len(fake.calls[0]["input"]) <= 49
    assert "revenue" in result["passages"][0]["excerpt"].lower()


def test_provider_failure_never_uses_fake_fallback(monkeypatch):
    monkeypatch.setenv("SEC_RESEARCH_ENABLED","true")
    monkeypatch.setenv("SEC_EMBEDDINGS_ENABLED","true")
    monkeypatch.setenv("BETA_DEMO_ONLY","false")
    monkeypatch.setenv("OPENAI_API_KEY","NOT_A_REAL_KEY")
    class Broken:
        embeddings=SimpleNamespace(create=lambda **kw: (_ for _ in ()).throw(RuntimeError("offline")))
    with pytest.raises(ValueError,match="provider unavailable"):
        retrieval.rank_passages(SAMPLE,"revenue",use_embeddings=True,embedding_client=Broken())


def test_invalid_embedding_vector_rejected(monkeypatch):
    monkeypatch.setenv("SEC_RESEARCH_ENABLED","true")
    monkeypatch.setenv("SEC_EMBEDDINGS_ENABLED","true")
    monkeypatch.setenv("BETA_DEMO_ONLY","false")
    monkeypatch.setenv("OPENAI_API_KEY","NOT_A_REAL_KEY")
    class Invalid:
        embeddings=SimpleNamespace(create=lambda *,model,input: SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.0,0.0])
                  for _ in input]))
    with pytest.raises(ValueError,match="zero vector"):
        retrieval.rank_passages(SAMPLE,"revenue",use_embeddings=True,embedding_client=Invalid())


def test_chunking_is_bounded_and_stable_across_repeated_invocations():
    longtext = "\n".join(
        "Fictional risk passage number " + str(i) + " explains supply-chain disruption and market liquidity. " * 3
        for i in range(250))
    a=retrieval.rank_passages(longtext,"liquidity and supply chain")
    b=retrieval.rank_passages(longtext,"liquidity and supply chain")
    assert a==b
    assert a["indexed_chunks"] <= retrieval.MAX_CHUNKS
    assert len(a["passages"]) <= 3


def _post(c,path,data):
    return c.post("/api/v4"+path,json=data,
                  headers={"X-CSRF-Token":c.cookies.get("piq_csrf") or ""})


def test_api_requires_explicit_semantic_consent_and_provider_configuration(monkeypatch):
    monkeypatch.setenv("BETA_DEMO_ONLY","false")
    monkeypatch.setenv("SEC_RESEARCH_ENABLED","true")
    monkeypatch.setenv("SEC_EMBEDDINGS_ENABLED","false")
    monkeypatch.setenv("SEC_USER_AGENT","PortfolioIQ Unit Test developer@example.test")
    monkeypatch.delenv("OPENAI_API_KEY",raising=False)
    with TestClient(app) as c:
        registration=c.post("/api/v4/auth/register",json={
            "email":f"v9b-{uuid4().hex}@example.test",
            "password":"LongStrongPassword!123"})
        assert registration.status_code==201,registration.text
        p=_post(c,"/portfolios",{"name":"Local research","kind":"snapshot"})
        assert p.status_code==201,p.text
        pid=p.json()["id"]
        csv=b"symbol,name,sector,asset_class,quantity,avg_cost,current_price\nAAA,Sample company,Technology,Equity,2,10,12\n"
        imp=c.post(f"/api/v4/portfolios/{pid}/holdings/csv",
                   files={"file":("fixture.csv",csv)},
                   headers={"X-CSRF-Token":c.cookies.get("piq_csrf") or ""})
        assert imp.status_code==200,imp.text
        st=c.get(f"/api/v4/portfolios/{pid}/research/sec/status").json()
        assert st["enabled"] and not st["semantic_rerank_enabled"]
        r=_post(c,f"/portfolios/{pid}/research/sec",{
            "symbol":"AAA","query":"supplier disruption","form":"10-K","use_embeddings":True})
        assert r.status_code==403,r.text
        assert "embedding provider" in r.text.lower()
        assert _post(c,f"/portfolios/{pid}/analyst",{
            "question":"supplier disruption","use_embeddings":True}).status_code==422


def test_offline_benchmark_has_exactly_180_meaningfully_checked_cases():
    from server.evaluation.phase9_benchmark import run
    result=run()
    assert result["evaluated"]==180
    assert len(result["categories"])==9
    assert result["failing"]==0
    assert all("actual_fixture" in str(result["categories"]) or result["passing"]==180
               for _ in [0])
