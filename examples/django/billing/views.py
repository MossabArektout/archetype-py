"""HTTP layer for the billing app.

Views call billing/services.py only.
"""

from __future__ import annotations

from django.http import HttpRequest, JsonResponse

from billing import services


def billing_summary(request: HttpRequest, user_email: str) -> JsonResponse:
    summary = services.get_billing_summary(user_email)
    if summary is None:
        return JsonResponse({"error": "not found"}, status=404)
    return JsonResponse(
        {
            "outstanding_cents": summary.outstanding_cents,
            "unpaid_invoice_count": summary.unpaid_invoice_count,
        }
    )
