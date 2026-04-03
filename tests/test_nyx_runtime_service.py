from __future__ import annotations

from dataclasses import replace
import pathlib
import subprocess

from metis_app.services.nyx_catalog import (
    CuratedNyxComponent,
    NyxCatalogBroker,
    NyxCatalogComponentDetail,
    NyxCatalogFileSummary,
)
from metis_app.services.nyx_install_executor import (
    NyxInstallActionExecutionError,
    execute_nyx_install_action,
    revalidate_nyx_install_action,
)
from metis_app.services.nyx_runtime import build_nyx_install_actions, build_nyx_runtime_context


def _make_broker() -> NyxCatalogBroker:
    registry_items = {
        "animated-grainy-bg": {
            "$schema": "https://ui.shadcn.com/schema/registry-item.json",
            "name": "animated-grainy-bg",
            "type": "registry:ui",
            "title": "Animated Grainy Background",
            "description": "Animated gradient background surface.",
            "dependencies": ["motion"],
            "files": [
                {
                    "path": "registry/ui/animated-grainy-bg.tsx",
                    "type": "registry:ui",
                    "target": "components/ui/animated-grainy-bg.tsx",
                    "content": "export function AnimatedGrainyBg() {}",
                }
            ],
        },
        "apple-glass-effect": {
            "$schema": "https://ui.shadcn.com/schema/registry-item.json",
            "name": "apple-glass-effect",
            "type": "registry:ui",
            "title": "Apple Glass Effect",
            "description": "Glassmorphism container with motion-based depth.",
            "dependencies": ["motion"],
            "files": [
                {
                    "path": "registry/ui/apple-glass-effect.tsx",
                    "type": "registry:ui",
                    "target": "components/ui/apple-glass-effect.tsx",
                    "content": "export function AppleGlassEffect() {}",
                }
            ],
        },
        "glow-card": {
            "$schema": "https://ui.shadcn.com/schema/registry-item.json",
            "name": "glow-card",
            "type": "registry:ui",
            "title": "Glow Card",
            "description": "Interactive card with glow-based accent effects.",
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
        "github-repo-card": {
            "$schema": "https://ui.shadcn.com/schema/registry-item.json",
            "name": "github-repo-card",
            "type": "registry:ui",
            "title": "GitHub Repo Card",
            "description": "Repository card with language and star metadata.",
            "dependencies": ["lucide-react"],
            "files": [
                {
                    "path": "registry/ui/github-repo-card.tsx",
                    "type": "registry:ui",
                    "target": "components/ui/github-repo-card.tsx",
                    "content": "export function GitHubRepoCard() {}",
                }
            ],
        },
    }

    def fake_fetch_json(url: str) -> dict[str, object]:
        component_name = url.rsplit("/", 1)[-1].replace(".json", "")
        return registry_items[component_name]

    return NyxCatalogBroker(
        curated_components={
            "animated-grainy-bg": CuratedNyxComponent(
                description="Animated gradient background surface.",
                required_dependencies=("motion",),
            ),
            "apple-glass-effect": CuratedNyxComponent(
                description="Glassmorphism container with motion-based depth.",
                required_dependencies=("motion",),
            ),
            "glow-card": CuratedNyxComponent(
                description="Interactive card with glow-based accent effects.",
                required_dependencies=("clsx", "tailwind-merge"),
            ),
            "github-repo-card": CuratedNyxComponent(
                description="Repository card with language and star metadata.",
                required_dependencies=("lucide-react",),
            ),
        },
        fetch_json=fake_fetch_json,
    )


def test_build_nyx_runtime_context_filters_generic_card_overlap() -> None:
    context = build_nyx_runtime_context(
        "Design a frosted glass panel with a glowing card.",
        _make_broker(),
    )

    assert context is not None
    payload = context.to_payload()
    selected_names = [item["component_name"] for item in payload["selected_components"]]
    assert selected_names == ["apple-glass-effect", "glow-card"]
    assert "github-repo-card" not in selected_names

    actions = build_nyx_install_actions(
        run_id="run-nyx-broad-prompt",
        settings={"nyx_runtime": payload},
        artifacts=context.to_artifacts(),
        broker=_make_broker(),
    )

    assert len(actions) == 1
    assert actions[0]["proposal"]["component_names"] == ["apple-glass-effect", "glow-card"]


def test_build_nyx_runtime_context_resolves_components_and_artifacts() -> None:
    context = build_nyx_runtime_context(
        "Design a frosted glass hero with an animated grainy background and a glowing card.",
        _make_broker(),
    )

    assert context is not None
    payload = context.to_payload()
    assert payload["schema_version"] == "1.0"
    assert payload["intent_type"] == "ui_layout_request"
    selected_names = [item["component_name"] for item in payload["selected_components"]]
    assert set(selected_names) == {
        "animated-grainy-bg",
        "apple-glass-effect",
        "glow-card",
    }

    artifacts = context.to_artifacts()
    assert [artifact["type"] for artifact in artifacts] == [
        "nyx_component_selection",
        "nyx_install_plan",
        "nyx_dependency_report",
    ]
    selection_payload = artifacts[0]["payload"]
    assert selection_payload["selected_components"][0]["registry_url"] == "https://nyxui.com/r/animated-grainy-bg.json"
    assert {
        item["install_target"] for item in selection_payload["selected_components"]
    } == {
        "@nyx/animated-grainy-bg",
        "@nyx/apple-glass-effect",
        "@nyx/glow-card",
    }
    dependency_payload = artifacts[2]["payload"]
    assert dependency_payload["groups"]["required"][0]["dependency_type"] == "required"


def test_build_nyx_runtime_context_skips_unrelated_prompts() -> None:
    context = build_nyx_runtime_context(
        "Explain how vector embeddings improve retrieval quality.",
        _make_broker(),
    )

    assert context is None


def test_build_nyx_install_actions_emits_stable_trace_ready_contract() -> None:
    broker = _make_broker()
    context = build_nyx_runtime_context(
        "Design a frosted glass hero with an animated grainy background and a glowing card.",
        broker,
    )

    assert context is not None

    settings = {"nyx_runtime": context.to_payload()}
    actions = build_nyx_install_actions(
        run_id="run-nyx-action",
        settings=settings,
        artifacts=context.to_artifacts(),
        broker=broker,
    )
    repeated = build_nyx_install_actions(
        run_id="run-nyx-action",
        settings=settings,
        artifacts=context.to_artifacts(),
        broker=broker,
    )

    assert len(actions) == 1
    action = actions[0]
    assert action["action_type"] == "nyx_install"
    assert action["action_id"] == repeated[0]["action_id"]
    assert action["payload"]["action_id"] == action["action_id"]
    assert action["payload"]["proposal_token"] == action["proposal"]["proposal_token"]
    assert action["run_action_endpoint"] == "/v1/runs/run-nyx-action/actions"
    assert action["proposal"]["component_count"] == 3
    assert set(action["proposal"]["component_names"]) == {
        "animated-grainy-bg",
        "apple-glass-effect",
        "glow-card",
    }
    assert all(component["installable"] is True for component in action["proposal"]["components"])


def test_build_nyx_install_actions_skips_preview_only_components() -> None:
    class _PreviewOnlyBroker:
        def get_component_detail(self, component_name: str) -> NyxCatalogComponentDetail:
            return NyxCatalogComponentDetail(
                component_name=component_name,
                title="Marquee",
                description="Preview only marquee.",
                curated_description="Preview only marquee.",
                component_type="registry:ui",
                install_target=f"@nyx/{component_name}",
                registry_url=f"https://nyxui.com/r/{component_name}.json",
                schema_url="https://ui.shadcn.com/schema/registry-item.json",
                source="nyx_registry",
                source_repo="https://github.com/MihirJaiswal/nyxui",
                required_dependencies=(),
                dependencies=("motion",),
                dev_dependencies=(),
                registry_dependencies=(),
                file_count=1,
                targets=("components/ui/marquee.tsx",),
                files=(
                    NyxCatalogFileSummary(
                        path="registry/ui/marquee.tsx",
                        file_type="registry:ui",
                        target="components/ui/marquee.tsx",
                        content_bytes=64,
                    ),
                ),
                review_status="preview",
                previewable=True,
                installable=False,
                install_path_policy="metis_nyx_targets_v1",
                install_path_safe=True,
                install_path_issues=(),
                audit_issues=("marquee: preview only",),
            )

    actions = build_nyx_install_actions(
        run_id="run-preview",
        settings={
            "nyx_runtime": {
                "schema_version": "1.0",
                "query": "Preview the marquee treatment.",
                "intent_type": "ui_layout_request",
                "matched_signals": ["explicit_nyx"],
                "selected_components": [{"component_name": "marquee"}],
            }
        },
        artifacts=[
            {
                "type": "nyx_component_selection",
                "payload": {"selected_components": [{"component_name": "marquee"}]},
            }
        ],
        broker=_PreviewOnlyBroker(),
    )

    assert actions == []


def _build_glow_card_action() -> dict[str, object]:
    broker = _make_broker()
    actions = build_nyx_install_actions(
        run_id="run-glow-card",
        settings={
            "nyx_runtime": {
                "schema_version": "1.0",
                "query": "Design a glowing card.",
                "intent_type": "interface_pattern_selection",
                "matched_signals": ["explicit_nyx", "pattern:card"],
                "selected_components": [{"component_name": "glow-card"}],
            }
        },
        artifacts=[
            {
                "type": "nyx_component_selection",
                "payload": {"selected_components": [{"component_name": "glow-card"}]},
            }
        ],
        broker=broker,
    )

    assert len(actions) == 1
    return actions[0]


def test_revalidate_nyx_install_action_accepts_current_reviewed_snapshot() -> None:
    action = _build_glow_card_action()

    result = revalidate_nyx_install_action(
        run_id="run-glow-card",
        persisted_action=action,
        action_id=str(action["action_id"]),
        proposal_token=str(action["proposal"]["proposal_token"]),
        requested_component_names=["glow-card"],
        broker=_make_broker(),
    )

    assert result.action_id == action["action_id"]
    assert result.proposal_token == action["proposal"]["proposal_token"]
    assert result.component_names == ("glow-card",)
    assert result.component_count == 1
    assert result.proposal["component_names"] == ["glow-card"]


def test_revalidate_nyx_install_action_fails_when_snapshot_digest_changes() -> None:
    action = _build_glow_card_action()

    class _ChangedBroker:
        def __init__(self) -> None:
            self._broker = _make_broker()

        def get_component_detail(self, component_name: str) -> NyxCatalogComponentDetail:
            detail = self._broker.get_component_detail(component_name)
            return replace(
                detail,
                description="Changed reviewed description.",
                curated_description="Changed reviewed description.",
            )

    try:
        revalidate_nyx_install_action(
            run_id="run-glow-card",
            persisted_action=action,
            action_id=str(action["action_id"]),
            proposal_token=str(action["proposal"]["proposal_token"]),
            requested_component_names=["glow-card"],
            broker=_ChangedBroker(),
        )
    except NyxInstallActionExecutionError as exc:
        assert exc.code == "stale_proposal"
    else:
        raise AssertionError("revalidation should fail when the reviewed snapshot digest changes")


def test_revalidate_nyx_install_action_classifies_unsafe_snapshot_state_as_unsafe() -> None:
    action = _build_glow_card_action()

    class _UnsafeBroker:
        def __init__(self) -> None:
            self._broker = _make_broker()

        def get_component_detail(self, component_name: str) -> NyxCatalogComponentDetail:
            detail = self._broker.get_component_detail(component_name)
            return replace(
                detail,
                installable=False,
                install_path_safe=False,
                install_path_issues=(
                    "glow-card: ../components/ui/glow-card.tsx cannot traverse parent directories",
                ),
            )

    try:
        revalidate_nyx_install_action(
            run_id="run-glow-card",
            persisted_action=action,
            action_id=str(action["action_id"]),
            proposal_token=str(action["proposal"]["proposal_token"]),
            requested_component_names=["glow-card"],
            broker=_UnsafeBroker(),
        )
    except NyxInstallActionExecutionError as exc:
        assert exc.code == "unsafe_component"
        assert exc.metadata["install_path_issues"] == [
            "glow-card: ../components/ui/glow-card.tsx cannot traverse parent directories"
        ]
    else:
        raise AssertionError("unsafe reviewed components must fail as unsafe")


def test_execute_nyx_install_action_runs_existing_safe_installer(tmp_path) -> None:
    action = _build_glow_card_action()
    web_app_dir = tmp_path / "apps" / "metis-web"
    scripts_dir = web_app_dir / "scripts"
    scripts_dir.mkdir(parents=True)
    (web_app_dir / "package.json").write_text(
        '{"scripts":{"ui:add:nyx":"node ./scripts/add-nyx-component.mjs"}}',
        encoding="utf-8",
    )
    (scripts_dir / "add-nyx-component.mjs").write_text("console.log('ok');\n", encoding="utf-8")

    calls: list[dict[str, object]] = []

    def fake_run(command, *, cwd, capture_output, text, encoding, errors, check, input, timeout):
        calls.append(
            {
                "command": command,
                "cwd": cwd,
                "capture_output": capture_output,
                "text": text,
                "encoding": encoding,
                "errors": errors,
                "check": check,
                "input": input,
                "timeout": timeout,
            }
        )
        return subprocess.CompletedProcess(command, 0, stdout="installed glow-card", stderr="")

    result = execute_nyx_install_action(
        run_id="run-glow-card",
        persisted_action=action,
        action_id=str(action["action_id"]),
        proposal_token=str(action["proposal"]["proposal_token"]),
        requested_component_names=["glow-card"],
        broker=_make_broker(),
        web_app_dir=web_app_dir,
        which=lambda name: "node-bin" if name == "node" else None,
        subprocess_run=fake_run,
    )

    assert calls == [
        {
            "command": [
                "node-bin",
                str(pathlib.Path(web_app_dir / "scripts" / "add-nyx-component.mjs")),
                "--",
                "glow-card",
            ],
            "cwd": str(web_app_dir),
            "capture_output": True,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "check": False,
            "input": "n\n" * 64,
            "timeout": 300,
        }
    ]
    assert result.execution_status == "completed"
    assert result.component_names == ("glow-card",)
    assert result.returncode == 0
    assert result.stdout_excerpt == "installed glow-card"


def test_execute_nyx_install_action_fails_closed_on_installer_error(tmp_path) -> None:
    action = _build_glow_card_action()
    web_app_dir = tmp_path / "apps" / "metis-web"
    scripts_dir = web_app_dir / "scripts"
    scripts_dir.mkdir(parents=True)
    (web_app_dir / "package.json").write_text(
        '{"scripts":{"ui:add:nyx":"node ./scripts/add-nyx-component.mjs"}}',
        encoding="utf-8",
    )
    (scripts_dir / "add-nyx-component.mjs").write_text("console.error('boom');\n", encoding="utf-8")

    def fake_run(command, *, cwd, capture_output, text, encoding, errors, check, input, timeout):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="installer exploded")

    try:
        execute_nyx_install_action(
            run_id="run-glow-card",
            persisted_action=action,
            action_id=str(action["action_id"]),
            proposal_token=str(action["proposal"]["proposal_token"]),
            requested_component_names=["glow-card"],
            broker=_make_broker(),
            web_app_dir=web_app_dir,
            which=lambda name: "node-bin" if name == "node" else None,
            subprocess_run=fake_run,
        )
    except NyxInstallActionExecutionError as exc:
        assert exc.code == "installer_failed"
        assert exc.metadata["returncode"] == 1
        assert exc.metadata["stderr_excerpt"] == "installer exploded"
    else:
        raise AssertionError("installer failures must fail closed")