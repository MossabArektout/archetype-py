"""Database internals for the users app.

Everything in this module talks to the ORM or the database directly and
skips the guardrails services.py provides (validation, permissions, side
effects). Two rules in ../architecture.py protect it:

  - No view, in any app, may import *.internal directly.
  - No app other than users may import users.internal at all.

services.py is the only code meant to call into this module.
"""

from __future__ import annotations

from django.db import connection

from users.models import User


def fetch_user_row_by_email(email: str) -> User | None:
    """Direct ORM lookup with no permission or validation checks."""
    return User.objects.filter(email=email).first()


def raw_active_user_count() -> int:
    """Hand-written SQL that bypasses the ORM entirely."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM users_user WHERE is_active = %s", [True])
        row = cursor.fetchone()
        return row[0] if row else 0
