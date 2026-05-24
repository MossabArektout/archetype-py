"""Namespace package API module."""

from company.shared import utils


def handle_payment() -> str:
    return utils.shared_value()
