import pytest
from pytest import MonkeyPatch

from app.evaluation.evaluator import RAGEvaluator


def test_eval_judge_inherits_main_llm_when_eval_overrides_are_empty(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.evaluation.evaluator.app_settings.EVAL_LLM_PROVIDER", None)
    monkeypatch.setattr("app.evaluation.evaluator.app_settings.EVAL_LLM_MODEL", None)
    monkeypatch.setattr("app.evaluation.evaluator.app_settings.LLM_PROVIDER", "google")
    monkeypatch.setattr("app.evaluation.evaluator.app_settings.LLM_MODEL", "gemini-test")

    calls = {}

    def fake_get_llm(provider: str | None = None, model: str | None = None) -> object:
        calls["provider"] = provider
        calls["model"] = model
        return object()

    monkeypatch.setattr("app.evaluation.evaluator.get_llm", fake_get_llm)

    evaluator = RAGEvaluator(rag_pipeline=object())

    assert evaluator.eval_provider == "google"
    assert evaluator.eval_model == "gemini-test"
    assert calls == {"provider": "google", "model": "gemini-test"}


def test_expected_contains_recall_supports_lists() -> None:
    evaluator = RAGEvaluator.__new__(RAGEvaluator)

    assert evaluator.expected_contains_recall(
        "Maya Chen, Jordan Ellis, and Priya Shah are the first shortlist.",
        ["Maya Chen", "Jordan Ellis", "Priya Shah"],
    )
    assert not evaluator.expected_contains_recall(
        "Maya Chen and Jordan Ellis are the first shortlist.",
        ["Maya Chen", "Jordan Ellis", "Priya Shah"],
    )


def test_expected_contains_recall_treats_empty_expectation_as_pass() -> None:
    evaluator = RAGEvaluator.__new__(RAGEvaluator)

    assert evaluator.expected_contains_recall("Any answer", [])
    assert evaluator.expected_contains_recall("Any answer", [""])


@pytest.mark.asyncio
async def test_answerable_case_with_no_retrieval_fails_without_judge() -> None:
    class EmptyRag:
        async def query(self, *args: object, **kwargs: object) -> dict:
            return {
                "answer": "The answer is not present in the provided documents.",
                "retrieved_nodes": [],
                "reranked_nodes": [],
                "latency": {"retrieval": 0.01, "generation": 0},
            }

    evaluator = RAGEvaluator.__new__(RAGEvaluator)
    evaluator.rag = EmptyRag()

    result = await evaluator.evaluate_case(
        {
            "id": "answerable",
            "question": "What does the document say?",
            "expected_contains": ["evidence"],
            "should_refuse": False,
        }
    )

    assert result["passed"] is False
    assert result["eval"]["reasoning"] == "Answerable case retrieved 0 chunks; judge skipped."
