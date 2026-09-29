"""Migrations must build exactly the ORM schema on a fresh database (checked offline, no server)."""
import re
from pathlib import Path

from alembic import command
from alembic.config import Config

from app import models  # noqa: F401
from app.core.database import Base

BACKEND = Path(__file__).resolve().parents[1]


def _offline_upgrade_sql(capsys) -> str:
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    capsys.readouterr()
    command.upgrade(config, "head", sql=True)  # offline mode prints the DDL to stdout
    return capsys.readouterr().out


def test_fresh_upgrade_creates_every_model_table_and_column(capsys):
    sql = _offline_upgrade_sql(capsys)
    created = dict(re.findall(r"CREATE TABLE (\w+) \((.*?)\n\);", sql, flags=re.S))
    added = re.findall(r"ALTER TABLE (\w+) ADD COLUMN (\w+)", sql)
    assert set(created) - {"alembic_version"} == set(Base.metadata.tables)
    for table in Base.metadata.sorted_tables:
        columns = set(re.findall(r"^\s+(\w+) ", created[table.name], flags=re.M))
        columns |= {column for name, column in added if name == table.name}
        assert set(table.columns.keys()) <= columns, table.name


def test_initial_revision_is_frozen_and_not_built_from_live_metadata():
    source = (BACKEND / "alembic/versions/20260902_0001_ai_kiosk_schema.py").read_text(encoding="utf-8")
    assert "Base.metadata" not in source
    assert source.count("op.create_table(") == 24
