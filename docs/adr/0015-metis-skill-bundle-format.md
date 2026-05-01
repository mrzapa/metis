# 0015 - `.metis-skill` Bundle Format

- **Status:** Accepted (M14 Phase 7)
- **Date:** 2026-05-01

## Context

M14 Phase 7 closes the Forge milestone by giving installed skills a
**file format**: a single artefact users can hand to another METIS
install and have the recipient absorb. This is the foundation
`pro-tier-launch/plan.md` will eventually build a marketplace on, but
Phase 7 ships nothing remote — no upload, no signature server, no
discoverability. The deliverable is `pack` + `unpack` + a drop zone.

The plan doc's *What NOT to do in M14* section makes this boundary
load-bearing for M15 launch copy: "you can already share skills
between METIS installs, the marketplace just makes it one click."
For that copy to be true, the file format has to actually exist and
round-trip cleanly between installs.

A skill on disk today is a directory under `skills/<id>/` containing
exactly one `SKILL.md` (YAML frontmatter + markdown body). The
loader is `metis_app/services/skill_repository.parse_skill_file`. The
nine shipped skills (`agent-native-bridge`, `evidence-pack-timeline`,
`pptx-export`, `qa-core`, `research-claims`, `summary-blinkist`,
`swarm-critique`, `symphony-setup`, `tutor-socratic`) are the
audit set; whatever the bundle format does must round-trip all nine.

Three architectural questions cut across the implementation:

1. **On-disk layout** — what's inside the tarball, and where?
2. **Trust** — should v1 sign bundles? With what root?
3. **Slug-conflict resolution on import** — silent replace, error,
   or a per-import prompt?

A fourth question — semver-aware dependency resolution between
skills — is deferred and recorded under *Open Questions*.

## Decision

### 1. On-disk layout — POSIX tar, `manifest.yaml` at root, `skill/` payload

A `.metis-skill` bundle is a **POSIX `tar` archive** (uncompressed in
v1; gzip can be added later without breaking the format) with this
layout:

```
manifest.yaml         # bundle metadata
skill/SKILL.md        # the skill payload
skill/<extra files>   # any other files the skill ships (none today)
```

The `skill/` directory holds *exactly* what `skills/<id>/` holds on
the source install — no rewrites, no path normalisation. On import
the contents of `skill/` are extracted into `<install
skills_root>/<id>/`. The `id` comes from the manifest, not from
the directory name in the tarball, so the on-disk layout is robust
to a recipient renaming the bundle file.

**`manifest.yaml` schema (v1):**

```yaml
bundle_format_version: 1            # int, required; bumps on breaking change
skill_id: qa-core                   # required; must match SKILL.md frontmatter id
name: Q&A Core                      # required; mirrors SKILL.md frontmatter name
description: ...                    # required; one-sentence
version: "0.1.0"                    # required; semver-shaped str (not validated yet)
exported_at: "2026-05-01T12:00:00Z" # required; ISO-8601 UTC
min_metis_version: "0.1.0"          # required; recipient compares
author: "user@example.com"          # optional; free-form string
dependencies:                       # optional; list of {id, min_version}
  - {id: agent-native-bridge, min_version: "0.0.0"}
```

`bundle_format_version: 1` is the canary that lets v2+ readers reject
older bundles cleanly. `min_metis_version` is recorded but **not
enforced** in v1 (no METIS version is committed to a tag yet); the
reader logs a warning if recipient version is missing or below the
declared minimum, and proceeds. `dependencies` is recorded for the
preview pane to display but is **not resolved** in v1 — the recipient
sees the list and decides.

YAML over JSON for the manifest because (a) the existing SKILL.md
frontmatter is YAML, (b) the bundle is human-readable when extracted
manually, and (c) the project already has `pyyaml` as a dep.

### 2. Trust — unsigned v1, deferred signing

