"""
Auth & authorisation test suite — 20+ cases.
Run: pytest tests/ -v
"""
import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Signup
# ---------------------------------------------------------------------------

async def test_signup_success(client):
    r = await client.post("/auth/signup", json={"email": "a@example.com", "password": "Password1"})
    assert r.status_code == 201
    data = r.json()
    assert data["email"] == "a@example.com"
    assert "id" in data
    assert "created_at" in data
    assert "password_hash" not in data


async def test_signup_duplicate_email(client):
    payload = {"email": "dup@example.com", "password": "Password1"}
    await client.post("/auth/signup", json=payload)
    r = await client.post("/auth/signup", json=payload)
    assert r.status_code == 409


async def test_signup_invalid_email(client):
    r = await client.post("/auth/signup", json={"email": "not-an-email", "password": "Password1"})
    assert r.status_code == 422


async def test_signup_weak_password_too_short(client):
    r = await client.post("/auth/signup", json={"email": "b@example.com", "password": "Ab1"})
    assert r.status_code == 422


async def test_signup_weak_password_no_digit(client):
    r = await client.post("/auth/signup", json={"email": "c@example.com", "password": "PasswordOnly"})
    assert r.status_code == 422


async def test_signup_weak_password_no_uppercase(client):
    r = await client.post("/auth/signup", json={"email": "d@example.com", "password": "password1"})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

async def test_login_success(client):
    await client.post("/auth/signup", json={"email": "e@example.com", "password": "Password1"})
    r = await client.post("/auth/login", json={"email": "e@example.com", "password": "Password1"})
    assert r.status_code == 200
    assert r.json()["email"] == "e@example.com"
    assert "token" in r.cookies


async def test_login_wrong_password(client):
    await client.post("/auth/signup", json={"email": "f@example.com", "password": "Password1"})
    r = await client.post("/auth/login", json={"email": "f@example.com", "password": "WrongPass1"})
    assert r.status_code == 401


async def test_login_unknown_user(client):
    r = await client.post("/auth/login", json={"email": "nobody@example.com", "password": "Password1"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# /auth/me
# ---------------------------------------------------------------------------

async def test_me_authenticated(authed_client):
    r = await authed_client.get("/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == "user@example.com"


async def test_me_unauthenticated(client):
    r = await client.get("/auth/me")
    assert r.status_code == 401


async def test_me_invalid_token(client):
    client.cookies.set("token", "not.a.valid.jwt")
    r = await client.get("/auth/me")
    assert r.status_code == 401


async def test_me_expired_token(client):
    import time
    import jwt as pyjwt
    expired = pyjwt.encode(
        {"sub": "some-id", "exp": int(time.time()) - 3600},
        "test-secret-for-tests-only",
        algorithm="HS256",
    )
    client.cookies.set("token", expired)
    r = await client.get("/auth/me")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

async def test_logout(authed_client):
    r = await authed_client.post("/auth/logout")
    assert r.status_code == 200
    # Cookie cleared — subsequent /me should 401
    r2 = await authed_client.get("/auth/me")
    assert r2.status_code == 401


# ---------------------------------------------------------------------------
# /token (LiveKit) — requires auth
# ---------------------------------------------------------------------------

async def test_token_unauthenticated(client):
    r = await client.get("/token")
    assert r.status_code == 401


async def test_token_authenticated(authed_client):
    r = await authed_client.get("/token")
    assert r.status_code == 200
    assert "token" in r.json()
    assert "url" in r.json()


# ---------------------------------------------------------------------------
# /appointments — own access only
# ---------------------------------------------------------------------------

async def test_appointments_unauthenticated(client):
    r = await client.get("/appointments")
    assert r.status_code == 401


async def test_appointments_empty(authed_client):
    r = await authed_client.get("/appointments")
    assert r.status_code == 200
    assert r.json() == []


async def test_appointments_other_user_isolation(authed_client, other_client):
    """Appointments created by user A must not appear for user B."""
    # Directly insert appointment via DB for authed user
    me_r = await authed_client.get("/auth/me")
    user_id = me_r.json()["id"]

    from tests.conftest import TestingSession
    from models import Appointment
    import uuid

    db = TestingSession()
    appt = Appointment(
        id=str(uuid.uuid4()),
        user_id=user_id,
        caller_name="Test User",
        caller_phone="555-0000",
        slot="2025-09-01 09:00",
        appointment_type="follow_up",
        label="Follow-Up Visit",
        duration_min=30,
        price=75,
    )
    db.add(appt)
    db.commit()
    db.close()

    r = await other_client.get("/appointments")
    assert r.status_code == 200
    assert r.json() == []

    r2 = await authed_client.get("/appointments")
    assert r2.status_code == 200
    assert len(r2.json()) == 1


# ---------------------------------------------------------------------------
# Tool-level authorisation (cancel_appointment)
# ---------------------------------------------------------------------------

async def test_cancel_own_appointment(authed_client):
    me_r = await authed_client.get("/auth/me")
    user_id = me_r.json()["id"]

    from tests.conftest import TestingSession
    from models import Appointment
    import uuid

    appt_id = str(uuid.uuid4())
    db = TestingSession()
    appt = Appointment(
        id=appt_id,
        user_id=user_id,
        caller_name="Test User",
        caller_phone="555-0001",
        slot="2025-09-02 10:00",
        appointment_type="follow_up",
        label="Follow-Up Visit",
        duration_min=30,
        price=75,
    )
    db.add(appt)
    db.commit()
    db.close()

    from tools import make_cancel_appointment
    db2 = TestingSession()
    cancel = make_cancel_appointment(user_id, db2)
    result = await cancel(appt_id[:8].upper())
    db2.close()
    assert "cancelled" in result.lower()


async def test_cancel_other_users_appointment(authed_client, other_client):
    """User A cannot cancel user B's appointment."""
    other_r = await other_client.get("/auth/me")
    other_id = other_r.json()["id"]

    from tests.conftest import TestingSession
    from models import Appointment
    import uuid

    appt_id = str(uuid.uuid4())
    db = TestingSession()
    appt = Appointment(
        id=appt_id,
        user_id=other_id,
        caller_name="Other User",
        caller_phone="555-0002",
        slot="2025-09-03 11:00",
        appointment_type="follow_up",
        label="Follow-Up Visit",
        duration_min=30,
        price=75,
    )
    db.add(appt)
    db.commit()
    db.close()

    me_r = await authed_client.get("/auth/me")
    my_id = me_r.json()["id"]

    from tools import make_cancel_appointment
    db2 = TestingSession()
    cancel = make_cancel_appointment(my_id, db2)
    result = await cancel(appt_id[:8].upper())
    db2.close()
    assert "not authorised" in result.lower()
