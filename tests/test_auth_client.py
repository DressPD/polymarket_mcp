from __future__ import annotations

from datetime import datetime, timedelta, timezone

from polymarket_mcp.auth.client import CachedCredentials, PolymarketAuthClient

from ._helpers import make_settings


def test_cached_credentials_validity_rules() -> None:
    now = datetime.now(timezone.utc)
    no_expiry = CachedCredentials("k", "s", "p", created_at=now, expires_at=None)
    future_expiry = CachedCredentials("k", "s", "p", created_at=now, expires_at=now + timedelta(minutes=5))
    past_expiry = CachedCredentials("k", "s", "p", created_at=now, expires_at=now - timedelta(minutes=5))

    assert no_expiry.is_valid() is True
    assert future_expiry.is_valid() is True
    assert past_expiry.is_valid() is False


def test_get_or_create_api_credentials_none_without_env_values() -> None:
    client = PolymarketAuthClient(make_settings(poly_api_key=None, poly_api_secret=None, poly_api_passphrase=None))

    assert client.get_or_create_api_credentials() is None


def test_get_or_create_api_credentials_is_cached() -> None:
    client = PolymarketAuthClient(make_settings(poly_api_key="key", poly_api_secret="secret", poly_api_passphrase="pass"))

    first = client.get_or_create_api_credentials()
    second = client.get_or_create_api_credentials()

    assert first is not None
    assert second is first


def test_save_credentials_to_env_file_behaviors(tmp_path) -> None:
    no_creds = PolymarketAuthClient(make_settings(poly_api_key=None, poly_api_secret=None, poly_api_passphrase=None))
    assert no_creds.save_credentials_to_env_file(path=str(tmp_path / "missing.env")) is False

    path = tmp_path / ".env"
    path.write_text("BOT_DRY_RUN=true\n", encoding="utf-8")

    with_creds = PolymarketAuthClient(make_settings(poly_api_key="key", poly_api_secret="secret", poly_api_passphrase="pass"))
    assert with_creds.save_credentials_to_env_file(path=str(path)) is True

    content = path.read_text(encoding="utf-8")
    assert "POLYMARKET_API_KEY=key" in content
    assert "POLYMARKET_API_SECRET=secret" in content
    assert "POLYMARKET_API_PASSPHRASE=pass" in content

    before = content
    assert with_creds.save_credentials_to_env_file(path=str(path)) is True
    assert path.read_text(encoding="utf-8") == before
