# apps/

Web frontends for Axiom. The Python backend and Qt desktop app live at the repository root (`axiom_app/`).

## axiom-web

Next.js web UI (TypeScript + Tailwind). Node tooling is fully isolated to this directory.

```bash
cd apps/axiom-web
pnpm install
pnpm dev        # starts on http://localhost:3000
```

The web UI expects the Axiom API server at `http://127.0.0.1:8000`. Start it with:

```bash
python -m axiom_app.api
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

## axiom-desktop (experimental)

> **Experimental.** A [Tauri v2](https://tauri.app) desktop shell that hosts `axiom-web` in a
> native window. Not production-ready. The primary Qt desktop app (`python main.py`) is unaffected.

See [`apps/axiom-desktop/README.md`](axiom-desktop/README.md) for setup and usage.
