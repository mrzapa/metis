from __future__ import annotations

import json

import pytest

from metis_app.services import nyx_catalog as nyx_catalog_module
from metis_app.services.nyx_catalog import CuratedNyxComponent, NyxCatalogBroker
from metis_app.services.nyx_catalog import load_curated_nyx_components
from metis_app.services.nyx_catalog import load_nyx_snapshot_component_details
from metis_app.services.nyx_catalog import normalize_component_name


@pytest.fixture(autouse=True)
def reset_nyx_catalog_state() -> None:
    nyx_catalog_module.load_curated_nyx_components.cache_clear()
    nyx_catalog_module.load_nyx_snapshot_component_details.cache_clear()
    nyx_catalog_module.load_optional_nyx_snapshot_component_details.cache_clear()
    nyx_catalog_module._DEFAULT_BROKER = None
    yield
    nyx_catalog_module.load_curated_nyx_components.cache_clear()
    nyx_catalog_module.load_nyx_snapshot_component_details.cache_clear()
    nyx_catalog_module.load_optional_nyx_snapshot_component_details.cache_clear()
    nyx_catalog_module._DEFAULT_BROKER = None


@pytest.mark.parametrize(
    ("component_name", "expected"),
    [
        ("music-player", "music-player"),
        ("Music-Player", "music-player"),
        ("@nyx/Music-Player", "music-player"),
        ("NyX/Music-Player", "music-player"),
        ("https://nyxui.com/r/Music-Player.json", "music-player"),
        ("HTTPS://NYXUI.COM/R/Music-Player.JSON?tab=demo", "music-player"),
    ],
)
def test_normalize_component_name_returns_canonical_lowercase_slug(
    component_name: str,
    expected: str,
) -> None:
    assert normalize_component_name(component_name) == expected


def test_load_curated_components_defaults_to_packaged_snapshot() -> None:
    curated = nyx_catalog_module.load_curated_nyx_components()

    assert curated["glow-card"] == CuratedNyxComponent(
        description="Interactive card with glow-based accent effects.",
        required_dependencies=("clsx", "tailwind-merge"),
    )
    assert curated["music-player"] == CuratedNyxComponent(
        description="Compact music player interface.",
        required_dependencies=("lucide-react",),
    )


def test_packaged_snapshot_preserves_preview_only_review_metadata() -> None:
    snapshot_details = load_nyx_snapshot_component_details()

    marquee = snapshot_details["marquee"]

    assert marquee.review_status == nyx_catalog_module.NYX_REVIEW_STATUS_PREVIEW
    assert marquee.previewable is True
    assert marquee.installable is False
    assert any(
        "invalid package specifiers: .." in issue for issue in marquee.audit_issues
    )


def test_load_curated_components_filters_preview_only_entries_from_snapshot(tmp_path) -> None:
    snapshot_path = tmp_path / "nyx-snapshot.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "components": {
                    "glow-card": {
                        "component_name": "glow-card",
                        "description": "Glow card.",
                        "curated_description": "Interactive card.",
                        "required_dependencies": ["clsx"],
                        "installable": True,
                        "previewable": True,
                        "review_status": "installable",
                    },
                    "marquee": {
                        "component_name": "marquee",
                        "description": "Marquee strip.",
                        "curated_description": "Preview only marquee.",
                        "required_dependencies": [],
                        "installable": False,
                        "previewable": True,
                        "review_status": "preview",
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    curated = load_curated_nyx_components(snapshot_path)

    assert curated == {
        "glow-card": CuratedNyxComponent(
            description="Interactive card.",
            required_dependencies=("clsx",),
        )
    }


def test_default_broker_uses_packaged_snapshot_without_live_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetch_calls: list[str] = []

    def fail_fetch(url: str) -> dict[str, object]:
        fetch_calls.append(url)
        raise AssertionError(f"Unexpected live Nyx fetch: {url}")

    monkeypatch.setattr(nyx_catalog_module, "_default_fetch_json", fail_fetch)

    broker = NyxCatalogBroker()
    search_result = broker.search_catalog(query="glow", limit=5)
    detail = broker.get_component_detail("glow-card")

    assert search_result.matched == 1
    assert search_result.items[0].component_name == "glow-card"
    assert detail.component_name == "glow-card"
    assert detail.install_target == "@nyx/glow-card"
    assert detail.schema_url == "https://ui.shadcn.com/schema/registry-item.json"
    assert detail.targets == ("components/ui/glow-card.tsx",)
    assert detail.files[0].content_bytes > 0
    assert fetch_calls == []


def test_default_broker_exposes_preview_only_snapshot_components_without_live_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetch_calls: list[str] = []

    def fail_fetch(url: str) -> dict[str, object]:
        fetch_calls.append(url)
        raise AssertionError(f"Unexpected live Nyx fetch: {url}")

    monkeypatch.setattr(nyx_catalog_module, "_default_fetch_json", fail_fetch)

    broker = NyxCatalogBroker()
    search_result = broker.search_catalog(query="marquee", limit=5)
    detail = broker.get_component_detail("marquee")

    assert search_result.total >= 12
    assert search_result.matched == 1
    assert search_result.items[0].component_name == "marquee"
    assert search_result.items[0].previewable is True
    assert search_result.items[0].installable is False
    assert detail.component_name == "marquee"
    assert detail.review_status == nyx_catalog_module.NYX_REVIEW_STATUS_PREVIEW
    assert detail.previewable is True
    assert detail.installable is False
    assert fetch_calls == []


def test_custom_curated_catalog_path_overrides_snapshot_metadata_without_live_fetch(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    curated_path = tmp_path / "nyx-curated-catalog.json"
    curated_path.write_text(
        json.dumps(
            {
                "glow-card": {
                    "description": "Local curated glow override.",
                    "requiredDependencies": ["clsx"],
                }
            }
        ),
        encoding="utf-8",
    )

    def fail_fetch(url: str) -> dict[str, object]:
        raise AssertionError(f"Unexpected live Nyx fetch: {url}")

    monkeypatch.setenv("METIS_NYX_CATALOG_PATH", str(curated_path))
    monkeypatch.setattr(nyx_catalog_module, "_default_fetch_json", fail_fetch)

    broker = NyxCatalogBroker()
    detail = broker.get_component_detail("glow-card")

    assert detail.curated_description == "Local curated glow override."
    assert detail.required_dependencies == ("clsx",)
    assert detail.description == "A glow card that that provide several effects."
    assert detail.targets == ("components/ui/glow-card.tsx",)


def test_component_detail_normalizes_and_caches_registry_metadata() -> None:
    fetch_calls: list[str] = []

    def fake_fetch_json(url: str) -> dict[str, object]:
        fetch_calls.append(url)
        return {
            "$schema": "https://ui.shadcn.com/schema/registry-item.json",
            "name": "@nyx/Music-Player",
            "type": "registry:ui",
            "title": "Music Player",
            "description": "A music player that that provide several effects.",
            "dependencies": ["lucide-react", "lucide-react", "  "],
            "devDependencies": ["@types/react", "@types/react"],
            "registryDependencies": ["button", "button", ""],
            "files": [
                {
                    "path": "registry/ui/music-player.tsx",
                    "type": "registry:ui",
                    "target": "components/ui/music-player.tsx",
                    "content": "export const MusicPlayer = () => null;",
                },
                {
                    "path": "lib/utils.ts",
                    "type": "registry:lib",
                    "target": "",
                    "content": "export const helper = true;",
                },
            ],
        }

    broker = NyxCatalogBroker(
        curated_components={
            "music-player": CuratedNyxComponent(
                description="Compact music player interface.",
                required_dependencies=("lucide-react",),
            )
        },
        fetch_json=fake_fetch_json,
    )

    detail = broker.get_component_detail("@nyx/Music-Player")
    cached_detail = broker.get_component_detail("NyX/Music-Player")

    assert detail is cached_detail
    assert detail.component_name == "music-player"
    assert detail.dependencies == ("lucide-react",)
    assert detail.dev_dependencies == ("@types/react",)
    assert detail.registry_dependencies == ("button",)
    assert detail.required_dependencies == ("lucide-react",)
    assert detail.file_count == 2
    assert detail.targets == ("components/ui/music-player.tsx",)
    assert detail.files[0].content_bytes == len(
        "export const MusicPlayer = () => null;".encode("utf-8")
    )
    assert fetch_calls == ["https://nyxui.com/r/music-player.json"]


def test_search_catalog_filters_matches_and_reuses_cached_details() -> None:
    fetch_calls: list[str] = []
    registry_items = {
        "glow-card": {
            "$schema": "https://ui.shadcn.com/schema/registry-item.json",
            "name": "glow-card",
            "type": "registry:ui",
            "title": "Glow Card",
            "description": "A glow card that that provide several effects.",
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
        "image-scanner": {
            "$schema": "https://ui.shadcn.com/schema/registry-item.json",
            "name": "image-scanner",
            "type": "registry:ui",
            "title": "Image Scanner",
            "description": "Animated scanline treatment for media blocks.",
            "dependencies": ["motion", "lucide-react"],
            "files": [
                {
                    "path": "registry/ui/image-scanner.tsx",
                    "type": "registry:ui",
                    "target": "components/ui/image-scanner.tsx",
                    "content": "export function ImageScanner() {}",
                }
            ],
        },
    }

    def fake_fetch_json(url: str) -> dict[str, object]:
        fetch_calls.append(url)
        component_name = url.rsplit("/", 1)[-1].replace(".json", "")
        return registry_items[component_name]

    broker = NyxCatalogBroker(
        curated_components={
            "glow-card": CuratedNyxComponent(
                description="Interactive card with glow-based accent effects.",
                required_dependencies=("clsx", "tailwind-merge"),
            ),
            "image-scanner": CuratedNyxComponent(
                description="Animated scanline treatment for media blocks.",
                required_dependencies=("lucide-react", "motion"),
            ),
        },
        fetch_json=fake_fetch_json,
    )

    search_result = broker.search_catalog(query="glow", limit=5)
    repeated_result = broker.search_catalog(query="scanner", limit=5)

    assert search_result.total == 2
    assert search_result.matched == 1
    assert search_result.items[0].component_name == "glow-card"
    assert repeated_result.matched == 1
    assert repeated_result.items[0].component_name == "image-scanner"
    assert fetch_calls == [
        "https://nyxui.com/r/glow-card.json",
        "https://nyxui.com/r/image-scanner.json",
    ]