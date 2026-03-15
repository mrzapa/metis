# axiom-desktop — EXPERIMENTAL

> **Status: Experimental.** This is a minimal scaffold for a Tauri v2 desktop container that
> hosts the `axiom-web` Next.js frontend in a native window. It is not production-ready and
> is independent of the primary Qt desktop app (`python main.py`). See WOR-13 / WOR-14.

---

## What this is

`apps/axiom-desktop` wraps `apps/axiom-web` in a [Tauri v2](https://tauri.app) desktop shell.

- **Development mode** — loads the `axiom-web` dev server at `http://localhost:3000`
- **Production build** — bundles the pre-built static export from `apps/axiom-web/out`

The existing Python/Qt desktop app (`python main.py`) is completely unaffected.

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
cd apps/axiom-desktop
pnpm install
```

---

## Development

```bash
# From apps/axiom-desktop:
pnpm tauri dev
```

This automatically starts `pnpm dev` in `apps/axiom-web` (port 3000) and opens a native
desktop window pointing at it. The Axiom API server must also be running:

```bash
# In a separate terminal from the repo root:
python -m axiom_app.api
```

---

## Production build

### 1. Sidecar (Python API binary)

Build the standalone `axiom-api` sidecar binary before bundling. This packages
`axiom_app.api` as a one-file console executable that Tauri embeds and spawns at launch.

```bash
# From repo root — requires PyInstaller and Rust toolchain in PATH:
bash scripts/build_api_sidecar.sh
```

This writes `apps/axiom-desktop/src-tauri/binaries/axiom-api-{target-triple}`.
The Tauri build picks it up automatically via `bundle.externalBin`.

The sidecar starts the API on `http://127.0.0.1:8000` (fixed port, same default as
the dev workflow). Dynamic port selection is deferred to WOR-15.

### 2. App icons

```bash
# From apps/axiom-desktop (after pnpm install):
pnpm tauri icon ../../logo.png
```

### 3. Bundle

```bash
pnpm tauri build
```

This runs `pnpm build` in `apps/axiom-web` (producing a static export in `apps/axiom-web/out`)
and then compiles the Tauri app with the frontend and sidecar binary bundled.

---

## What is NOT changed

- `main.py` and the Qt desktop app are untouched
- `axiom_app/` Python code is untouched
- CI workflows remain Python-only
