from types import SimpleNamespace
from typing import Any

import pytest
from pytest import MonkeyPatch

from app.api.endpoints.query import QueryRequest
from app.rag.pipeline import HybridRAG

TOP_K = 12


class FakeRetriever:
    def __init__(self, nodes: list[Any]) -> None:
        self.nodes = nodes
        self.calls = []

    async def retrieve(
        self,
        query: str,
        support_hybrid: bool = True,
        document_ids: list[str] | None = None,
        collection_ids: list[str] | None = None,
        top_k: int | None = None,
    ) -> list[Any]:
        self.calls.append(
            {
                "query": query,
                "support_hybrid": support_hybrid,
                "document_ids": document_ids,
                "collection_ids": collection_ids,
                "top_k": top_k,
            }
        )
        return self.nodes


class FakeReranker:
    def __init__(self) -> None:
        self.nodes = None

    async def rerank(self, query: str, nodes: list[Any], top_n: int = 25) -> list[Any]:
        self.nodes = list(nodes)
        return nodes[:top_n]


class FakeGenerator:
    async def generate(self, query: str, final_nodes: list[Any]) -> dict[str, Any]:
        return {"answer": "ok", "sources": [node.node.metadata for node in final_nodes]}


class FakeVectorStoreProvider:
    def supports_sparse(self) -> bool:
        return True


def fake_config() -> SimpleNamespace:
    return SimpleNamespace(
        LLM_PROVIDER="openai",
        DENSE_PROVIDER="openai",
        SPARSE_PROVIDER="fastembed",
        RERANKER_PROVIDER="remote",
        LLM_MODEL="test-llm",
        EMBEDDING_MODEL="test-embed",
        SPARSE_MODEL="test-sparse",
        RERANKER_MODEL="test-reranker",
        RETRIEVAL_MODE="hybrid",
        SIMILARITY_TOP_K=50,
        SIMILARITY_CUTOFF=0.0,
        RERANK_TOP_N=20,
        FINAL_CONTEXT_N=7,
        USE_CACHE=True,
        USE_RERANKER=True,
    )


def fake_node(document_id: str, collection_id: str | None = None) -> SimpleNamespace:
    node = SimpleNamespace(
        text=f"text for {document_id}",
        metadata={
            "chunk_id": f"chunk_{document_id}",
            "document_id": document_id,
            "document_name": f"{document_id}.md",
            "collection_id": collection_id,
        },
    )
    return SimpleNamespace(node=node, score=0.9)


def test_query_request_accepts_legacy_and_new_shapes() -> None:
    assert QueryRequest(query="legacy").query == "legacy"
    request = QueryRequest(
        question="new",
        document_ids=["doc_1"],
        collection_ids=["col_1"],
        top_k=TOP_K,
    )
    assert request.question == "new"


@pytest.mark.asyncio
async def test_scoped_query_bypasses_cache_and_reranks_only_scoped_candidates(
    monkeypatch: MonkeyPatch,
) -> None:
    nodes = [fake_node("doc_1", "col_1")]
    rag = HybridRAG.__new__(HybridRAG)
    rag.config = fake_config()
    rag.retriever = FakeRetriever(nodes)
    rag.reranker = FakeReranker()
    rag.generator = FakeGenerator()
    rag.vector_store_provider = FakeVectorStoreProvider()

    async def forbidden_cache(*args: object, **kwargs: object) -> None:
        raise AssertionError("scoped queries must not call semantic cache")

    monkeypatch.setattr("app.rag.pipeline.get_semantic", forbidden_cache)

    result = await rag.query(
        "question",
        trace_id="trace",
        document_ids=["doc_1"],
        collection_ids=["col_1"],
        top_k=TOP_K,
    )

    assert result["answer"] == "ok"
    assert rag.retriever.calls[0]["document_ids"] == ["doc_1"]
    assert rag.retriever.calls[0]["collection_ids"] == ["col_1"]
    assert rag.retriever.calls[0]["top_k"] == TOP_K
    assert rag.reranker.nodes == nodes
    assert result["trace"]["cache"]["enabled"] is False
    assert result["trace"]["scope"]["scoped"] is True
