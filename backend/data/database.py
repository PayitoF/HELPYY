"""Database connection — SQLite for local, DynamoDB for production."""

import os


DATABASE_TYPE = os.getenv("DATABASE_TYPE", "sqlite")


class Database:
    """Unified database interface.

    Switches between SQLite (local dev) and DynamoDB (production)
    based on DATABASE_TYPE env var.
    """

    def __init__(self):
        self.db_type = DATABASE_TYPE
        # TODO: initialize SQLite or DynamoDB connection

    async def get_user(self, user_id: str) -> dict | None:
        """Retrieve user state."""
        # TODO: query users table
        pass

    async def save_user(self, user: dict) -> None:
        """Create or update user state."""
        # TODO: upsert into users table
        pass

    async def save_message(self, message: dict) -> None:
        """Store a chat message."""
        # TODO: insert into messages table
        pass

    async def get_messages(self, session_id: str) -> list[dict]:
        """Retrieve chat history for a session."""
        # TODO: query messages by session_id
        pass

    async def save_notification(self, notification: dict) -> None:
        """Store a notification from the monitor agent."""
        # TODO: insert into notifications table
        pass

    async def get_notifications(self, user_id: str) -> list[dict]:
        """Retrieve notifications for a user."""
        # TODO: query notifications by user_id, ordered by date
        pass

    async def save_pii_mapping(self, session_id: str, mapping: dict, ttl_hours: int = 24) -> None:
        """Store PII token mapping in vault with TTL."""
        # TODO: insert with expiration timestamp
        pass

    async def get_pii_mapping(self, session_id: str) -> dict | None:
        """Retrieve PII token mapping for a session."""
        # TODO: query vault, check TTL expiration
        pass
