import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

import structlog
from llama_index.core import Document, SimpleDirectoryReader
from llama_index.core.node_parser import SentenceSplitter
from llama_index.readers.file import PDFReader, PyMuPDFReader

from app.config import app_settings, configure_llm_settings
from app.rag.hybrid_indexer import HybridIndexer
from app.storage.metadata_store import MetadataStore

logger = structlog.get_logger()

configure_llm_settings()

# ------------------------
# Text Cleaning
# ------------------------

def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"endobj.*?obj", "", text, flags=re.DOTALL)
    text = re.sub(r"/Type\s*/\w+", "", text)
    return text.strip()

# ------------------------
# Dynamic file Loader (Production Robust)
# ------------------------

def load_documents(input_path: str) -> list[Document]:
    input_path = Path(input_path)
    documents = []

    pdf_files = list(input_path.glob("**/*.pdf"))
    other_files = list(input_path.glob("**/*.*"))

    # ---- PDFs
    for file in pdf_files:
        try:
            reader = PyMuPDFReader()
            docs = reader.load_data(file_path=str(file))
            logger.info("Loaded PDF with PyMuPDF", file=str(file))
        except Exception:
            reader = PDFReader()
            docs = reader.load_data(file=str(file))
            logger.warning("Fallback to PDFReader", file=str(file))

        cleaned_docs = [
            Document(
                text=clean_text(d.text),
                metadata={
                    **d.metadata,
                    "file_path": str(file),
                    "file_name": file.name,
                },
            )
            for d in docs
        ]

        documents.extend(cleaned_docs)

    # ---- MD / TXT
    non_pdf_files = [
        f for f in other_files
        if f.suffix.lower() in [".md", ".txt"]
    ]

    if non_pdf_files:
        reader = SimpleDirectoryReader(
            input_files=[str(f) for f in non_pdf_files]
        )
        docs = reader.load_data()

        cleaned_docs = [
            Document(
                text=clean_text(d.text),
                metadata=d.metadata,
            )
            for d in docs
        ]

        documents.extend(cleaned_docs)

    if not documents:
        supported = [".pdf", ".txt", ".md", ".docx", ".doc", ".html"]  # adjust to your loader
        raise ValueError(f"No supported documents found in '{input_path}'. Supported: {supported}")

    return documents


def _source_key(document: Document, fallback: str) -> str:
    metadata = document.metadata or {}
    return str(
        metadata.get("file_path")
        or metadata.get("filename")
        or metadata.get("file_name")
        or fallback
    )


def _display_name(document: Document, fallback: str) -> str:
    metadata = document.metadata or {}
    value = (
        metadata.get("file_name")
        or metadata.get("filename")
        or metadata.get("file_path")
        or fallback
    )
    return Path(str(value)).name


def _page_number(metadata: dict[str, Any]) -> int | str | None:
    for key in ("page_number", "page_label", "page"):
        value = metadata.get(key)
        if value not in (None, ""):
            try:
                return int(value)
            except (TypeError, ValueError):
                return str(value)
    return None


def _decorate_documents(
    documents: list[Document],
    metadata_store: MetadataStore,
    collection_id: str | None,
    source_name: str | None,
    source_type: str | None,
) -> tuple[list[Document], dict[str, dict[str, Any]], dict[str, Any] | None]:
    collection = metadata_store.require_collection(collection_id) if collection_id else None
    created_by_source: dict[str, dict[str, Any]] = {}
    decorated: list[Document] = []

    for document in documents:
        source_key = _source_key(document, source_name or "uploaded document")
        if source_key not in created_by_source:
            document_name = _display_name(document, source_name or source_key)
            created_by_source[source_key] = metadata_store.create_document(
                document_name=document_name,
                collection_id=collection_id,
                source_name=source_name or source_key,
                source_type=source_type or "path",
                metadata={"source_key": source_key},
            )

        record = created_by_source[source_key]
        metadata = {
            **(document.metadata or {}),
            "document_id": record["document_id"],
            "document_name": record["document_name"],
            "collection_id": collection_id,
            "collection_name": collection["collection_name"] if collection else None,
        }
        page_number = _page_number(metadata)
        if page_number is not None:
            metadata["page_number"] = page_number

        decorated.append(
            Document(
                text=document.text,
                id_=record["document_id"],
                metadata=metadata,
                excluded_embed_metadata_keys=[
                    "text",
                    "chunk_id",
                    "collection_id",
                    "collection_name",
                    "document_id",
                    "document_name",
                ],
            )
        )

    return decorated, created_by_source, collection


def _decorate_nodes(nodes: list, collection: dict[str, Any] | None) -> Counter[str]:
    chunk_counts: Counter[str] = Counter()
    excluded_keys = {
        "text",
        "chunk_id",
        "collection_id",
        "collection_name",
        "document_id",
        "document_name",
    }

    for node in nodes:
        metadata = dict(getattr(node, "metadata", {}) or {})
        document_id = str(metadata.get("document_id") or getattr(node, "ref_doc_id", "") or "")
        metadata["chunk_id"] = getattr(node, "id_", None) or getattr(node, "node_id", None)
        metadata["document_id"] = document_id
        metadata["doc_id"] = document_id
        metadata["collection_id"] = metadata.get("collection_id")
        metadata["collection_name"] = (
            collection["collection_name"]
            if metadata.get("collection_id") and collection
            else metadata.get("collection_name")
        )
        page_number = _page_number(metadata)
        if page_number is not None:
            metadata["page_number"] = page_number
        metadata["text"] = node.text
        node.metadata = metadata
        node.excluded_embed_metadata_keys = sorted(
            set(node.excluded_embed_metadata_keys) | excluded_keys
        )
        node.excluded_llm_metadata_keys = sorted(set(node.excluded_llm_metadata_keys) | {"text"})
        if document_id:
            chunk_counts[document_id] += 1

    return chunk_counts

