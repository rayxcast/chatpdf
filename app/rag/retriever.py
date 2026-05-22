"""Hybrid RAG query engine: retrieval + generation + flags + fallback."""
import structlog
import yaml
from llama_index.core import PromptTemplate, VectorStoreIndex
from llama_index.core.postprocessor import SimilarityPostprocessor
from llama_index.core.vector_stores import (
    FilterCondition,
    FilterOperator,
    MetadataFilter,
    MetadataFilters,
)

from app.config import app_settings, configure_llm_settings
from app.rag.vectorstores.factory import get_vector_store_provider

logger = structlog.get_logger()

# Load prompts
with open("app/rag/prompts.yaml") as f:
    prompts = yaml.safe_load(f)
qa_prompt = PromptTemplate(prompts["v2"]["qa"])


def build_scope_filters(
    document_ids: list[str] | None = None,
    collection_ids: list[str] | None = None,
) -> MetadataFilters | None:
    filters = []
    if document_ids:
        filters.append(
            MetadataFilter(
                key="document_id",
                value=document_ids,
                operator=FilterOperator.IN,
            )
        )
    if collection_ids:
        filters.append(
            MetadataFilter(
                key="collection_id",
                value=collection_ids,
                operator=FilterOperator.IN,
            )
        )

    if not filters:
        return None

    return MetadataFilters(filters=filters, condition=FilterCondition.OR)


class Retriever:
    def __init__(self) -> None:
        configure_llm_settings()
        self.vector_store_provider = get_vector_store_provider()
        self.config = app_settings

    async def retrieve(
        self,
        query: str,
        support_hybrid: bool = True,
        document_ids: list[str] | None = None,
        collection_ids: list[str] | None = None,
        top_k: int | None = None,
    ) -> list:
        try:
            index = VectorStoreIndex.from_vector_store(
                self.vector_store_provider.get_vector_store()
            )
            mode = (
                "hybrid"
                if self.config.RETRIEVAL_MODE == "hybrid" and support_hybrid
                else "default"
            )
            node_postprocessors = [
                SimilarityPostprocessor(similarity_cutoff=self.config.SIMILARITY_CUTOFF)
            ]
            filters = build_scope_filters(document_ids, collection_ids)

            retriever = index.as_retriever(
                similarity_top_k=top_k or self.config.SIMILARITY_TOP_K,
                node_postprocessors=node_postprocessors,
                vector_store_query_mode=mode,
                filters=filters,
            )

            retrieved_nodes = await retriever.aretrieve(query)
            if retrieved_nodes:
                return retrieved_nodes

        except Exception as e:
            logger.error("retrieval_failed", error=str(e), exc_info=True)

        return []
