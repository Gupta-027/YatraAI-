"""Versioned API surface."""

from __future__ import annotations

from fastapi import APIRouter

from yatraai.api.v1 import (
    routes_analytics,
    routes_auth,
    routes_collab,
    routes_destinations,
    routes_rag,
    routes_trips,
)

api_router = APIRouter()
api_router.include_router(routes_auth.router)
api_router.include_router(routes_destinations.router)
api_router.include_router(routes_trips.router)
api_router.include_router(routes_rag.router)
api_router.include_router(routes_collab.router)
api_router.include_router(routes_analytics.router)

__all__ = ["api_router"]
