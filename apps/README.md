# apps/

Frontend applications for METIS.

## metis-web

Next.js web UI (TypeScript + Tailwind). Node tooling is fully isolated to this directory.

```bash
cd apps/metis-web
pnpm install
pnpm dev        # starts on http://localhost:3000
```

The web UI expects the METIS API server at `http://127.0.0.1:8000`. Start it with:

```bash
python -m metis_app.api
```

From the repo root you can launch both the API and the web UI together:

```bash
bash scripts/run_nextgen_dev.sh
```

On Windows use:

```powershell
.\scripts\run_nextgen_dev.ps1
```

---

## metis-desktop

The canonical Tauri desktop shell that wraps `metis-web` in a native window.

See [`apps/metis-desktop/README.md`](metis-desktop/README.md) for setup and usage.
