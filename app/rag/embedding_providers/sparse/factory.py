def get_sparse_provider(provider: str = "fastembed") -> object:
    if provider == "fastembed":
        from .splade_provider import SparseEmbeddingProvider  # noqa: PLC0415

        return SparseEmbeddingProvider()

    raise ValueError(f"Unsupported sparse provider: {provider}")
