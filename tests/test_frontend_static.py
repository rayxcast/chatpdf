from pathlib import Path


def test_frontend_sends_selected_scope_and_collapses_details_by_default() -> None:
    app_js = Path("app/static/app.js").read_text()
    index_html = Path("app/static/index.html").read_text()

    assert "selectedDocumentIds" in app_js
    assert "selectedCollectionIds" in app_js
    assert "selectedFiles" in app_js
    assert 'formData.append("files", file)' in app_js
    assert "multiple" in index_html
    assert "JSON.stringify({ question: query, document_ids, collection_ids })" in app_js
    assert "els.detailsBody.classList.add(\"hidden\")" in app_js
    assert "function scopeDocumentRow(document)" not in app_js
    assert "async function moveDocument(document," not in app_js
    assert "Show details" in index_html
