from pathlib import Path

from app.storage.metadata_store import MetadataStore


def test_collection_create_rename_delete_and_document_membership(tmp_path: Path) -> None:
    store = MetadataStore(str(tmp_path / "metadata.sqlite3"))
    store.init_db()

    collection = store.create_collection("Research")
    document = store.create_document("brief.md")

    assigned = store.assign_documents_to_collection(
        collection["collection_id"],
        [document["document_id"]],
    )
    assert assigned[0]["collection_id"] == collection["collection_id"]
    assert assigned[0]["collection_name"] == "Research"

    renamed = store.rename_collection(collection["collection_id"], "Evidence")
    assert renamed["collection_name"] == "Evidence"

    details = store.get_collection(collection["collection_id"], include_documents=True)
    assert details["document_count"] == 1
    assert details["documents"][0]["document_id"] == document["document_id"]

    deleted = store.soft_delete_collection(collection["collection_id"])
    assert deleted["collection_id"] == collection["collection_id"]
    assert store.get_collection(collection["collection_id"]) is None
    assert store.get_document(document["document_id"])["collection_id"] is None


def test_document_upload_metadata_with_collection(tmp_path: Path) -> None:
    store = MetadataStore(str(tmp_path / "metadata.sqlite3"))
    store.init_db()
    collection = store.create_collection("Client Packet")

    document = store.create_document(
        "recommendations.pdf",
        collection_id=collection["collection_id"],
        source_name="recommendations.pdf",
        source_type="upload",
        metadata={"kind": "test"},
    )
    chunk_count = 3
    store.update_document_chunk_count(document["document_id"], chunk_count)

    listed = store.list_documents()[0]
    assert listed["document_name"] == "recommendations.pdf"
    assert listed["collection_id"] == collection["collection_id"]
    assert listed["collection_name"] == "Client Packet"
    assert listed["chunk_count"] == chunk_count
    assert listed["metadata"] == {"kind": "test"}
