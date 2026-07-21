"""Public interface for the users app.

Views (users/views.py) and other apps (e.g. billing) call functions here
instead of touching users/internal.py or the ORM directly. This is the
layer that owns validation, permissions, and business rules -- and it's the
only layer allowed to import users/internal.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from users import internal
from users.models import User


@dataclass
class UserProfile:
    """A read-only view of a user, safe to hand to other apps."""

    id: int
    email: str
    full_name: str
    is_active: bool


def get_user_profile(email: str) -> UserProfile | None:
    """Look up a user and return the public-safe representation."""
    user = internal.fetch_user_row_by_email(email)
    if user is None:
        return None
    return UserProfile(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
    )


def active_user_count() -> int:
    """Expose the active-user count without leaking how it's computed."""
    return internal.raw_active_user_count()


def register_user(email: str, full_name: str) -> UserProfile:
    """Create a new user account."""
    user = User.objects.create(email=email, full_name=full_name)
    return UserProfile(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
    )