`pyca/cryptography` is **not** in the `pyproject.toml` dep set. The
Phase 7 plan flags signing as conditional ("if we can add
`pyca/cryptography` without weight"); the actual answer is that
unsigned v1 is the right call for a separate reason:

**A signature without a trust root is theatre.** v1 has no key
infrastructure: no METIS signing authority, no per-user keypair
storage, no revocation. A self-signed bundle adds a cryptographic
ritual that protects against nothing the user could verify. The
honest posture is "this bundle is trusted because you got it from
someone you trust" — same as any `.zip` of a Python project.

When M15+ wires the marketplace, signing arrives as ADR 0016 (or
higher) with the trust-root design that v1 deliberately punts. The
manifest already has room: future readers will check for an optional
`signature` field, ignore it on `bundle_format_version: 1`, require
it on `bundle_format_version: 2+` if the marketplace decision says
so.

### 3. Slug-conflict resolution on import — explicit `replace=True` switch

When the recipient imports a bundle whose `skill_id` already exists
under `skills/`, the **install endpoint returns HTTP 409** unless
the request body sets `replace: true`. The frontend's preview
dialog surfaces the conflict, asks the user, and re-submits the
upload with `replace: true` if they confirm. The preview endpoint
itself is read-only — it never touches the filesystem.

This is an explicit choice over (a) silent replace (would lose
local edits) and (b) auto-rename to `<id>-2` (breaks the manifest's
`skill_id` invariant and confuses the engine's enabled-list
lookup). The user's local edits are real work; clobbering them
without acknowledgement is exactly the M13/M14 lesson — "skill
acceptance must respect the user".

A bundle whose `skill_id` collides with itself (importing the same
bundle twice) is the common case for "I exported, I edited, I want
to overwrite my own previous version". The replace-confirm dialog
handles that path.

### 4. Tarball-traversal defence — Python 3.12 `data` filter + explicit prefix check

The bundle reader uses Python 3.12's
[`tarfile.data_filter`](https://docs.python.org/3.12/library/tarfile.html#tarfile.data_filter)
on `extractall`, plus an explicit pre-extraction loop that rejects
any tarball member whose normalised path:

- Is absolute (`startswith("/")` or matches a Windows drive prefix).
- Contains `..` after `os.path.normpath`.
- Resolves outside the per-bundle staging directory.

This is belt-and-braces — `data_filter` raises on these cases
already, but the explicit check produces a `BundleValidationError`
with a clear human-readable message instead of `tarfile`'s generic
exception. The bundle never extracts to the live `skills/` root
directly; staging in `tmp_path` first and *moving* the validated
`skill/` subtree is the install step.

## Constraints

- **No new top-level dependencies.** The format uses `tarfile` +
  `pyyaml` + `dataclasses` + `pathlib` — all stdlib or already in
  the dep set. Adding `pyca/cryptography` for signing is rejected
  in §2 above.
- **Round-trip parity with `skills/<id>/SKILL.md`.** Pack-then-unpack
  on any of the nine shipped skills must produce a byte-identical
  `SKILL.md`. The acceptance test exercises this on every shipped
  skill.
- **No remote endpoint.** Per `VISION.md` principle #6 ("Local by
  default"). Phase 7 ships file-only export and file-only import.
  The format reserves room for a future `signature` field but the
  v1 reader/writer never produces or consumes one.
- **Frontend never sees raw bytes.** The export route returns
  base64 + the intended filename; the frontend decodes to a `Blob`
  and triggers a download. Keeps the JSON path clean and matches
  the `audited_urlopen`-style "no surprises in the network layer"
  posture.
- **Free tier ships export and import.** Per `VISION.md` business
  model, every local feature is free. The shareable foundation is
  free; the marketplace (when it arrives) is Pro.

## Alternatives Considered

- **Zip instead of tar.** Rejected. `zipfile` is also stdlib, but
  the project's existing artefact-export code (`pptx-export` skill)
  uses tar conventions; matching that keeps tooling consistent. The
  format is uncompressed because skill payloads are tiny (~1–5 KB
  each); compression is a v2 concern.
- **Single-file format (manifest as YAML frontmatter on a combined
  file).** Rejected. The directory layout is the source of truth on
  disk; the bundle's job is to *transport* that layout, not invent
  a new representation. Future skills will ship multi-file payloads
  (templates, fixtures); the directory shape needs to survive.
- **Sign with self-generated keypair.** Rejected — see §2. Signing
  without a trust root is theatre, and the time spent on key
  management is better spent shipping the marketplace UI in a
  future milestone.
- **Auto-rename on slug conflict.** Rejected — see §3. Manifest
  `skill_id` is a stable identifier the engine uses; silently
  rewriting it produces ghost-skills that don't match the
  manifest, the SKILL.md frontmatter, or the directory name.
- **Resolve dependencies eagerly on import.** Rejected for v1.
  Dependency resolution requires both a registry (which the
  marketplace would provide) and a version solver — both
  out of scope. v1 records dependencies in the manifest and
  surfaces them in the preview dialog so the user can install
  the prerequisites by hand.
- **Bundle the user's `settings["skills"]["enabled"][<id>]`
  state.** Rejected. The bundle ships the skill *definition*, not
  the recipient's preference. Whether the recipient enables the
  skill after import is the recipient's call; pre-flipping a toggle
  on import would be a surprise. The manifest's `description`
  surfaces "this is what this skill does" so the recipient can
  decide.

## Consequences

- **Forward-compat hooks reserved.** `bundle_format_version: 1`
  pins the schema. v2 readers gate on this field; v1 readers
  hard-fail on `bundle_format_version: 2+` so no surprise reads
  occur.
- **`metis_app/services/forge_bundle.py`** is the single source of
  truth for pack/unpack/validate/install. The route layer never
  touches `tarfile` directly; everything goes through this module.
- **Frontend gets a `Blob`.** `apps/metis-web/lib/api.ts` ships
  an `exportSkillBundle` that returns a `Blob` ready to feed to
  `URL.createObjectURL` for the download trigger. The route's
  `content_base64 + sha256` envelope is decoded client-side; the
  hash lets the UI show a fingerprint when paranoia is justified.
- **`.metis-skill` is now part of the public surface.** The
  on-disk layout, the manifest schema, and the `bundle_format_version`
  field are committed to `main` and have to roll forward
  compatibly. Renaming `manifest.yaml` to `manifest.json` post-v1
  requires a v2 schema bump and reader fallback.
- **Slug stability.** The bundle ships the source `skill_id`; the
  recipient cannot rename on import without re-packing. This is
  consistent with how the engine and the constellation address
  skills — the slug is the primary key.
- **Validation errors are user-readable.** `validate_bundle`
  returns a `list[str]` of human-readable problems for the
  preview dialog. The route surfaces them as 400 details when the
  user hits Install on a bundle that fails validation.
- **The Phase 7 export button is a "stable URL".** `<id>-<version>.metis-skill`
  is the recommended filename; the frontend uses
  `Content-Disposition` + the route's returned `filename` field.
  Version bumps produce new files; old versions still load.

## Open Questions

- **Semver dependency resolver.** Phase 7 records `dependencies`
  but does not solve them. When the marketplace arrives, a real
  resolver (probably `packaging.specifiers` from stdlib + a
  registry lookup) becomes its own ADR.
- **Signing trust root.** Per §2, signing arrives with the
  marketplace and gets its own ADR. v1 reserves the field name
  but never produces or consumes it.
- **Compression.** v2 may switch to `tar.gz` once skill payloads
  grow past ~10 KB. The format-version bump handles the
  transition; v1 readers reject `bundle_format_version: 2+`.
- **Multi-skill bundles.** Out of scope for v1. A "skill pack"
  format that ships several skills in one tarball can come in
  later as v2 with a `skills/` directory in the bundle plus a
  manifest list. Designed for; not implemented.
- **Engine-wide minimum version enforcement.** v1 records
  `min_metis_version` but does not block install. When METIS
  ships a tagged release, the comparison becomes load-bearing
  and should hard-fail.
