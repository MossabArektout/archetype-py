"""Django ORM models for the billing app.

Schema-only layer, same rules as users/models.py.
"""

from __future__ import annotations

from django.db import models


class Invoice(models.Model):
    """A bill issued to a user.

    The user is referenced with the string form "users.User" rather than an
    imported class. This is standard Django practice for cross-app foreign
    keys, and as a side effect it keeps billing.models decoupled from
    users.models at the Python-import level too -- billing never needs to
    `import users.models` just to declare this relationship.
    """

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="invoices",
    )
    amount_cents = models.PositiveIntegerField()
    is_paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "billing"
