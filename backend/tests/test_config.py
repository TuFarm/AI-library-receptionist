from app.core.config import Settings


def test_railway_postgres_url_uses_installed_psycopg_driver():
    settings = Settings(
        _env_file=None,
        database_url="postgresql://user:password@postgres.railway.internal:5432/railway",
    )

    assert settings.database_url == (
        "postgresql+psycopg://user:password@postgres.railway.internal:5432/railway"
    )


def test_explicit_sqlalchemy_driver_is_preserved():
    url = "postgresql+psycopg://user:password@localhost:5432/ai_library"

    assert Settings(_env_file=None, database_url=url).database_url == url
