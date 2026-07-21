"""Django ORM models for the users app.

This module is the schema layer: it defines shape and constraints only. It
must not import services.py or views.py -- both sit above it -- which is
enforced by the layering rule in ../architecture.py.
"""

from __future__ import annotations

from django.db import models


class User(models.Model):
    """A registered account."""

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "users"

    def __str__(self) -> str:
        return self.email
