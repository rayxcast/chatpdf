from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import app_settings


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


class MetadataStore:
    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = Path(db_path or app_settings.METADATA_DB_PATH)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS collections (
                    collection_id TEXT PRIMARY KEY,
                    collection_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    deleted_at TEXT
                );

                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    document_name TEXT NOT NULL,
                    collection_id TEXT,
                    source_name TEXT,
                    source_type TEXT,
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (collection_id) REFERENCES collections(collection_id)
                );
                """
            )

    def create_collection(self, collection_name: str) -> dict[str, Any]:
        timestamp = _now()
        collection_id = _new_id("col")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO collections (
                    collection_id, collection_name, created_at, updated_at, deleted_at
                )
                VALUES (?, ?, ?, ?, NULL)
                """,
                (collection_id, collection_name, timestamp, timestamp),
            )
        collection = self.get_collection(collection_id)
        if not collection:
            raise RuntimeError("Collection was not created")
        return collection

    def list_collections(self, include_deleted: bool = False) -> list[dict[str, Any]]:
        where = "" if include_deleted else "WHERE deleted_at IS NULL"
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    c.*,
                    COUNT(d.document_id) AS document_count
                FROM collections c
                LEFT JOIN documents d
                    ON d.collection_id = c.collection_id
                {where}
                GROUP BY c.collection_id
                ORDER BY c.created_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_collection(
        self,
        collection_id: str,
        include_deleted: bool = False,
        include_documents: bool = False,
    ) -> dict[str, Any] | None:
        deleted_clause = "" if include_deleted else "AND deleted_at IS NULL"
        with self.connect() as conn:
            row = conn.execute(
                f"""
                SELECT
                    c.*,
                    (
                        SELECT COUNT(*)
                        FROM documents d
                        WHERE d.collection_id = c.collection_id
                    ) AS document_count
                FROM collections c
                WHERE collection_id = ? {deleted_clause}
                """,
                (collection_id,),
            ).fetchone()
            collection = _row_to_dict(row)
            if collection and include_documents:
                collection["documents"] = self._list_documents_for_collection(conn, collection_id)
            return collection

    def rename_collection(self, collection_id: str, collection_name: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE collections
                SET collection_name = ?, updated_at = ?
                WHERE collection_id = ? AND deleted_at IS NULL
                """,
                (collection_name, _now(), collection_id),
            )
        return self.get_collection(collection_id)

    def soft_delete_collection(self, collection_id: str) -> dict[str, Any] | None:
        timestamp = _now()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM collections WHERE collection_id = ? AND deleted_at IS NULL",
                (collection_id,),
            ).fetchone()
            if not row:
                return None
            conn.execute(
                """
                UPDATE documents
                SET collection_id = NULL, updated_at = ?
                WHERE collection_id = ?
                """,
                (timestamp, collection_id),
            )
            conn.execute(
                """
                UPDATE collections
                SET deleted_at = ?, updated_at = ?
                WHERE collection_id = ?
                """,
                (timestamp, timestamp, collection_id),
            )
        return dict(row)

    def create_document(
        self,
        document_name: str,
        collection_id: str | None = None,
        source_name: str | None = None,
        source_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if collection_id:
            self.require_collection(collection_id)

        document_id = _new_id("doc")
        timestamp = _now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO documents (
                    document_id, document_name, collection_id, source_name,
                    source_type, chunk_count, metadata_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)
                """,
                (
                    document_id,
                    document_name,
                    collection_id,
                    source_name,
                    source_type,
                    json.dumps(metadata or {}),
                    timestamp,
                    timestamp,
                ),
            )
        document = self.get_document(document_id)
        if not document:
            raise RuntimeError("Document was not created")
        return document

    def list_documents(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    d.*,
                    c.collection_name
                FROM documents d
                LEFT JOIN collections c
                    ON c.collection_id = d.collection_id
                    AND c.deleted_at IS NULL
                ORDER BY d.created_at DESC
                """
            ).fetchall()
        return [self._document_from_row(row) for row in rows]

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    d.*,
                    c.collection_name
                FROM documents d
                LEFT JOIN collections c
                    ON c.collection_id = d.collection_id
                    AND c.deleted_at IS NULL
                WHERE d.document_id = ?
                """,
                (document_id,),
            ).fetchone()
        return self._document_from_row(row) if row else None

    def update_document_chunk_count(self, document_id: str, chunk_count: int) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE documents
                SET chunk_count = ?, updated_at = ?
                WHERE document_id = ?
                """,
                (chunk_count, _now(), document_id),
            )

    def assign_documents_to_collection(
        self,
        collection_id: str,
        document_ids: list[str],
    ) -> list[dict[str, Any]]:
        self.require_collection(collection_id)
        self.require_documents(document_ids)
        if not document_ids:
            return []

        placeholders = ",".join("?" for _ in document_ids)
        with self.connect() as conn:
            conn.execute(
                f"""
                UPDATE documents
                SET collection_id = ?, updated_at = ?
                WHERE document_id IN ({placeholders})
                """,
                (collection_id, _now(), *document_ids),
            )
        return [doc for doc in self.list_documents() if doc["document_id"] in set(document_ids)]

    def remove_document_from_collection(
        self,
        collection_id: str,
        document_id: str,
    ) -> dict[str, Any] | None:
        document = self.get_document(document_id)
        if not document or document.get("collection_id") != collection_id:
            return None
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE documents
                SET collection_id = NULL, updated_at = ?
                WHERE document_id = ? AND collection_id = ?
                """,
                (_now(), document_id, collection_id),
            )
        return self.get_document(document_id)

    def clear_documents(self) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM documents")

    def require_collection(self, collection_id: str) -> dict[str, Any]:
        collection = self.get_collection(collection_id)
        if not collection:
            raise KeyError(f"Collection not found: {collection_id}")
        return collection

    def require_documents(self, document_ids: list[str]) -> list[dict[str, Any]]:
        if not document_ids:
            return []
        documents = [self.get_document(document_id) for document_id in document_ids]
        missing = [
            document_id
            for document_id, document in zip(document_ids, documents, strict=False)
            if document is None
        ]
        if missing:
            raise KeyError(f"Document not found: {', '.join(missing)}")
        return [document for document in documents if document]

    def _list_documents_for_collection(
        self,
        conn: sqlite3.Connection,
        collection_id: str,
    ) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT
                d.*,
                c.collection_name
            FROM documents d
            LEFT JOIN collections c
                ON c.collection_id = d.collection_id
                AND c.deleted_at IS NULL
            WHERE d.collection_id = ?
            ORDER BY d.created_at DESC
            """,
            (collection_id,),
        ).fetchall()
        return [self._document_from_row(row) for row in rows]

    @staticmethod
    def _document_from_row(row: sqlite3.Row) -> dict[str, Any]:
        document = dict(row)
        metadata_json = document.pop("metadata_json", "{}") or "{}"
        try:
            document["metadata"] = json.loads(metadata_json)
        except json.JSONDecodeError:
            document["metadata"] = {}
        return document
