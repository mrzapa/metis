---
name: launch-app
description: Launch the METIS app for runtime validation and testing.
---

# Launch App

METIS is a web-first local app: a Python API plus the Next.js UI in
`apps/metis-web/`. The legacy PySide desktop path has been removed.

## Setup

From the repo root:

```powershell
python -m pip install --upgrade pip
pip install -e .[dev,api]
```

## Primary launch

Start the default local app shell:

```powershell
python main.py
```

Useful alternates:

```powershell
python main.py --cli --help
.\scripts\run_api_dev.ps1
cd apps/metis-web; pnpm dev
.\scripts\run_forecast_api_dev.ps1
```

## What to verify

- Web path: `/chat` loads without a startup traceback and the core shell renders.
- CLI path: `python main.py --cli --help` exits successfully and prints CLI help.
- Forecast path: if validating TimesFM, switch to `Forecast` in chat and confirm preflight, CSV upload, and schema controls appear.

## Notes

- `python main.py` opens the browser against the API server at `http://127.0.0.1:8000`.
- For the live Next dev UI, run the API and `pnpm dev` separately.
- On Windows, the reproducible Forecast runtime currently uses Python 3.11, FastAPI, and `.\scripts\run_forecast_api_dev.ps1`.
