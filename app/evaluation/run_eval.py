import asyncio
import json
import os
import time
from typing import Any

from qdrant_client import QdrantClient

from app.config import app_settings
from app.evaluation.eval_dataset import EVAL_SET, EVAL_SET_OPS
from app.evaluation.evaluator import RAGEvaluator
from app.rag.pipeline import HybridRAG

DATASETS = {
    "default": EVAL_SET,
    "ops": EVAL_SET_OPS,
    "EVAL_SET": EVAL_SET,
    "EVAL_SET_OPS": EVAL_SET_OPS,
}


def selected_dataset() -> tuple[str, list[dict[str, Any]]]:
    name = os.getenv("EVAL_DATASET", "ops")
    try:
        return name, DATASETS[name]
    except KeyError as error:
        valid = ", ".join(sorted(DATASETS))
        raise ValueError(f"Unknown EVAL_DATASET={name!r}. Valid values: {valid}") from error


def latency_value(result: dict[str, Any], key: str) -> float:
    value = result.get("latency", {}).get(key, 0)
    return float(value or 0)


def print_dry_run(dataset_name: str, dataset: list[dict[str, Any]]) -> None:
    print(f"Eval dry run: dataset={dataset_name}, cases={len(dataset)}")
    print(
        "Eval judge: "
        f"{app_settings.EVAL_LLM_PROVIDER or app_settings.LLM_PROVIDER} / "
        f"{app_settings.EVAL_LLM_MODEL or app_settings.LLM_MODEL}"
    )
    for case in dataset:
        expected = case.get("expected_contains")
        expected_count = len(expected) if isinstance(expected, list) else int(bool(expected))
        print(
            f"- {case['id']}: type={case.get('type', 'n/a')}, "
            f"should_refuse={case['should_refuse']}, expected_items={expected_count}"
        )


def preflight_qdrant() -> None:
    client = QdrantClient(url=app_settings.QDRANT_URL)
    try:
        if not client.collection_exists(app_settings.COLLECTION_NAME):
            raise RuntimeError(
                f"Qdrant collection {app_settings.COLLECTION_NAME!r} does not exist. "
                "Ingest documents before running evals."
            )
        count_result = client.count(
            collection_name=app_settings.COLLECTION_NAME,
            exact=False,
        )
        if count_result.count <= 0:
            raise RuntimeError(
                f"Qdrant collection {app_settings.COLLECTION_NAME!r} has 0 indexed chunks. "
                "Ingest documents before running evals."
            )
        print(
            "Qdrant preflight passed: "
            f"{app_settings.COLLECTION_NAME} has about {count_result.count} chunks."
        )
    except Exception as error:
        raise RuntimeError(
            "Qdrant preflight failed. Make sure the qdrant service is running and "
            f"reachable at {app_settings.QDRANT_URL!r}. "
            "If you use --no-deps, start dependencies first with: "
            "docker compose up -d qdrant redis reranker_service"
        ) from error
    finally:
        close = getattr(client, "close", None)
        if close:
            close()


async def evaluate_with_timer(
    evaluator: RAGEvaluator,
    semaphore: asyncio.Semaphore,
    case: dict[str, Any],
) -> dict[str, Any] | None:
    async with semaphore:
        start_time = time.time()
        try:
            result = await evaluator.evaluate_case(case)
            latency = time.time() - start_time
            print(f"Case '{case['question']}' | execution time: {latency:.2f} seconds")
            return result
        except Exception as exc:
            latency = time.time() - start_time
            print(f"Error in case '{case['question']}': {exc} | time: {latency:.2f} seconds")
            return None


async def main() -> None:
    start_time_global = time.time()
    dataset_name, dataset = selected_dataset()

    if os.getenv("EVAL_DRY_RUN", "").lower() in {"1", "true", "yes"}:
        print_dry_run(dataset_name, dataset)
        return

    rag = HybridRAG()
    preflight_qdrant()
    evaluator = RAGEvaluator(rag)
    semaphore = asyncio.Semaphore(app_settings.RERANKER_CONCURRENCY_LIMIT)

    tasks = [evaluate_with_timer(evaluator, semaphore, case) for case in dataset]
    completed = await asyncio.gather(*tasks, return_exceptions=False)
    results = [result for result in completed if result is not None]

    if not results:
        print("No successful evaluations completed.")
        return

    accuracy = sum(result["passed"] for result in results) / len(results)

    summary = {
        "dataset": dataset_name,
        "avg_accuracy": f"{accuracy:.2%}",
        "avg_latency": {
            "retrieval_time": round(
                sum(latency_value(result, "retrieval") for result in results) / len(results),
                2,
            ),
            "rerank_time": round(
                sum(latency_value(result, "rerank") for result in results) / len(results),
                2,
            ),
            "generation_time": round(
                sum(latency_value(result, "generation") for result in results) / len(results),
                2,
            ),
            "judge_time": round(
                sum(latency_value(result, "judge") for result in results) / len(results),
                2,
            ),
        },
        "total_retrieval_recall": sum(
            1 for result in results if result.get("retrieval_recall", False)
        ),
        "total_answer_contains_expected": sum(
            1 for result in results if result.get("answer_contains_expected", False)
        ),
        "total_passed": sum(1 for result in results if result["passed"]),
        "num_cases_evaluated": len(results),
        "num_cases_failed": len(dataset) - len(results),
    }

    print("\n" + "=" * 50)
    print(
        "EVALUATION SUMMARY "
        f"(dataset = {dataset_name}, max concurrency = {app_settings.RERANKER_CONCURRENCY_LIMIT})"
    )
    print(f"Overall accuracy:       {summary['avg_accuracy']}")
    print(f"Cases evaluated:        {summary['num_cases_evaluated']}/{len(dataset)}")
    print(f"Cases failed:           {summary['num_cases_failed']}")
    print("Average latencies:")
    for key, val in summary["avg_latency"].items():
        print(f"  {key:18}: {val:>5.2f} s")
    print(f"Retrieval recall:       {summary['total_retrieval_recall']}/{len(results)}")
    print(f"Answer contains check:  {summary['total_answer_contains_expected']}/{len(results)}")
    print(f"Total passed:           {summary['total_passed']}/{len(results)}")
    print("=" * 50)

    to_save = {
        "results": results,
        "overall": summary,
        "metadata": {
            "RERANKER_CONCURRENCY_LIMIT": app_settings.RERANKER_CONCURRENCY_LIMIT,
            "eval_llm_provider": evaluator.eval_provider,
            "eval_llm_model": evaluator.eval_model,
            "total_time_seconds": round(time.time() - start_time_global, 2),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
    }
    try:
        with open("eval_results/eval_results_parallel.json", "w") as f:
            json.dump(to_save, f, indent=2)
        print("Results saved to eval_results/eval_results_parallel.json")
    except Exception as e:
        print(f"Failed to save JSON: {e}")

    total_time = time.time() - start_time_global
    print(f"Total execution time (parallel): {total_time:.2f} seconds")


if __name__ == "__main__":
    asyncio.run(main())
