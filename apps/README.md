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
