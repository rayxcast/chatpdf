from pathlib import Path

from llama_index.core import Document
from llama_index.core.node_parser import SentenceSplitter

from app.rag.ingestion import _decorate_documents, _decorate_nodes
from app.storage.metadata_store import MetadataStore

BATCH_DOCUMENT_COUNT = 2


def test_chunk_metadata_includes_scope_fields(tmp_path: Path) -> None:
    store = MetadataStore(str(tmp_path / "metadata.sqlite3"))
    store.init_db()
    collection = store.create_collection("Scope")

    source = Document(
        text="Recommendation one has evidence. Recommendation two has evidence.",
        metadata={"file_name": "evidence.md", "page_label": "1"},
    )

    documents, created, collection_record = _decorate_documents(
        documents=[source],
        metadata_store=store,
        collection_id=collection["collection_id"],
        source_name="evidence.md",
        source_type="upload",
    )
    nodes = SentenceSplitter(chunk_size=128, chunk_overlap=0).get_nodes_from_documents(documents)
    chunk_counts = _decorate_nodes(nodes, collection_record)

    document = next(iter(created.values()))
    metadata = nodes[0].metadata
    assert metadata["chunk_id"] == nodes[0].id_
    assert metadata["document_id"] == document["document_id"]
    assert metadata["doc_id"] == document["document_id"]
    assert metadata["document_name"] == "evidence.md"
    assert metadata["collection_id"] == collection["collection_id"]
    assert metadata["collection_name"] == "Scope"
    assert metadata["page_number"] == 1
    assert metadata["text"] == nodes[0].text
    assert chunk_counts[document["document_id"]] == len(nodes)


def test_batch_upload_keeps_per_file_document_names(tmp_path: Path) -> None:
    store = MetadataStore(str(tmp_path / "metadata.sqlite3"))
    store.init_db()

    sources = [
        Document(text="Alpha evidence", metadata={"file_name": "alpha.md"}),
        Document(text="Beta evidence", metadata={"file_name": "beta.md"}),
    ]

    documents, created, _collection_record = _decorate_documents(
        documents=sources,
        metadata_store=store,
        collection_id=None,
        source_name="2 uploaded files",
        source_type="upload",
    )

    assert len(documents) == BATCH_DOCUMENT_COUNT
    assert {record["document_name"] for record in created.values()} == {"alpha.md", "beta.md"}
