"""
API routers package.

This package contains all FastAPI routers for the Canonical DB Agent API.
"""

from app.routers import chunks, documents, health

__all__ = ["health", "documents", "chunks"]

# Made with Bob
