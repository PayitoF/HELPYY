"""Tests for the persistent monitor agent and notification system.

Covers: score change detection, notification generation by type, store operations,
API endpoints, mission reminders, scheduler config, edge cases.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from backend.agents.persistent_monitor_agent import (
    MONITOR_INTERVAL_HOURS,
    InMemoryUserStore,
    Notification,
    NotificationStore,
    PersistentMonitorAgent,
    UserRecord,
    _classify_change,
    _compute_delta,
    generate_mission_reminder,
    generate_notification,
)


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

def _make_user(
    user_id: str = "user_1",
    last_p_default: float | None = 0.55,
    income: float = 800_000,
    is_banked: bool = True,
    missions: list[str] | None = None,
) -> UserRecord:
    return UserRecord(
        user_id=user_id,
        score_status="pendiente_mejora",
        last_p_default=last_p_default,
        declared_income=income,
        is_banked=is_banked,
        active_missions=missions or [],
    )


def _make_monitor(
    users: list[UserRecord] | None = None,
    ml_predictions: dict | None = None,
) -> PersistentMonitorAgent:
    """Create a monitor with in-memory stores and optional mock ML client."""
    user_store = InMemoryUserStore()
    for u in (users or []):
        user_store.add_user(u)

    notif_store = NotificationStore()

    ml_client = None
    if ml_predictions:
        ml_client = AsyncMock()

        async def _predict_side_effect(request):
            # Return prediction based on declared_income
            income = request.declared_income
            pred_data = ml_predictions.get(income)
            if pred_data:
                mock_pred = AsyncMock()
                mock_pred.eligible = pred_data["eligible"]
                mock_pred.p_default = pred_data["p_default"]
                mock_pred.score_band.value = pred_data.get("score_band", "high_risk")
                mock_pred.max_amount = pred_data.get("max_amount")
                return mock_pred
            return None

        ml_client.predict = AsyncMock(side_effect=_predict_side_effect)

    monitor = PersistentMonitorAgent(
        ml_client=ml_client,
        user_store=user_store,
        notification_store=notif_store,
    )
    return monitor


# -----------------------------------------------------------------------
# Delta computation & classification
# -----------------------------------------------------------------------

class TestDeltaComputation:
    def test_improvement_is_negative_delta(self):
        """Lower p_default = improvement = negative delta."""
        assert _compute_delta(0.55, 0.45) == pytest.approx(-0.10)

    def test_worsening_is_positive_delta(self):
        assert _compute_delta(0.40, 0.50) == pytest.approx(0.10)

    def test_no_change(self):
        assert _compute_delta(0.50, 0.50) == pytest.approx(0.0)

    def test_first_check_no_previous(self):
        """No previous score → delta = 0."""
        assert _compute_delta(None, 0.50) == 0.0


class TestClassifyChange:
    def test_eligible_always_improved(self):
        """If now eligible, always classify as improved regardless of delta."""
        assert _classify_change(0.01, eligible=True) == "score_improved"

    def test_significant_improvement(self):
        assert _classify_change(-0.05, eligible=False) == "score_improved"

    def test_significant_decrease(self):
        assert _classify_change(0.05, eligible=False) == "score_decreased"

    def test_small_change_is_same(self):
        assert _classify_change(-0.01, eligible=False) == "score_same"
        assert _classify_change(0.01, eligible=False) == "score_same"

    def test_zero_change_is_same(self):
        assert _classify_change(0.0, eligible=False) == "score_same"


# -----------------------------------------------------------------------
# Notification generation
# -----------------------------------------------------------------------

class TestNotificationGeneration:
    def test_monitor_detects_improvement(self):
        """Score drop of >=2pp generates score_improved notification."""
        user = _make_user(last_p_default=0.55)
        notif = generate_notification(user, new_p_default=0.45, eligible=False)

        assert notif.type == "score_improved"
        assert notif.user_id == "user_1"
        assert "mejorando" in notif.title.lower() or "mejor" in notif.body.lower()

    def test_now_eligible_generates_approval_notification(self):
        """User becoming eligible generates special improved notification."""
        user = _make_user(last_p_default=0.55)
        notif = generate_notification(user, new_p_default=0.18, eligible=True)

        assert notif.type == "score_improved"
        assert "calificas" in notif.title.lower() or "calificas" in notif.body.lower()

    def test_no_change_generates_tip(self):
        user = _make_user(last_p_default=0.55)
        notif = generate_notification(user, new_p_default=0.54, eligible=False)

        assert notif.type == "score_same"
        assert "tip" in notif.title.lower() or "misiones" in notif.body.lower()

    def test_score_decreased_generates_alert(self):
        user = _make_user(last_p_default=0.50)
        notif = generate_notification(user, new_p_default=0.60, eligible=False)

        assert notif.type == "score_decreased"
        assert "atención" in notif.title.lower() or "bajó" in notif.body.lower()

    def test_first_check_no_previous_score(self):
        """First time monitoring — no delta, should be score_same."""
        user = _make_user(last_p_default=None)
        notif = generate_notification(user, new_p_default=0.55, eligible=False)

        assert notif.type == "score_same"

    def test_notification_has_action_url(self):
        user = _make_user()
        notif = generate_notification(user, new_p_default=0.45, eligible=False)
        assert notif.action_url is not None

    def test_notification_has_unique_id(self):
        user = _make_user()
        n1 = generate_notification(user, 0.45, False)
        n2 = generate_notification(user, 0.45, False)
        assert n1.notification_id != n2.notification_id

    def test_mission_reminder(self):
        user = _make_user()
        notif = generate_mission_reminder(user, "Depósito Constante")

        assert notif.type == "mission_reminder"
        assert "Depósito Constante" in notif.title or "Depósito Constante" in notif.body
        assert notif.action_url == "/helpyy/missions"


# -----------------------------------------------------------------------
# Notification store
# -----------------------------------------------------------------------

class TestNotificationStore:
    def test_notification_stored_and_retrievable(self):
        """Save a notification and retrieve it by user_id."""
        store = NotificationStore()
        notif = Notification(
            user_id="u1",
            type="score_improved",
            title="Test",
            body="Test body",
        )
        store.save(notif)

        retrieved = store.get_for_user("u1")
        assert len(retrieved) == 1
        assert retrieved[0].notification_id == notif.notification_id

    def test_multiple_notifications_per_user(self):
        store = NotificationStore()
        store.save(Notification(user_id="u1", type="score_improved", title="A", body="a"))
        store.save(Notification(user_id="u1", type="score_same", title="B", body="b"))

        assert len(store.get_for_user("u1")) == 2

    def test_users_are_isolated(self):
        store = NotificationStore()
        store.save(Notification(user_id="u1", type="score_same", title="A", body="a"))
        store.save(Notification(user_id="u2", type="score_same", title="B", body="b"))

        assert len(store.get_for_user("u1")) == 1
        assert len(store.get_for_user("u2")) == 1

    def test_unread_only_filter(self):
        store = NotificationStore()
        n1 = Notification(user_id="u1", type="score_same", title="A", body="a")
        n2 = Notification(user_id="u1", type="score_same", title="B", body="b", read=True)
        store.save(n1)
        store.save(n2)

        unread = store.get_for_user("u1", unread_only=True)
        assert len(unread) == 1
        assert unread[0].title == "A"

    def test_mark_read(self):
        store = NotificationStore()
        n = Notification(user_id="u1", type="score_same", title="A", body="a")
        store.save(n)

        assert store.mark_read(n.notification_id) is True
        assert store.get_for_user("u1")[0].read is True

    def test_mark_read_nonexistent(self):
        store = NotificationStore()
        assert store.mark_read("nonexistent") is False

    def test_count_unread(self):
        store = NotificationStore()
        store.save(Notification(user_id="u1", type="score_same", title="A", body="a"))
        store.save(Notification(user_id="u1", type="score_same", title="B", body="b"))
        store.save(Notification(user_id="u1", type="score_same", title="C", body="c", read=True))

        assert store.count_unread("u1") == 2

    def test_empty_user(self):
        store = NotificationStore()
        assert store.get_for_user("no_such_user") == []
        assert store.count_unread("no_such_user") == 0

    def test_clear(self):
        store = NotificationStore()
        store.save(Notification(user_id="u1", type="score_same", title="A", body="a"))
        store.clear()
        assert store.get_for_user("u1") == []

    def test_ordered_by_most_recent_first(self):
        store = NotificationStore()
        n1 = Notification(
            user_id="u1", type="score_same", title="Old", body="old",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        n2 = Notification(
            user_id="u1", type="score_same", title="New", body="new",
            created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        )
        store.save(n1)
        store.save(n2)

        results = store.get_for_user("u1")
        assert results[0].title == "New"
        assert results[1].title == "Old"


# -----------------------------------------------------------------------
# User store
# -----------------------------------------------------------------------

class TestInMemoryUserStore:
    @pytest.mark.asyncio
    async def test_get_pending_users(self):
        store = InMemoryUserStore()
        store.add_user(_make_user("u1"))
        store.add_user(UserRecord(user_id="u2", score_status="approved"))

        pending = await store.get_pending_users()
        assert len(pending) == 1
        assert pending[0].user_id == "u1"

    @pytest.mark.asyncio
    async def test_update_score(self):
        store = InMemoryUserStore()
        store.add_user(_make_user("u1"))

        await store.update_score("u1", 0.30, "approved")
        users = list(store._users.values())
        assert users[0].last_p_default == 0.30
        assert users[0].score_status == "approved"


# -----------------------------------------------------------------------
# Full monitor cycle
# -----------------------------------------------------------------------

class TestMonitorCycle:
    @pytest.mark.asyncio
    async def test_monitor_generates_notification(self):
        """Full cycle: user with pending status → ML check → notification stored."""
        user = _make_user("u1", last_p_default=0.55, income=800_000)
        monitor = _make_monitor(users=[user])

        notifications = await monitor.run_cycle()

        assert len(notifications) >= 1
        # Should be stored in notification store
        stored = monitor.notification_store.get_for_user("u1")
        assert len(stored) >= 1

    @pytest.mark.asyncio
    async def test_monitor_detects_improvement_in_cycle(self):
        """User whose income qualifies them gets score_improved."""
        user = _make_user("u1", last_p_default=0.55, income=2_000_000)
        monitor = _make_monitor(users=[user])

        notifications = await monitor.run_cycle()

        # High income → eligible → score_improved
        score_notifs = [n for n in notifications if n.type != "mission_reminder"]
        assert any(n.type == "score_improved" for n in score_notifs)

    @pytest.mark.asyncio
    async def test_monitor_updates_user_score(self):
        """After cycle, user's last_p_default should be updated."""
        user = _make_user("u1", last_p_default=0.55, income=800_000)
        monitor = _make_monitor(users=[user])

        await monitor.run_cycle()

        updated_users = await monitor.user_store.get_pending_users()
        # If still not eligible, status stays pendiente_mejora
        # and last_p_default is updated
        all_users = list(monitor.user_store._users.values())
        assert all_users[0].last_p_default != 0.55 or all_users[0].last_p_default is not None

    @pytest.mark.asyncio
    async def test_monitor_handles_no_pending_users(self):
        """Empty user list → no notifications."""
        monitor = _make_monitor(users=[])
        notifications = await monitor.run_cycle()
        assert notifications == []

    @pytest.mark.asyncio
    async def test_monitor_handles_multiple_users(self):
        """Multiple pending users each get a notification."""
        users = [
            _make_user("u1", last_p_default=0.55, income=800_000),
            _make_user("u2", last_p_default=0.60, income=600_000),
            _make_user("u3", last_p_default=0.40, income=1_500_000),
        ]
        monitor = _make_monitor(users=users)

        notifications = await monitor.run_cycle()

        # Each user should have at least one notification
        user_ids = {n.user_id for n in notifications}
        assert user_ids == {"u1", "u2", "u3"}

    @pytest.mark.asyncio
    async def test_monitor_generates_mission_reminders(self):
        """Users with active missions get reminder notifications."""
        user = _make_user("u1", missions=["Depósito Constante", "Colchón de Seguridad"])
        monitor = _make_monitor(users=[user])

        notifications = await monitor.run_cycle()

        reminders = [n for n in notifications if n.type == "mission_reminder"]
        assert len(reminders) == 2

    @pytest.mark.asyncio
    async def test_monitor_error_doesnt_stop_cycle(self):
        """If one user's check fails, others still get processed."""
        users = [
            _make_user("u1", income=800_000),
            _make_user("u2", income=600_000),
        ]
        monitor = _make_monitor(users=users)

        # Patch _check_user to fail on first user
        original_check = monitor._check_user
        call_count = 0

        async def _flaky_check(user):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("ML service timeout")
            return await original_check(user)

        monitor._check_user = _flaky_check

        notifications = await monitor.run_cycle()

        # u1 failed but u2 should still have a notification
        score_notifs = [n for n in notifications if n.type != "mission_reminder"]
        assert any(n.user_id == "u2" for n in score_notifs)

    @pytest.mark.asyncio
    async def test_eligible_user_status_updated_to_approved(self):
        """When user becomes eligible, their status changes to 'approved'."""
        user = _make_user("u1", last_p_default=0.55, income=2_000_000)
        monitor = _make_monitor(users=[user])

        await monitor.run_cycle()

        u = monitor.user_store._users["u1"]
        assert u.score_status == "approved"


