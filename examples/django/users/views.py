"""HTTP layer for the users app.

Views call users/services.py only. They never import users/internal.py or
the ORM directly -- that boundary is enforced by ../architecture.py.
"""

from __future__ import annotations

from django.http import HttpRequest, JsonResponse

from users import services


def user_detail(request: HttpRequest, email: str) -> JsonResponse:
    profile = services.get_user_profile(email)
    if profile is None:
        return JsonResponse({"error": "not found"}, status=404)
    return JsonResponse(
        {"id": profile.id, "email": profile.email, "full_name": profile.full_name}
    )


def user_count(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"active_users": services.active_user_count()})
