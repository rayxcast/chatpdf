from typing import Any

import structlog
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import AsyncQdrantClient, QdrantClient, models

from app.config import app_settings

from .base import BaseVectorStoreProvider

logger = structlog.get_logger()

class QdrantHybridStore(BaseVectorStoreProvider):

    def __init__(self, sparse_provider: object = None) -> None:
        self.client = QdrantClient(url=app_settings.QDRANT_URL)
        self.aclient = AsyncQdrantClient(url=app_settings.QDRANT_URL)
        self.sparse = sparse_provider

    async def init_collection_if_needed(self) -> None:
        if not await self.aclient.collection_exists(app_settings.COLLECTION_NAME):
            await self.aclient.create_collection(
                collection_name=app_settings.COLLECTION_NAME,
                vectors_config=models.VectorParams(
                    size=app_settings.EMBEDDING_DIM,
                    distance=models.Distance.COSINE,
                ),
                sparse_vectors_config={
                    "text-sparse": models.SparseVectorParams()
                },
            )
            logger.info("created_qdrant_collection", name=app_settings.COLLECTION_NAME)

    def get_vector_store(self) -> QdrantVectorStore:
        return QdrantVectorStore(
            client=self.client,     # Used for sync calls
            aclient=self.aclient,   # Used for async calls
            collection_name=app_settings.COLLECTION_NAME,
            enable_hybrid=True,
            sparse_doc_fn=self.sparse.embed_documents,
            sparse_query_fn=self.sparse.embed_query,
            text_sparse_name="text-sparse",
            use_default_sparse_query_encoder=False,
        )

    async def delete_collection(self) -> dict[str, Any]:
        try:
            if not await self.aclient.collection_exists(app_settings.COLLECTION_NAME):
                return {
                    "deleted": False,
                    "collection_name": app_settings.COLLECTION_NAME,
                    "existed": False,
                }

            await self.aclient.delete_collection(app_settings.COLLECTION_NAME)
            return {
                "deleted": True,
                "collection_name": app_settings.COLLECTION_NAME,
                "existed": True,
            }
        except Exception as error:
            logger.error(
                "delete_collection_failed",
                error=str(error),
                collection=app_settings.COLLECTION_NAME,
            )

        return {
            "deleted": False,
            "collection_name": app_settings.COLLECTION_NAME,
            "existed": None,
        }

    async def update_document_scope_payloads(
        self,
        document_ids: list[str],
        collection_id: str | None,
        collection_name: str | None,
    ) -> dict[str, Any]:
        if not document_ids:
            return {"updated": False, "document_count": 0}

        if not await self.aclient.collection_exists(app_settings.COLLECTION_NAME):
            return {
                "updated": False,
                "document_count": len(document_ids),
                "collection_exists": False,
            }

        payload_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="document_id",
                    match=models.MatchAny(any=document_ids),
                )
            ]
        )

        await self.aclient.set_payload(
            collection_name=app_settings.COLLECTION_NAME,
            payload={
                "collection_id": collection_id,
                "collection_name": collection_name,
            },
            points=payload_filter,
        )
        return {"updated": True, "document_count": len(document_ids), "collection_exists": True}

    def supports_sparse(self) -> bool:
        return True
