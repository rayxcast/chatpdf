# rag/vectorstores/base.py

from abc import ABC, abstractmethod

from llama_index.core.vector_stores.types import BasePydanticVectorStore


class BaseVectorStoreProvider(ABC):

    @abstractmethod
    def get_vector_store(self) -> BasePydanticVectorStore:
        pass

    @abstractmethod
    def supports_sparse(self) -> bool:
        pass

    async def init_collection_if_needed(self) -> None:
        """Optional lifecycle hook"""
        return None

    async def delete_collection(self) -> None:
        """Optional lifecycle hook"""
        return None

    async def update_document_scope_payloads(
        self,
        document_ids: list[str],
        collection_id: str | None,
        collection_name: str | None,
    ) -> None:
        """Optional hook to update document collection payloads in-place."""
        return None
