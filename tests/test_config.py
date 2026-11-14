import pytest
from pydantic import ValidationError

from app.core.config import Settings

VALID = {
    'database_uri': 'sqlite+aiosqlite://',
    'jwt_secret': 'a' * 32,
    'access_token_expires_minutes': 15,
    'refresh_token_expire_days': 7,
}


def settings(**overrides):
    # _env_file=None so a developer's real .env can't leak into the test
    return Settings(_env_file=None, **{**VALID, **overrides})


@pytest.mark.parametrize('secret', ['', 'short', 'a' * 31])
def test_short_jwt_secret_is_rejected(secret):
    with pytest.raises(ValidationError, match='JWT_SECRET'):
        settings(jwt_secret=secret)


def test_jwt_secret_of_minimum_length_is_accepted():
    assert settings(jwt_secret='a' * 32).jwt_secret == 'a' * 32


def test_sql_echo_is_off_by_default():
    assert settings().sql_echo is False


def test_unknown_env_file_keys_are_ignored(tmp_path):
    # .env is shared with docker compose, which adds keys the app doesn't read
    env = tmp_path / '.env'
    env.write_text(
        'DATABASE_URI=sqlite+aiosqlite://\n'
        f'JWT_SECRET={"a" * 32}\n'
        'ACCESS_TOKEN_EXPIRES_MINUTES=15\n'
        'REFRESH_TOKEN_EXPIRE_DAYS=7\n'
        'GRAFANA_ADMIN_PASSWORD=whatever\n'
    )
    assert Settings(_env_file=env).refresh_token_expire_days == 7
