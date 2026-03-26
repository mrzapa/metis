# Desktop App: Versioning, Lockstep, and Updater Placeholders

> **Status: experimental / placeholder**
> The desktop container is explicitly experimental (see window title). This
> document captures the intended versioning model and future update wiring.
> No production update infrastructure is required or implied by this document.

---

## Current Versioning Model

### Single Source of Truth

The canonical version lives in `VERSION` at the repo root. All consumers derive from this:

| Component | Version Source |
|----------|---------------|
| Python config | `metis_app/config.py` reads from `VERSION` |
| FastAPI | `GET /v1/version` returns `APP_VERSION` |
| Tauri shell | `apps/metis-desktop/src-tauri/tauri.conf.json` |
| Frontend | `apps/metis-web/app/diagnostics/page.tsx` (hardcoded `WEB_VERSION`) |

> **Note:** The frontend version is currently hardcoded. Future: derive from build process or `VERSION`.

### Schema Versioning

**Settings schema:** Integer `schema_version` in `settings.json` (defaults to 1).
- Migration hook exists in `metis_app/settings_store.py`
- Migrations run automatically on load
- See `_run_migrations()` for available migrations

**Session schema:** Currently **NOT versioned**. This is a gap that should be addressed:
- `SessionRepository` creates tables without version tracking
- Schema changes require manual migration or data loss
- **Recommendation:** Add `schema_version` to session tables before production release

---

## Overview

The METIS desktop distribution packages three components together:

| Component | What it is | Where it lives |
|-----------|-----------|----------------|
| **Desktop container** | Tauri v2 shell (Rust + WebView) | `apps/metis-desktop/` |
| **Web bundle** | Next.js static export | built from `apps/metis-web/`, embedded in the container at build time |
| **API sidecar** | PyInstaller-packaged Python API server | `apps/metis-desktop/src-tauri/binaries/metis-api-<target>` |

These three ship as **one release unit**. They share a single version string.

---

## Version Lockstep

### Single source of truth

The authoritative version lives in:

```
apps/metis-desktop/src-tauri/tauri.conf.json  →  "version": "x.y.z"
```

When a release is cut:
- The Tauri container is built from that version.
- The web bundle is exported and embedded at build time; its version is
  implicit in the desktop release (no separate web version string).
- The API sidecar binary is built via `scripts/build_api_sidecar.sh` and
  bundled into the same installer; it carries the same version.

### Why version together?

The sidecar exposes an internal HTTP API that the embedded web frontend
calls via `invoke("get_api_base_url")`. The frontend and API are built and
tested together, so shipping them as separate versioned artifacts would
introduce a compatibility matrix with no current benefit.

**Smallest reasonable assumption:** desktop container and API sidecar version
together as one release unit. If the API ever needs an independent release
cycle, introduce a separate `SIDECAR_VERSION` at that time.

---

## Future Update Flow (placeholder, not implemented)

When the Tauri updater plugin is eventually wired up, the intended flow is:

```
App startup
  └─ tauri-plugin-updater checks endpoint
       └─ endpoint returns manifest JSON
            ├─ no update → continue normally
            └─ update available
                 ├─ (optional) prompt user
                 └─ download & verify signed bundle
                      └─ replace container + embedded sidecar + web bundle
                           └─ restart
```

Key points:
- The sidecar binary travels **inside** the container bundle; a container
  update also updates the sidecar. There is no separate sidecar updater.
- The web bundle is re-embedded at container build time; it is never fetched
  separately at runtime.
- Update manifests are signed. The public key would live in
  `tauri.conf.json` under `plugins.updater.pubkey` (see placeholder below).

### Placeholder manifest location

When a hosting provider is chosen, update manifests would be served at a
URL matching the Tauri updater template variables:

```
https://<tbd-host>/updates/{{target}}/{{arch}}/{{current_version}}
```

Example resolved URL:
```
https://<tbd-host>/updates/linux/x86_64/0.0.1
```

The manifest format is defined by the Tauri updater spec:
<https://v2.tauri.app/plugin/updater/>

**This URL is not live.** No manifests are published. Hosting and CDN
choices are undecided.

---

## Known Limitations

### Before Production Desktop Release

| Item | Status | Notes |
|------|--------|-------|
| Signed update manifests | Not implemented | Placeholder config exists |
| Version locking (shell ↔ sidecar) | Not implemented | No runtime compatibility check |
| Rollback on failed update | Not implemented | Not wired |
| CI/CD release pipeline | Out of scope | Needs separate work |
| Session schema versioning | Not implemented | Gap - should add before prod |
| Frontend version derivation | Hardcoded | Should derive from VERSION |

### What Works

- Version is now synchronized across Python config, API, and Tauri shell
- Settings have schema versioning with migration hooks
- API exposes `min_compatible` for frontend compatibility checks
- Frontend shows compatibility warning in diagnostics

---

## What Is Out of Scope for This Ticket

- Production update manifests
- Signing key generation or key management
- CI/CD release pipeline changes
- Hosting or CDN setup
- Delta/patch updates
- Rollback mechanisms

These are deferred until the desktop container graduates from experimental
status.

---

## Tauri Config Placeholder

The `plugins.updater` block in `tauri.conf.json` contains placeholder values
that mark where future wiring belongs without enabling any real update
checks. See that file for the exact block.

To activate the updater in the future:
1. Generate a signing keypair: `tauri signer generate`
2. Replace `PLACEHOLDER` in `pubkey` with the generated public key.
3. Store the private key as a CI secret (`TAURI_SIGNING_PRIVATE_KEY`).
4. Replace the `endpoints` URL with the real manifest host.
5. Add `tauri-plugin-updater` to `Cargo.toml` and wire the Rust plugin.
6. Publish signed manifests to the chosen host as part of the release workflow.

---

## Related

- `apps/metis-desktop/src-tauri/tauri.conf.json` — container config and updater placeholder
- `scripts/build_api_sidecar.sh` — sidecar build script
- `apps/metis-desktop/src-tauri/src/lib.rs` — sidecar spawn and port negotiation
- `docs/adr/0001-local-api-and-web-ui.md` — architectural context
