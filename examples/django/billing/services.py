"""Public interface for the billing app.

To act on a user, billing goes through users.services -- the users app's
public API -- and never through users.internal. That cross-app boundary is
enforced by ../architecture.py: billing has no special exemption, so if
this file imported users.internal instead, `archetype check` would fail.
"""

from __future__ import annotations

from dataclasses import dataclass

from billing import internal
from billing.models import Invoice
from users import services as users_services


@dataclass
class BillingSummary:
    """A user's billing status, assembled from billing + users data."""

    user_email: str
    outstanding_cents: int
    unpaid_invoice_count: int


def get_billing_summary(user_email: str) -> BillingSummary | None:
    """Look up a user's billing summary.

    Needs the user's identity, so it calls users_services.get_user_profile
    -- the sanctioned entry point -- rather than reaching into
    users.internal to fetch the row itself.
    """
    profile = users_services.get_user_profile(user_email)
    if profile is None:
        return None
    unpaid = internal.unpaid_invoices_for_user(profile.id)
    outstanding = internal.raw_outstanding_balance_cents(profile.id)
    return BillingSummary(
        user_email=profile.email,
        outstanding_cents=outstanding,
        unpaid_invoice_count=len(unpaid),
    )


def issue_invoice(user_email: str, amount_cents: int) -> Invoice | None:
    """Create a new invoice for a user, identified by email."""
    profile = users_services.get_user_profile(user_email)
    if profile is None:
        return None
    return Invoice.objects.create(user_id=profile.id, amount_cents=amount_cents)
