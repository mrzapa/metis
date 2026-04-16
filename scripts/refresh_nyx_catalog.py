"""Rebuild the packaged Nyx component catalog snapshot.

Thin dispatcher to ``metis_app.services.nyx_catalog_refresh:main``. Run this
by hand after editing ``metis_app/assets/nyx_catalog_review.json``; the regenerated
``nyx_catalog_snapshot.json`` is consumed by both the API and the installer.

Invocation:
    python scripts/refresh_nyx_catalog.py
"""

from metis_app.services.nyx_catalog_refresh import main


if __name__ == "__main__":
    raise SystemExit(main())