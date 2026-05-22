import ast
import json
import re
import textwrap
import time
import uuid
from typing import Any

import structlog

from app.config import app_settings, get_llm

logger = structlog.get_logger()

FAITHFULNESS_WEIGHT = 0.5
ANSWER_RELEVANCE_WEIGHT = 0.3
CONTEXT_RELEVANCE_WEIGHT = 0.2
PASSING_SCORE = 0.8


def _expected_values(expected_contains: str | list[str] | None) -> list[str]:
    if not expected_contains:
        return []
    values = [expected_contains] if isinstance(expected_contains, str) else expected_contains
    return [value for value in values if value.strip()]


class RAGEvaluator:
    def __init__(self, rag_pipeline: object) -> None:
        self.rag = rag_pipeline
        self.eval_provider = app_settings.EVAL_LLM_PROVIDER or app_settings.LLM_PROVIDER
        self.eval_model = app_settings.EVAL_LLM_MODEL or app_settings.LLM_MODEL
        self.llm = get_llm(
            provider=self.eval_provider,
            model=self.eval_model,
        )

    @staticmethod
    def normalize(text: str) -> str:
        text = text.lower()
        return re.sub(r"\s+", "", text)

    def expected_contains_recall(
        self,
        text: str,
        expected_contains: str | list[str] | None,
    ) -> bool:
        if not expected_contains:
            return True

        expected_values = _expected_values(expected_contains)
        if not expected_values:
            return True

        text_norm = self.normalize(text)
        return all(self.normalize(expected) in text_norm for expected in expected_values)

    @staticmethod
    def parse_llm_json_response(response_content: str) -> dict | None:
        cleaned_content = response_content.replace("```json", "").replace("```", "").strip()
        match = re.search(r"\{[\s\S]*\}", cleaned_content)

        if not match:
            print("No JSON object found in the response.")
            return None

        json_string = match.group(0)
        json_string = (
            json_string.replace(": True", ": true")
            .replace(": False", ": false")
            .replace(": None", ": null")
        )

        try:
            return json.loads(json_string)
        except json.JSONDecodeError:
            try:
                return ast.literal_eval(json_string)
            except (ValueError, SyntaxError):
                print("Error decoding JSON/Python dict from response.")
                return None

    def retrieval_recall(
        self,
        retrieved_nodes: list[Any],
        expected_contains: str | list[str] | None,
    ) -> bool:
        if not expected_contains:
            return True

        retrieved_text = "\n\n".join(node.node.text for node in retrieved_nodes)
        return self.expected_contains_recall(retrieved_text, expected_contains)

    async def llm_as_judge(
        self,
        question: str,
        answer: str,
        retrieved_nodes: list[Any],
        should_refuse: bool = False,
    ) -> dict | None:
        context = "\n\n".join(
            node.node.text for node in retrieved_nodes[: app_settings.FINAL_CONTEXT_N]
        )
        refusal_instruction = (
            "The expected behavior is refusal when the context does not support an answer."
            if should_refuse
            else "The expected behavior is answering only when the context supports it."
        )
        prompt = textwrap.dedent(
            f"""
            You are an expert AI auditor for retrieval-augmented generation systems.
            Judge whether the generated answer is correct and grounded only in the context.

            Evaluation criteria:
            1. Faithfulness: all claims in the answer are supported by the context.
            2. Answer relevance: the answer addresses the user's intent.
            3. Context relevance: the retrieved context is necessary and sufficient.
            4. Refusal handling: {refusal_instruction}

            Return ONLY a JSON object with this schema:
            {{
                "reasoning": "A concise explanation of your judgment.",
                "faithfulness": float,
                "answer_relevance": float,
                "context_relevance": float,
                "passed": boolean
            }}

            Query: {question}
            Context: {context}
            Generated Answer: {answer}
            """
        )

        response = await self.llm.acomplete(prompt)
        return self.parse_llm_json_response(response.text)

    async def evaluate_case(self, case: dict[str, Any]) -> dict[str, Any]:
        try:
            trace_id = str(uuid.uuid4())
            result = await self.rag.query(
                case["question"],
                trace_id,
                cache=False,
                return_metadata=True,
            )

            answer = result["answer"]
            retrieved_nodes = (
                result["reranked_nodes"]
                if app_settings.USE_RERANKER and result["reranked_nodes"]
                else result["retrieved_nodes"]
            )
            retrieval_required = not case["should_refuse"]

            retrieval = self.retrieval_recall(
                retrieved_nodes,
                case.get("expected_contains"),
            )
            answer_contains_expected = self.expected_contains_recall(
                answer,
                case.get("expected_contains"),
            )

            if retrieval_required and not retrieved_nodes:
                return {
                    "id": case["id"],
                    "question": case["question"],
                    "answer": answer,
                    "retrieval_recall": False,
                    "answer_contains_expected": answer_contains_expected,
                    "latency": {
                        **result["latency"],
                        "judge": 0,
                    },
                    "eval": {
                        "reasoning": "Answerable case retrieved 0 chunks; judge skipped.",
                        "faithfulness": 0,
                        "answer_relevance": 0,
                        "context_relevance": 0,
                        "passed": False,
                    },
                    "score": 0,
                    "passed": False,
                }

            start = time.time()
            judge_result = await self.llm_as_judge(
                case["question"],
                answer,
                retrieved_nodes,
                case["should_refuse"],
            )
            judge_time = time.time() - start

            score = 0
            passed = False

            try:
                score = (
                    judge_result["faithfulness"] * FAITHFULNESS_WEIGHT
                    + judge_result["answer_relevance"] * ANSWER_RELEVANCE_WEIGHT
                    + judge_result["context_relevance"] * CONTEXT_RELEVANCE_WEIGHT
                )
                passed = (
                    judge_result["passed"]
                    and score >= PASSING_SCORE
                    # and (not retrieval_required or retrieval)
                    # and (case["should_refuse"] or answer_contains_expected)
                )
            except Exception as error:
                logger.error(
                    "failed_eval_passed_calculation",
                    error=error,
                    question=case["question"],
                )

            return {
                "id": case["id"],
                "question": case["question"],
                "answer": answer,
                "retrieval_recall": retrieval,
                "answer_contains_expected": answer_contains_expected,
                "latency": {
                    **result["latency"],
                    "judge": round(judge_time, 2),
                },
                "eval": judge_result,
                "score": score,
                "passed": passed,
            }

        except Exception as error:
            logger.error("failed_eval", error=error, question=case["question"])
            raise error
