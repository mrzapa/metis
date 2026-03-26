# metis-web-lite

**Status:** Experimental prototype — WOR-23

A minimal streaming shell experiment focused on *perceived performance* rather than
full design parity with `apps/metis-web`. The goal is a fast proof-of-concept that
validates the SSE streaming path end-to-end in a browser.

---

## Framework choice: Astro

**Chosen over Qwik** because Astro gets to a working streaming proof faster:

- Zero-JS by default; client interactivity is added only where needed via `<script>`
  tags — no framework overhead on the critical path.
- The streaming client is plain fetch + ReadableStream, which is framework-agnostic.
- `npm install && npm run dev` is the entire setup — no build adapters or framework
  config required for a static prototype.

**Trade-off:** Astro's island model is not optimised for fine-grained reactive
streaming. A production build would benefit from a signals-based framework (Solid,
Qwik, or a React with concurrent features). This experiment answers the question:
*"can we reach a faithful streaming proof quickly?"* — the answer is yes.

---

## Prerequisites

- Node 18+ and npm (or pnpm/yarn)
- The Python API running locally:
  ```bash
  # from repo root
  python -m metis_app.api
  # starts FastAPI on http://127.0.0.1:8000
  ```
- At least one index built via `apps/metis-web` or the Python CLI (the chat page
  needs a `manifest_path` to send a RAG query).

---

## Local run path

```bash
cd apps/metis-web-lite
npm install
npm run dev
# → http://localhost:4321
```

The dev server proxies nothing — it serves static HTML with client-side JS that
calls the API directly. The API base URL defaults to `http://127.0.0.1:8000`; set
`PUBLIC_METIS_API_BASE` to override:

```bash
PUBLIC_METIS_API_BASE=http://localhost:9000 npm run dev
```

---

## What it does

1. **`/`** — Landing page that links to `/chat`.
2. **`/chat`** — Single-page streaming chat:
   - On load, fetches `/v1/index/list` and populates an index dropdown.
   - On submit, POSTs to `/v1/query/rag/stream` and renders tokens as they arrive.
   - Handles `token`, `final`, and `error` SSE events; ignores the rest.

---

## What it does NOT do

- No session history, library management, or settings pages.
- No design system — intentionally plain HTML + minimal CSS.
- No sharing of code or state with `apps/metis-web`.
- No production build target (no deployment config, no Docker).

---

## Isolation guarantee

This package has its own `package.json` and is **not** referenced by any other
workspace. Building or running it has no effect on `apps/metis-web`.
