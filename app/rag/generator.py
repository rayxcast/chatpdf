import structlog
import yaml
from llama_index.core import PromptTemplate, Settings

from app.config import configure_llm_settings

logger = structlog.get_logger()

# Load prompts
with open("app/rag/prompts.yaml") as f:
    prompts = yaml.safe_load(f)
qa_prompt = PromptTemplate(prompts["v2"]["qa"])


def _source_label(metadata: dict) -> str:
    document_name = (
        metadata.get("document_name")
        or metadata.get("file_name")
        or metadata.get("filename")
    )
    collection_name = metadata.get("collection_name")
    page = metadata.get("page_number") or metadata.get("page_label") or metadata.get("page")
    section = metadata.get("section_name")
    chunk_id = metadata.get("chunk_id")

    parts = []
    if document_name:
        parts.append(f"Document: {document_name}")
    if collection_name:
        parts.append(f"Collection: {collection_name}")
    if page:
        parts.append(f"Page: {page}")
    elif section:
        parts.append(f"Section: {section}")
    if chunk_id:
        parts.append(f"Chunk: {chunk_id}")
    return " | ".join(parts) if parts else "Source metadata unavailable"


def _context_from_nodes(final_nodes: list) -> str:
    chunks = []
    for index, node_with_score in enumerate(final_nodes, start=1):
        node = node_with_score.node
        metadata = node.metadata or {}
        chunks.append(
            "\n".join(
                [
                    f"[Source {index}] {_source_label(metadata)}",
                    node.text,
                ]
            )
        )
    return "\n\n".join(chunks)


class LLMGenerator:
    def __init__(self) -> None:
        configure_llm_settings()
        # Grab the model from the global settings once.
        self.llm = Settings.llm

    async def generate(self, query: str, final_nodes: list) -> dict:
        try:
            if not final_nodes:
                answer = "The answer is not present in the provided documents."
                sources = []
            else:
                context_str = _context_from_nodes(final_nodes)
                prompt = qa_prompt.format(context_str=context_str, query_str=query)
                response = await self.llm.acomplete(prompt)
                answer = response.text
                sources = [n.node.metadata for n in final_nodes]

        except Exception as e:
            logger.error("retrieval_failed", error=str(e), exc_info=True)
            answer = "The answer is not present in the provided documents."
            sources = []

        return {"answer": answer, "sources": sources}
