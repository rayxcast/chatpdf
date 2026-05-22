from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field

from app.rag.pipeline import HybridRAG
from app.storage.metadata_store import MetadataStore

router = APIRouter(prefix="/query", tags=["query"])
metadata_store = MetadataStore()

class QueryRequest(BaseModel):
    query: str | None = None
    question: str | None = None
    document_ids: list[str] = Field(default_factory=list)
    collection_ids: list[str] = Field(default_factory=list)
    top_k: int | None = Field(default=None, gt=0, le=200)


@lru_cache(maxsize=1)
def get_rag() -> HybridRAG:
    return HybridRAG()


@router.post("/")
async def query_endpoint(
    request: Request,
    req: Annotated[QueryRequest, Body(...)],
) -> dict[str, Any]:
    request_id = getattr(request.state, "request_id", "no-id")
    question = (req.question or req.query or "").strip()
    if not question:
        raise HTTPException(status_code=422, detail="Provide 'question' or legacy 'query'.")

    metadata_store.init_db()
    try:
        for collection_id in req.collection_ids:
            metadata_store.require_collection(collection_id)
        metadata_store.require_documents(req.document_ids)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    return await get_rag().query(
        question,
        trace_id=request_id,
        document_ids=req.document_ids,
        collection_ids=req.collection_ids,
        top_k=req.top_k,
    )
