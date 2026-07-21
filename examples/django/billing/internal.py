"""Database internals for the billing app.

Same rule as users/internal.py: direct ORM/SQL access that only
billing/services.py is allowed to call. No view and no other app may
import this module -- see ../architecture.py.
"""

from __future__ import annotations

from django.db import connection

from billing.models import Invoice


def unpaid_invoices_for_user(user_id: int) -> list[Invoice]:
    """Direct queryset with no authorization checks."""
    return list(Invoice.objects.filter(user_id=user_id, is_paid=False))


def raw_outstanding_balance_cents(user_id: int) -> int:
    """Hand-written SQL for a user's outstanding balance."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COALESCE(SUM(amount_cents), 0) FROM billing_invoice "
            "WHERE user_id = %s AND is_paid = 0",
            [user_id],
        )
        row = cursor.fetchone()
        return row[0] if row else 0
