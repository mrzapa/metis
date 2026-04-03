from __future__ import annotations

import json

import pytest

from metis_app.services.nyx_catalog_refresh import build_nyx_catalog_snapshot
from metis_app.services.nyx_catalog_refresh import build_nyx_registry_fetcher
from metis_app.services.nyx_catalog_refresh import load_nyx_review_manifest
from metis_app.services.nyx_catalog_refresh import refresh_nyx_catalog_snapshot


def _write_json(path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_refresh_snapshot_writes_reviewed_and_preview_components(tmp_path) -> None:
    review_path = tmp_path / "nyx-review.json"
    source_path = tmp_path / "nyx-source.json"
    snapshot_path = tmp_path / "nyx-snapshot.json"

    _write_json(
        review_path,
        {
            "source": "nyx_registry",
            "source_repo": "https://github.com/MihirJaiswal/nyxui",
            "registry_url_template": "https://nyxui.com/r/{name}.json",
            "schema_url": "https://ui.shadcn.com/schema/registry-item.json",
            "install_target_policy": {
                "policy_name": "metis_nyx_targets_v1",
                "allowed_target_prefixes": ["components/", "hooks/", "lib/"],
                "allowed_targetless_types": ["registry:lib"],
            },
            "components": {
                "glow-card": {
                    "review_status": "installable",
                    "description": "Interactive card with glow-based accent effects.",
                    "required_dependencies": ["clsx", "tailwind-merge"],
                },
                "marquee": {
                    "review_status": "preview",
                    "description": "Looping marquee strip for logos.",
                    "required_dependencies": [],
                },
            },
        },
    )
    _write_json(
        source_path,
        {
            "components": {
                "glow-card": {
                    "$schema": "https://ui.shadcn.com/schema/registry-item.json",
                    "name": "glow-card",
                    "type": "registry:ui",
                    "title": "Glow Card",
                    "description": "Upstream glow card description.",
                    "dependencies": ["clsx", "tailwind-merge"],
                    "files": [
                        {
                            "path": "registry/ui/glow-card.tsx",
                            "type": "registry:ui",
                            "target": "components/ui/glow-card.tsx",
                            "content": "export function GlowCard() {}",
                        }
                    ],
                },
                "marquee": {
                    "$schema": "https://ui.shadcn.com/schema/registry-item.json",
                    "name": "marquee",
                    "type": "registry:ui",
                    "title": "Marquee",
                    "description": "Marquee strip.",
                    "dependencies": ["motion", ".."],
                    "files": [
                        {
                            "path": "registry/ui/marquee.tsx",
                            "type": "registry:ui",
                            "target": "components/ui/marquee.tsx",
                            "content": "export function Marquee() {}",
                        }
                    ],
                },
            }
        },
    )

    result = refresh_nyx_catalog_snapshot(
        review_manifest_path=review_path,
        snapshot_path=snapshot_path,
        source_path=source_path,
    )

    assert result.previewable_components == ("glow-card", "marquee")
    assert result.installable_components == ("glow-card",)
    assert result.blocking_installable_components == ()

    written_snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert written_snapshot["installable_component_count"] == 1
    assert written_snapshot["previewable_component_count"] == 2
    assert written_snapshot["components"]["glow-card"]["installable"] is True
    assert written_snapshot["components"]["marquee"]["review_status"] == "preview"
    assert written_snapshot["components"]["marquee"]["previewable"] is True
    assert written_snapshot["components"]["marquee"]["installable"] is False
    assert written_snapshot["components"]["marquee"]["audit_issues"] == [
        "marquee: dependencies contains invalid package specifiers: .."
    ]


def test_refresh_snapshot_rejects_installable_components_with_unsafe_targets(tmp_path) -> None:
    review_path = tmp_path / "nyx-review.json"
    source_path = tmp_path / "nyx-source.json"
    snapshot_path = tmp_path / "nyx-snapshot.json"

    _write_json(
        review_path,
        {
            "components": {
                "danger-card": {
                    "review_status": "installable",
                    "description": "Unsafe card.",
                    "required_dependencies": [],
                }
            }
        },
    )
    _write_json(
        source_path,
        {
            "components": {
                "danger-card": {
                    "name": "danger-card",
                    "type": "registry:ui",
                    "title": "Danger Card",
                    "description": "Unsafe target.",
                    "files": [
                        {
                            "path": "registry/ui/danger-card.tsx",
                            "type": "registry:ui",
                            "target": "../components/ui/danger-card.tsx",
                            "content": "export function DangerCard() {}",
                        }
                    ],
                }
            }
        },
    )

    with pytest.raises(RuntimeError, match="danger-card"):
        refresh_nyx_catalog_snapshot(
            review_manifest_path=review_path,
            snapshot_path=snapshot_path,
            source_path=source_path,
        )

    assert not snapshot_path.exists()


def test_build_snapshot_uses_local_source_fetcher_for_offline_refreshes(tmp_path) -> None:
    review_path = tmp_path / "nyx-review.json"
    source_path = tmp_path / "nyx-source.json"

    _write_json(
        review_path,
        {
            "components": {
                "glow-card": {
                    "review_status": "installable",
                    "description": "Interactive card.",
                    "required_dependencies": ["clsx"],
                }
            }
        },
    )
    _write_json(
        source_path,
        {
            "components": {
                "glow-card": {
                    "name": "glow-card",
                    "type": "registry:ui",
                    "title": "Glow Card",
                    "description": "Offline source copy.",
                    "dependencies": ["clsx"],
                    "files": [
                        {
                            "path": "registry/ui/glow-card.tsx",
                            "type": "registry:ui",
                            "target": "components/ui/glow-card.tsx",
                            "content": "export function GlowCard() {}",
                        }
                    ],
                }
            }
        },
    )

    manifest = load_nyx_review_manifest(review_path)
    fetcher = build_nyx_registry_fetcher(source_path=source_path)
    result = build_nyx_catalog_snapshot(manifest, fetch_json=fetcher)

    assert result.installable_components == ("glow-card",)
    assert result.payload["components"]["glow-card"]["description"] == "Offline source copy."
    assert result.payload["components"]["glow-card"]["install_path_safe"] is True