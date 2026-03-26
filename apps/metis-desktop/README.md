# metis-desktop

The canonical Tauri desktop shell that wraps `metis-web` in a native window.

---

## What this is

`apps/metis-desktop` wraps `apps/metis-web` in a [Tauri v2](https://tauri.app) desktop shell.

- **Development mode** — loads the `metis-web` dev server at `http://localhost:3000`
- **Production build** — bundles the pre-built static export from `apps/metis-web/out`

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Rust + Cargo | stable ≥ 1.77 | https://rustup.rs |
| Node.js | ≥ 20 | https://nodejs.org |
| pnpm | ≥ 9 | `npm i -g pnpm` |
| Tauri system deps | — | https://tauri.app/start/prerequisites/ |

---

## Setup

```bash
cd apps/metis-desktop
pnpm install
```

---

## Development

```bash
# From apps/metis-desktop:
pnpm tauri dev
```

This automatically starts `pnpm dev` in `apps/metis-web` (port 3000) and opens a native
desktop window pointing at it. The METIS API server must also be running:

```bash
# In a separate terminal from the repo root:
python -m metis_app.api
```

---

## Production build

### 1. Sidecar (Python API binary)

Build the standalone `metis-api` sidecar binary before bundling. This packages
`metis_app.api` as a one-file console executable that Tauri embeds and spawns at launch.

```bash
# From repo root — requires PyInstaller and Rust toolchain in PATH:
bash scripts/build_api_sidecar.sh
```

This writes `apps/metis-desktop/src-tauri/binaries/metis-api-{target-triple}`.
The Tauri build picks it up automatically via `bundle.externalBin`.

The sidecar starts the API on a dynamically selected free port (or port 8000 if
`METIS_API_PORT` is set). The selected URL is printed to stdout as
`METIS_API_LISTENING=http://host:port` which the Tauri host reads for the frontend.

### 2. App icons

```bash
# From apps/metis-desktop (after pnpm install):
pnpm tauri icon ../../logo.png
```

### 3. Bundle

```bash
pnpm tauri build
```

This runs `pnpm build` in `apps/metis-web` (producing a static export in `apps/metis-web/out`)
and then compiles the Tauri app with the frontend and sidecar binary bundled.

---

## Architecture

- `metis-web/` — Next.js frontend
- `metis_app.api` — FastAPI backend
- Tauri — native desktop container
