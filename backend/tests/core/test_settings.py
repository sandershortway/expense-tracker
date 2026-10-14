import pytest

from findash.core.settings import Settings, get_settings


def test_default_investments_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FINDASH_INVESTMENTS_DATABASE_URL", raising=False)

    assert get_settings().investments_database_url == (
        "sqlite:///.data/investments.db"
    )


def test_environment_variable_overrides_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "FINDASH_INVESTMENTS_DATABASE_URL", "sqlite:///elsewhere.db"
    )

    assert get_settings().investments_database_url == (
        "sqlite:///elsewhere.db"
    )


def test_settings_accept_explicit_values() -> None:
    settings = Settings(investments_database_url="sqlite:///explicit.db")

    assert settings.investments_database_url == "sqlite:///explicit.db"
