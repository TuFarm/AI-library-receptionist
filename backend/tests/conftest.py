from types import SimpleNamespace
from uuid import UUID

import pytest

from app.api.deps import require_kiosk_device
from app.core.config import settings
from app.main import app

TEST_DEVICE_ID = UUID("0d0d0d0d-0000-4000-8000-000000000001")
TEST_DEVICE = SimpleNamespace(id=TEST_DEVICE_ID, device_code="KIOSK_TEST", status="active", deleted_at=None)


@pytest.fixture(autouse=True)
def fast_password_hashing(monkeypatch):
    """Production uses 600k PBKDF2 rounds; tests only need the format and behaviour."""
    monkeypatch.setattr(settings, "staff_password_iterations", 1_000)


@pytest.fixture(autouse=True)
def trusted_kiosk_device():
    """Most API tests exercise business rules, not device auth: act as one registered kiosk.

    Device-auth tests remove this override explicitly (see test_access_control.py).
    """
    previous = app.dependency_overrides.get(require_kiosk_device)
    app.dependency_overrides[require_kiosk_device] = lambda: TEST_DEVICE
    yield TEST_DEVICE
    if previous is None:
        app.dependency_overrides.pop(require_kiosk_device, None)
    else:
        app.dependency_overrides[require_kiosk_device] = previous


@pytest.fixture
def admin_staff():
    """Act as a signed-in admin for endpoints whose auth is not what the test is about."""
    from app.api.deps import get_current_staff
    from app.services.staff_auth_service import StaffIdentity

    identity = StaffIdentity(UUID("0d0d0d0d-0000-4000-8000-0000000000aa"), "test-admin", "Test Admin", "admin", 4_102_444_800)
    app.dependency_overrides[get_current_staff] = lambda: identity
    yield identity
    app.dependency_overrides.pop(get_current_staff, None)


@pytest.fixture
def sqlite_db():
    """In-memory SQL database with every table SQLite can represent (not the JSONB ones)."""
    from sqlalchemy import create_engine
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    from app import models  # noqa: F401
    from app.core.database import Base

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[
        table for table in Base.metadata.sorted_tables
        if not any(isinstance(column.type, JSONB) for column in table.columns)
    ])
    with Session(engine) as db:
        yield db
    engine.dispose()


@pytest.fixture
def use_db(sqlite_db):
    """Route the app's `get_db` dependency to `sqlite_db`."""
    from app.core.database import get_db

    app.dependency_overrides[get_db] = lambda: sqlite_db
    yield sqlite_db
    app.dependency_overrides.pop(get_db, None)
