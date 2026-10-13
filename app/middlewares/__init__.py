"""Middleware aiogram."""

from app.middlewares.db_session import DbSessionMiddleware

__all__ = ["DbSessionMiddleware"]
