from app.config import app_settings
from app.rag.reranker_providers.remote_reranker import RemoteReranker


def get_reranker() -> object | None:
    if app_settings.RERANKER_PROVIDER == "fastembed":
        from .fastembed_reranker import FastEmbedReranker  # noqa: PLC0415

        return FastEmbedReranker()
    elif app_settings.RERANKER_PROVIDER == "remote":
        return RemoteReranker()
    else:
        return None
