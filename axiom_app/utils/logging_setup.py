"""axiom_app.utils.logging_setup — Application-wide logging initialisation.

Call ``setup_logging()`` once, as early as possible in ``axiom_app.app``
(before Tk is created), so that even startup errors are captured on disk.

Hierarchy
---------
All axiom_app modules use ``logging.getLogger(__name__)``, which produces
names like ``axiom_app.models.app_model``.  These are children of the
``axiom_app`` logger configured here, so they all inherit the two handlers
without any per-module configuration.

Handlers
--------
* **RotatingFileHandler** — writes DEBUG+ to ``<log_dir>/axiom.log``.
  Rolls at 5 MB; keeps 3 backup files (``axiom.log.1``, ``.2``, ``.3``).
* **StreamHandler** (stderr) — writes INFO+ to the console so routine
  operation stays quiet while the file captures full detail.

The function is idempotent: calling it twice returns the same logger
without adding duplicate handlers.
"""

from __future__ import annotations

import logging
import pathlib
import sys
from logging.handlers import RotatingFileHandler

# Name of the log file written inside log_dir.
_LOG_FILENAME = "axiom.log"

# Shared format: timestamp, padded level, dotted module name, message.
_FMT = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

# Root logger for the entire axiom_app namespace.
_LOGGER_NAME = "axiom_app"


def setup_logging(
    log_dir: str | pathlib.Path,
    level: str | int = "DEBUG",
) -> logging.Logger:
    """Configure rotating-file + console logging for the axiom_app namespace.

    Parameters
    ----------
    log_dir:
        Directory in which ``axiom.log`` (and its rotated siblings) will be
        created.  The directory is created with ``parents=True`` if absent.
    level:
        Minimum level written to the **file** handler.  Accepts a logging
        level name (``"DEBUG"``, ``"INFO"``, …) or an integer.
        The console handler is always clamped to INFO regardless of this
        value, so debug noise never reaches the terminal.

    Returns
    -------
    logging.Logger
        The configured ``axiom_app`` root logger.  All child loggers
        (``axiom_app.models.*``, ``axiom_app.controllers.*``, …) inherit
        these handlers automatically.
    """
    log_dir = pathlib.Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(_LOGGER_NAME)

    # Idempotent: if handlers are already attached we were called before.
    if logger.handlers:
        return logger

    # The logger itself accepts everything; individual handlers filter.
    logger.setLevel(logging.DEBUG)
    logger.propagate = False  # don't bubble up to the root logging logger

    formatter = logging.Formatter(_FMT, datefmt=_DATEFMT)

    # ── rotating file handler (DEBUG+, or caller-supplied level) ─────
    file_level = (
        getattr(logging, level.upper(), logging.DEBUG)
        if isinstance(level, str)
        else int(level)
    )
    fh = RotatingFileHandler(
        log_dir / _LOG_FILENAME,
        maxBytes=5 * 1024 * 1024,   # 5 MB
        backupCount=3,
        encoding="utf-8",
        delay=True,                  # don't create the file until first write
    )
    fh.setLevel(file_level)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # ── console handler (INFO+ always) ───────────────────────────────
    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger
