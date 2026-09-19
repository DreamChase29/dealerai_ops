from dealerai_ops.core.config import Settings


def test_default_settings_do_not_require_secrets() -> None:
    settings = Settings()

    assert settings.app_name == "DealerAI Ops"
    assert settings.environment == "local"
    assert settings.database_url.startswith("sqlite")
