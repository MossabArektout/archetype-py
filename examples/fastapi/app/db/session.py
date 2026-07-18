"""Database session layer, wraps the internal engine for the rest of the app."""

from app.db.internal.engine import Engine

_engine = Engine()


def get_session() -> Engine:
    return _engine
