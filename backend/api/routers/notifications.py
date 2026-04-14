"""Notifications router — monitor trigger + notification retrieval.

Endpoints:
    POST /monitor/run           — Trigger a monitoring cycle manually
    GET  /notifications/{user_id} — Get notifications for a user
    POST /notifications/{notification_id}/read — Mark notification as read
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.agents.persistent_monitor_agent import PersistentMonitorAgent

router = APIRouter()


# -----------------------------------------------------------------------
# Response models
# -----------------------------------------------------------------------

class NotificationOut(BaseModel):
    notification_id: str
    user_id: str
    type: str
    title: str
    body: str
    created_at: str
    read: bool
    action_url: str | None = None


class MonitorRunResponse(BaseModel):
    notifications_generated: int
    notifications: list[NotificationOut]


class NotificationsListResponse(BaseModel):
    user_id: str
    count: int
    unread_count: int
    notifications: list[NotificationOut]


# -----------------------------------------------------------------------
# Singleton monitor (created on first use)
# -----------------------------------------------------------------------

_monitor: PersistentMonitorAgent | None = None


def _get_monitor() -> PersistentMonitorAgent:
    global _monitor
    if _monitor is None:
        _monitor = PersistentMonitorAgent()
    return _monitor


def set_monitor(monitor: PersistentMonitorAgent) -> None:
    """Allow dependency injection for testing."""
    global _monitor
    _monitor = monitor


# -----------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------

@router.post("/monitor/run", response_model=MonitorRunResponse)
async def trigger_monitor():
    """Manually trigger a monitoring cycle (for testing/ops).

    Runs the persistent monitor agent for all pending users and returns
    the list of notifications generated.
    """
    monitor = _get_monitor()
    notifications = await monitor.run_cycle()

    return MonitorRunResponse(
        notifications_generated=len(notifications),
        notifications=[
            NotificationOut(
                notification_id=n.notification_id,
                user_id=n.user_id,
                type=n.type,
                title=n.title,
                body=n.body,
                created_at=n.created_at.isoformat(),
                read=n.read,
                action_url=n.action_url,
            )
            for n in notifications
        ],
    )


@router.get("/notifications/{user_id}", response_model=NotificationsListResponse)
async def get_notifications(user_id: str, unread_only: bool = False):
    """Retrieve notifications for a user.

    Returns list of notifications: score updates, tips, alerts, mission reminders.
    Ordered by most recent first.
    """
    store = _get_monitor().notification_store
    notifications = store.get_for_user(user_id, unread_only=unread_only)

    return NotificationsListResponse(
        user_id=user_id,
        count=len(notifications),
        unread_count=store.count_unread(user_id),
        notifications=[
            NotificationOut(
                notification_id=n.notification_id,
                user_id=n.user_id,
                type=n.type,
                title=n.title,
                body=n.body,
                created_at=n.created_at.isoformat(),
                read=n.read,
                action_url=n.action_url,
            )
            for n in notifications
        ],
    )


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str):
    """Mark a single notification as read."""
    store = _get_monitor().notification_store
    found = store.mark_read(notification_id)
    if not found:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"notification_id": notification_id, "read": True}
