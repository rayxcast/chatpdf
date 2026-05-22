from llama_index.core.vector_stores import FilterCondition, FilterOperator

from app.rag.retriever import build_scope_filters


def test_document_scope_filter() -> None:
    filters = build_scope_filters(document_ids=["doc_1", "doc_2"])

    assert filters.condition == FilterCondition.OR
    assert len(filters.filters) == 1
    assert filters.filters[0].key == "document_id"
    assert filters.filters[0].operator == FilterOperator.IN
    assert filters.filters[0].value == ["doc_1", "doc_2"]


def test_collection_scope_filter() -> None:
    filters = build_scope_filters(collection_ids=["col_1"])

    assert filters.condition == FilterCondition.OR
    assert len(filters.filters) == 1
    assert filters.filters[0].key == "collection_id"
    assert filters.filters[0].operator == FilterOperator.IN
    assert filters.filters[0].value == ["col_1"]


def test_mixed_scope_filter_uses_or() -> None:
    filters = build_scope_filters(document_ids=["doc_1"], collection_ids=["col_1"])

    assert filters.condition == FilterCondition.OR
    assert {item.key for item in filters.filters} == {"document_id", "collection_id"}


def test_no_scope_filter_is_global() -> None:
    assert build_scope_filters() is None