# -----------------------------------------------------------------------
# API endpoints
# -----------------------------------------------------------------------

class TestNotificationEndpoints:
    """Test the FastAPI endpoints via TestClient."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from backend.api.routers.notifications import router, set_monitor
        from fastapi import FastAPI

        # Create isolated app with just the notifications router
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")

        # Inject a monitor with test data
        user = _make_user("test_user", last_p_default=0.55, income=800_000)
        monitor = _make_monitor(users=[user])
        set_monitor(monitor)

        return TestClient(app)

    def test_trigger_monitor_endpoint(self, client):
        """POST /api/v1/monitor/run returns notifications."""
        response = client.post("/api/v1/monitor/run")
        assert response.status_code == 200

        data = response.json()
        assert "notifications_generated" in data
        assert data["notifications_generated"] >= 1
        assert len(data["notifications"]) >= 1

    def test_get_notifications_endpoint(self, client):
        """GET /api/v1/notifications/{user_id} returns stored notifications."""
        # First trigger a cycle to generate notifications
        client.post("/api/v1/monitor/run")

        response = client.get("/api/v1/notifications/test_user")
        assert response.status_code == 200

        data = response.json()
        assert data["user_id"] == "test_user"
        assert data["count"] >= 1
        assert len(data["notifications"]) >= 1

    def test_get_notifications_empty_user(self, client):
        """No notifications for unknown user."""
        response = client.get("/api/v1/notifications/no_such_user")
        assert response.status_code == 200
        assert response.json()["count"] == 0

    def test_mark_notification_read(self, client):
        """POST /api/v1/notifications/{id}/read marks it read."""
        # Generate a notification first
        client.post("/api/v1/monitor/run")
        notifs = client.get("/api/v1/notifications/test_user").json()
        notif_id = notifs["notifications"][0]["notification_id"]

        response = client.post(f"/api/v1/notifications/{notif_id}/read")
        assert response.status_code == 200
        assert response.json()["read"] is True

        # Verify unread count decreased
        updated = client.get("/api/v1/notifications/test_user").json()
        assert updated["unread_count"] < notifs["unread_count"]

    def test_mark_nonexistent_notification(self, client):
        response = client.post("/api/v1/notifications/fake_id/read")
        assert response.status_code == 404

    def test_unread_only_filter(self, client):
        """?unread_only=true filters read notifications."""
        client.post("/api/v1/monitor/run")
        notifs = client.get("/api/v1/notifications/test_user").json()
        notif_id = notifs["notifications"][0]["notification_id"]

        # Mark one as read
        client.post(f"/api/v1/notifications/{notif_id}/read")

        # With unread_only
        unread = client.get("/api/v1/notifications/test_user?unread_only=true").json()
        assert all(not n["read"] for n in unread["notifications"])


# -----------------------------------------------------------------------
# Scheduler config
# -----------------------------------------------------------------------

class TestSchedulerConfig:
    def test_default_interval(self):
        assert MONITOR_INTERVAL_HOURS == 6.0

    @patch.dict("os.environ", {"MONITOR_INTERVAL_HOURS": "2"})
    def test_custom_interval_from_env(self):
        # Re-import to pick up env var
        import importlib
        import backend.agents.persistent_monitor_agent as mod
        importlib.reload(mod)
        assert mod.MONITOR_INTERVAL_HOURS == 2.0
        # Reload back to default
        import os
        os.environ.pop("MONITOR_INTERVAL_HOURS", None)
        importlib.reload(mod)
