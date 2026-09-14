from app.config import AppSettings


def test_default_reranker_url_matches_compose_service_name() -> None:
    settings = AppSettings(_env_file=None)

    assert settings.APP_NAME == "ChatPDF"
    assert settings.RERANKER_URL == "http://reranker_service:8001"
