from pathlib import Path

from app.rag.ingestion import load_documents

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_synthetic_research_fixture_is_loadable_and_non_sensitive() -> None:
    documents = load_documents(str(FIXTURE_DIR))

    assert len(documents) == 1
    assert documents[0].metadata["file_name"] == "synthetic_research_brief.md"
    assert "entirely synthetic" in documents[0].text
    assert "six-week pilot" in documents[0].text
    assert "$48,000" in documents[0].text
