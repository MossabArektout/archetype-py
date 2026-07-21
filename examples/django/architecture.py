"""Example Archetype rules for a Django project.

Layout modeled here (repeated once per app, using users/ and billing/):

    users/
        models.py     -- ORM models. Schema only.
        internal.py   -- raw ORM/SQL access. Private to this app.
        services.py   -- the app's public API. The only sanctioned
                          integration point for views and other apps.
        views.py      -- HTTP layer. Talks to services.py only.
    billing/
        (same shape as users/)

Run these rules with:

    archetype check examples/django

See examples/django/README.md for a full walkthrough, including what a
violation looks like.
"""

from __future__ import annotations

from archetype import imports, module, rule
from archetype.rules import layers, no_cycles


@rule("views must not import internal modules directly")
def views_must_not_import_internal() -> None:
    """Views must go through services, never internal.py or the ORM.

    This is the "no database internals in the HTTP layer" rule. It applies
    to every app at once: *.views may not import *.internal.
    """
    imports("*.views").must_not_import("*.internal")


@rule("users internal is private to the users app")
def users_internal_is_private() -> None:
    """Only code inside users/ may import users/internal.py.

    billing (or any other app) reaching into users.internal directly -- to
    skip users.services and query the ORM itself -- is exactly the
    violation this rule exists to catch.
    """
    module("users.internal").only_imported_within("users")


@rule("billing internal is private to the billing app")
def billing_internal_is_private() -> None:
    """Mirror of the rule above, scoped to billing/internal.py."""
    module("billing.internal").only_imported_within("billing")


@rule("views, services, and models stay in order")
def layers_are_ordered() -> None:
    """Enforce the top-down direction: views -> services -> models.

    models.py must never import services.py or views.py, and services.py
    must never import views.py. This is a broader, ongoing check; it does
    not by itself stop views from importing internal.py directly -- that's
    the job of the rule above, since layering only forbids imports back
    *up* the stack, not skipping a layer on the way down.
    """
    layers(["*.views", "*.services", "*.models"]).are_ordered()


@rule("no import cycles between apps")
def no_cycles_between_apps() -> None:
    """Guard against users and billing (or future apps) forming a cycle."""
    no_cycles()
