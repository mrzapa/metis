# Axiom HTTP API

The API layer is a thin, typed boundary over Axiom's engine layer.

**Design constraints:**
- Does not import Qt, PySide6, or any UI toolkit.
- Accepts and returns JSON; uses Pydantic models for validation.
- Engine errors (`ValueError` → 400, `RuntimeError` → 503) are translated to HTTP status codes.

Start the server:

```bash
python -m axiom_app.api          # default: 0.0.0.0:8000
uvicorn axiom_app.api:app --reload
```

---

## Endpoints

### Health

| Method | Path      | Description          |
|--------|-----------|----------------------|
| GET    | `/healthz` | Returns `{"ok": true}` |

---

### Index

| Method | Path              | Description                         |
|--------|-------------------|-------------------------------------|
| POST   | `/v1/index/build` | Build a vector index from documents |
| GET    | `/v1/index/list`  | List available indexes              |

---

### Query

| Method | Path                    | Description                                |
|--------|-------------------------|--------------------------------------------|
| POST   | `/v1/query/rag`         | RAG query (retrieval + synthesis)          |
| POST   | `/v1/query/direct`      | Direct LLM query (no retrieval)            |
| POST   | `/v1/query/rag/stream`  | Streaming RAG query (SSE, `text/event-stream`) |

---

### Sessions

| Method | Path                                    | Description                              |
|--------|-----------------------------------------|------------------------------------------|
| GET    | `/v1/sessions`                          | List sessions (supports `search`, `skill` query params) |
| GET    | `/v1/sessions/{session_id}`             | Get full session detail (messages, feedback, traces) |
| POST   | `/v1/sessions/{session_id}/feedback`    | Submit thumbs-up / thumbs-down feedback  |

---

### Settings

| Method | Path            | Description                                              |
|--------|-----------------|----------------------------------------------------------|
| GET    | `/v1/settings`  | Return current settings profile (safe subset)            |
| POST   | `/v1/settings`  | Persist partial settings update to `settings.json`       |

#### GET /v1/settings

Returns the active merged settings (defaults → legacy → user overrides) as a
JSON object.

**Security:** All keys whose name starts with `api_key_` are **always redacted**
from the response. Filesystem paths are included as-is to allow clients to
display or validate them; no other filtering is applied beyond the API key
denylist.

Example response (truncated):

```json
{
  "llm_provider": "anthropic",
  "llm_model": "claude-opus-4-6",
  "llm_temperature": 0.0,
  "embedding_provider": "voyage",
  "vector_db_type": "json",
  "retrieval_k": 25,
  "top_k": 5
}
```

#### POST /v1/settings

Accepts a JSON body with an `updates` object containing the keys to change.
The update is merged with the current settings and written to `settings.json`
in the repository root. The response contains the full updated profile with
`api_key_*` fields redacted.

Request body:

```json
{
  "updates": {
    "llm_provider": "openai",
    "llm_model": "gpt-4o",
    "llm_temperature": 0.2
  }
}
```

**Security — API key denylist:**

Any update that contains a key starting with `api_key_` is **rejected with
HTTP 403** by default:

```
HTTP 403 Forbidden
{
  "detail": "Updating API key fields is not permitted via this endpoint: ['api_key_openai']. Set AXIOM_ALLOW_API_KEY_WRITE=1 to override."
}
```

To allow API key writes (e.g. during initial setup from a trusted management
tool), set the environment variable before starting the server:

```bash
AXIOM_ALLOW_API_KEY_WRITE=1 python -m axiom_app.api
```

The response **always** redacts `api_key_*` keys regardless of whether the
write was permitted, so secrets are never echoed back.

---

## CORS

Default allowed origins: `http://localhost`, `http://127.0.0.1`,
`https://localhost`, `https://127.0.0.1` (plus any port variant matched by
regex).

Override via environment variable:

```bash
AXIOM_API_CORS_ORIGINS="https://myapp.example.com,http://localhost:3000"
```
