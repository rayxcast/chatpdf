from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.rag.vectorstores.factory import get_vector_store_provider
from app.storage.metadata_store import MetadataStore

router = APIRouter(tags=["collections"])
store = MetadataStore()


class CollectionCreateRequest(BaseModel):
    collection_name: str = Field(..., min_length=1)


class CollectionUpdateRequest(BaseModel):
    collection_name: str = Field(..., min_length=1)


class CollectionDocumentsRequest(BaseModel):
    document_ids: list[str] = Field(default_factory=list)


def _not_found(message: str) -> HTTPException:
    return HTTPException(status_code=404, detail=message)


@router.post("/collections")
async def create_collection(req: CollectionCreateRequest) -> dict[str, Any]:
    store.init_db()
    return store.create_collection(req.collection_name.strip())


@router.get("/collections")
async def list_collections() -> dict[str, list[dict[str, Any]]]:
    store.init_db()
    return {"collections": store.list_collections()}


@router.get("/collections/{collection_id}")
async def get_collection(collection_id: str) -> dict[str, Any]:
    store.init_db()
    collection = store.get_collection(collection_id, include_documents=True)
    if not collection:
        raise _not_found("Collection not found")
    return collection


@router.patch("/collections/{collection_id}")
async def update_collection(
    collection_id: str,
    req: CollectionUpdateRequest,
) -> dict[str, Any]:
    store.init_db()
    collection = store.rename_collection(collection_id, req.collection_name.strip())
    if not collection:
        raise _not_found("Collection not found")

    documents = store.get_collection(collection_id, include_documents=True)["documents"]
    document_ids = [document["document_id"] for document in documents]
    await get_vector_store_provider().update_document_scope_payloads(
        document_ids=document_ids,
        collection_id=collection_id,
        collection_name=collection["collection_name"],
    )
    return collection


@router.delete("/collections/{collection_id}")
async def delete_collection(collection_id: str) -> dict[str, Any]:
    store.init_db()
    collection = store.get_collection(collection_id, include_documents=True)
    if not collection:
        raise _not_found("Collection not found")

    document_ids = [document["document_id"] for document in collection["documents"]]
    deleted = store.soft_delete_collection(collection_id)
    await get_vector_store_provider().update_document_scope_payloads(
        document_ids=document_ids,
        collection_id=None,
        collection_name=None,
    )
    return {"deleted": True, "collection": deleted, "ungrouped_document_ids": document_ids}


@router.post("/collections/{collection_id}/documents")
async def add_documents_to_collection(
    collection_id: str,
    req: CollectionDocumentsRequest,
) -> dict[str, list[dict[str, Any]]]:
    store.init_db()
    try:
        documents = store.assign_documents_to_collection(collection_id, req.document_ids)
        collection = store.require_collection(collection_id)
    except KeyError as error:
        raise _not_found(str(error)) from error

    await get_vector_store_provider().update_document_scope_payloads(
        document_ids=req.document_ids,
        collection_id=collection_id,
        collection_name=collection["collection_name"],
    )
    return {"documents": documents}


@router.delete("/collections/{collection_id}/documents/{document_id}")
async def remove_document_from_collection(
    collection_id: str,
    document_id: str,
) -> dict[str, Any]:
    store.init_db()
    document = store.remove_document_from_collection(collection_id, document_id)
    if not document:
        raise _not_found("Document not found in collection")

    await get_vector_store_provider().update_document_scope_payloads(
        document_ids=[document_id],
        collection_id=None,
        collection_name=None,
    )
    return document


@router.get("/documents")
async def list_documents() -> dict[str, list[dict[str, Any]]]:
    store.init_db()
    return {"documents": store.list_documents()}
