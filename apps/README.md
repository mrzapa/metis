# apps/

Frontend applications for METIS.

## metis-web

Next.js web UI (TypeScript + Tailwind). Node tooling is fully isolated to this directory.
Uses **pnpm** (see `pnpm-workspace.yaml` and `pnpm-lock.yaml`).

```bash
cd apps/metis-web
pnpm install
pnpm dev        # starts on http://localhost:3000
```

The web UI expects the METIS API server at `http://127.0.0.1:8000`. Start it with:

```bash
python -m metis_app.api_litestar
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
Uses **npm** (keeps the Tauri toolchain setup identical to the official Tauri
templates, which are npm-native).

See [`apps/metis-desktop/README.md`](metis-desktop/README.md) for setup and usage.

---

## metis-web-lite

Archived Astro streaming experiment — not a shipped product surface. Uses **npm**
intentionally so the entire setup is `npm install && npm run dev` with no
workspace or adapter configuration. See [`apps/metis-web-lite/README.md`](metis-web-lite/README.md).

---

## Why the mix of package managers?

- `metis-web` → pnpm (workspace, overrides, lockfile integrity for the shipped web product).
- `metis-desktop` → npm (matches Tauri's official scaffolds; no third-party workspace needed).
- `metis-web-lite` → npm (archived experiment; a zero-config setup was the point).

Each app's lockfile is the source of truth for that app; there is no repo-root
`package.json`.
