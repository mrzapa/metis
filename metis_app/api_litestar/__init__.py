"""Experimental Litestar shadow port of the METIS API.

This module provides an alternative ASGI implementation using Litestar
for evaluation purposes. The FastAPI implementation in metis_app.api
remains the production default.

Do not modify this module as part of normal development.
"""

from .app import create_app

__all__ = ["create_app"]