# ------------------------
# Ingest Pipeline
# ------------------------
async def ingest_documents(  # noqa: PLR0913
    input_path: str,
    recreate: bool = False,
    request_id: str | None = None,
    source_name: str | None = None,
    source_type: str | None = None,
    collection_id: str | None = None,
) -> dict[str, Any]:
    total_start = time.perf_counter()
    timings = {}
    trace = {
        "request_id": request_id,
        "operation": "ingest",
        "source": {
            "name": source_name or input_path,
            "type": source_type or "path",
        },
        "collection_id": collection_id,
        "recreate": recreate,
        "providers": {
            "llm": app_settings.LLM_PROVIDER,
            "embedding": app_settings.DENSE_PROVIDER,
            "sparse": app_settings.SPARSE_PROVIDER,
            "reranker": app_settings.RERANKER_PROVIDER,
        },
        "models": {
            "llm": app_settings.LLM_MODEL,
            "embedding": app_settings.EMBEDDING_MODEL,
            "sparse": app_settings.SPARSE_MODEL,
            "reranker": app_settings.RERANKER_MODEL,
        },
        "retrieval_mode": app_settings.RETRIEVAL_MODE,
        "warnings": [
            (
                "Reset/re-ingest when embedding provider, embedding model, "
                "or embedding dimension changes."
            ),
        ],
    }

    try:
        logger.info(
            "ingestion_started",
            request_id=request_id,
            source_name=source_name or input_path,
            source_type=source_type or "path",
            recreate=recreate,
            llm_provider=app_settings.LLM_PROVIDER,
            embedding_provider=app_settings.DENSE_PROVIDER,
            retrieval_mode=app_settings.RETRIEVAL_MODE,
        )
        indexer = HybridIndexer()
        metadata_store = MetadataStore()
        metadata_store.init_db()

        if recreate:
            start = time.perf_counter()
            deleted = await indexer.store_provider.delete_collection()
            metadata_store.clear_documents()
            timings["delete_collection"] = round(time.perf_counter() - start, 4)
            logger.info(
                "collection_delete_finished",
                request_id=request_id,
                collection_name=deleted["collection_name"],
                deleted=deleted["deleted"],
                existed=deleted.get("existed"),
                duration_seconds=timings["delete_collection"],
            )

        start = time.perf_counter()
        await indexer.store_provider.init_collection_if_needed()
        timings["init_collection"] = round(time.perf_counter() - start, 4)

        # ---- Load Documents
        start = time.perf_counter()
        documents = load_documents(input_path)
        documents, created_documents, collection = _decorate_documents(
            documents=documents,
            metadata_store=metadata_store,
            collection_id=collection_id,
            source_name=source_name,
            source_type=source_type,
        )
        timings["load_documents"] = round(time.perf_counter() - start, 4)
        logger.info(
            "documents_loaded",
            request_id=request_id,
            document_count=len(created_documents),
            loaded_document_units=len(documents),
            duration_seconds=timings["load_documents"],
        )

        # ---- Chunking
        splitter = SentenceSplitter(
            chunk_size=app_settings.CHUNK_SIZE,
            chunk_overlap=app_settings.CHUNK_OVERLAP,
        )

        start = time.perf_counter()
        nodes = splitter.get_nodes_from_documents(documents)
        chunk_counts = _decorate_nodes(nodes, collection)
        for document_id, chunk_count in chunk_counts.items():
            metadata_store.update_document_chunk_count(document_id, chunk_count)
        timings["chunking"] = round(time.perf_counter() - start, 4)
        logger.info(
            "nodes_created",
            request_id=request_id,
            chunk_count=len(nodes),
            duration_seconds=timings["chunking"],
        )

        # ---- Indexing (Dense + Sparse + Insert)
        start = time.perf_counter()
        indexer.build_index(nodes)
        timings["indexing"] = round(time.perf_counter() - start, 4)
        timings["total"] = round(time.perf_counter() - total_start, 4)
        logger.info(
            "index_built",
            request_id=request_id,
            duration_seconds=timings["indexing"],
            total_duration_seconds=timings["total"],
        )

        return {
            "status": "success",
            "docs_ingested": len(created_documents),
            "nodes": len(nodes),
            "documents": list(created_documents.values()),
            "trace": {
                **trace,
                "status": "success",
                "document_count": len(created_documents),
                "loaded_document_units": len(documents),
                "chunk_count": len(nodes),
                "timings": timings,
            },
        }

    except Exception as e:
        timings["total"] = round(time.perf_counter() - total_start, 4)
        logger.error(
            "ingestion_failed",
            request_id=request_id,
            error=str(e),
            duration_seconds=timings["total"],
            exc_info=True,
        )
        raise
