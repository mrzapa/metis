---
name: launch-app
description: Launch the METIS app for runtime validation and testing.
---

# Launch App

METIS is primarily a PySide6 desktop app with a shared CLI entrypoint.

## Setup

From the repo root:

```powershell
python -m pip install --upgrade pip
pip install -e .[dev]
```

## Primary launch

Start the default desktop app:

```powershell
python main.py
```

Useful alternates:

```powershell
python main.py --cli --help
$env:QT_QPA_PLATFORM="offscreen"; python -m pytest -q tests/test_app_view_smoke.py
```

## What to verify

- Desktop path: the PySide6 app opens without a startup traceback.
- CLI path: `python main.py --cli --help` exits successfully and prints CLI help.
- Offscreen UI smoke: the Qt smoke test passes when GUI interaction is not practical.

## Notes

- Prefer the desktop launch for app-shell or interaction changes.
- Prefer the offscreen smoke test for fast validation when a visible window is not required.
