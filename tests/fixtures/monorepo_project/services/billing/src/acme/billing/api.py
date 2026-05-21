"""Billing service API module in monorepo layout."""

from acme.shared import utils


def run() -> str:
    return utils.format_total(10)
