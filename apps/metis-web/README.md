# metis-web

Next.js web UI for METIS. Provides a browser-based interface for chat, document library management, and settings — backed by the local METIS API server.

## Stack

- **Next.js 16** (App Router, TypeScript)
- **Tailwind CSS v4**
- **Base UI + shadcn/ui** components
- **React Hook Form + Zod** for forms

## Prerequisites

- Node.js 18+ and [pnpm](https://pnpm.io/installation)
- The METIS Python backend running on `http://127.0.0.1:8000`

## Quick start

### 1. Start the API server

From the repo root:

```bash
bash scripts/run_api_dev.sh
```

Or on Windows (PowerShell):

```powershell
.\scripts\run_api_dev.ps1
```

This starts a hot-reloading FastAPI server at `http://127.0.0.1:8000`.

### 2. Start the web UI

```bash
cd apps/metis-web
pnpm install
pnpm dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

### Alternative: start both from the repo root

If you are iterating on the browser UI and API together, use the combined
launcher from the repo root instead of two terminals:

```bash
bash scripts/run_nextgen_dev.sh
```

On Windows (PowerShell):

```powershell
.\scripts\run_nextgen_dev.ps1
```

## Available scripts

| Command | Description |
|---------|-------------|
| `pnpm dev` | Start development server with hot reload |
| `pnpm build` | Production build |
| `pnpm start` | Start production server (requires `pnpm build` first) |
| `pnpm lint` | Run ESLint |

## Pages

| Route | Description |
|-------|-------------|
| `/` | Home / landing |
| `/chat` | Chat with your indexed documents |
| `/library` | Manage indexed document library |
| `/settings` | Configure LLM provider, embeddings, and vector store |

## Configuration

The web UI connects to the API at `http://127.0.0.1:8000` by default. To point it at a different host, set `NEXT_PUBLIC_METIS_API_BASE` in a `.env.local` file:

```bash
# apps/metis-web/.env.local
NEXT_PUBLIC_METIS_API_BASE=http://127.0.0.1:8000
```

## Development tips

- The API server must be running before the web UI can load data.
- Both the API server and web dev server support hot reload — changes take effect immediately.
- API docs are available at `http://127.0.0.1:8000/docs` when the server is running.
