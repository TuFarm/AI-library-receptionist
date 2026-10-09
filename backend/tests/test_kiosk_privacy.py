"""Kiosks never receive a student's full email, and phone numbers are not collected."""
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.v1.routes.face import _user_data, mask_email
from app.main import app
from app.models.schema import User, UserSession
from tests.conftest import TEST_DEVICE_ID


@pytest.mark.parametrize("email,masked", [
    ("nguyenvana@st.hcmuaf.edu.vn", "ng***@st.hcmuaf.edu.vn"),
    ("abc@x.vn", "a***@x.vn"),
    ("a@x.vn", "a***@x.vn"),
    (None, None), ("", None), ("not-an-email", None),
])
def test_mask_email(email, masked):
    assert mask_email(email) == masked


def test_kiosk_profile_data_masks_email_and_has_no_phone():
    user = User(full_name="An", email="nguyenvana@st.hcmuaf.edu.vn", admission_year=2024)
    data = _user_data(user)
    assert data["email"] == "ng***@st.hcmuaf.edu.vn"
    assert "nguyenvana" not in str(data) and "phone" not in data


def test_kiosk_profile_edit_returns_masked_email_and_rejects_phone(use_db):
    user = User(full_name="Người A", email="nguyenvana@st.hcmuaf.edu.vn", user_type="STUDENT", account_status="ACTIVE")
    use_db.add(user)
    use_db.flush()
    session = UserSession(device_id=TEST_DEVICE_ID, user_id=user.id, identified=True, started_at=datetime.now(UTC))
    use_db.add(session)
    use_db.commit()
    kiosk = TestClient(app)
    url = f"/api/v1/kiosk/sessions/{session.id}/profile"
    updated = kiosk.patch(url, json={"major": "CNTT"})
    assert updated.status_code == 200
    assert updated.json()["data"]["email"] == "ng***@st.hcmuaf.edu.vn"
    assert kiosk.patch(url, json={"phone": "0901234567"}).status_code == 422
    changed = kiosk.patch(url, json={"email": "moi@st.hcmuaf.edu.vn"})
    assert changed.json()["data"]["email"] == "m***@st.hcmuaf.edu.vn"
    use_db.refresh(user)
    assert user.email == "moi@st.hcmuaf.edu.vn"


def test_sending_back_the_masked_hint_never_overwrites_the_real_email(use_db):
    user = User(full_name="Người A", email="nguyenvana@st.hcmuaf.edu.vn", user_type="STUDENT", account_status="ACTIVE")
    use_db.add(user)
    use_db.flush()
    session = UserSession(device_id=TEST_DEVICE_ID, user_id=user.id, identified=True, started_at=datetime.now(UTC))
    use_db.add(session)
    use_db.commit()
    url = f"/api/v1/kiosk/sessions/{session.id}/profile"
    response = TestClient(app).patch(url, json={"email": "ng***@st.hcmuaf.edu.vn", "major": "CNTT"})
    assert response.status_code == 200
    use_db.refresh(user)
    assert user.email == "nguyenvana@st.hcmuaf.edu.vn" and user.major == "CNTT"
