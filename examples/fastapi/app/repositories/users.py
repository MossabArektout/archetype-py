"""Data access layer: translates domain calls into database queries."""

from app.db.session import get_session


class UserRepository:
    def find_by_id(self, user_id: int) -> dict:
        session = get_session()
        return session.query_one("users", user_id)

    def save(self, data: dict) -> dict:
        session = get_session()
        return session.insert("users", data)
