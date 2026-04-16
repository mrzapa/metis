"""Profile repository compatible with the legacy monolith profile format."""

from __future__ import annotations

from dataclasses import replace
import json
import logging
import pathlib
import re

from metis_app.models.parity_types import AgentProfile

log = logging.getLogger(__name__)

_HERE = pathlib.Path(__file__).resolve().parent
_PACKAGE_ROOT = _HERE.parent
_REPO_ROOT = _PACKAGE_ROOT.parent
_DEFAULT_PROFILES_DIR = _REPO_ROOT / "profiles"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "").strip()).strip("_")
    return slug or "profile"


class ProfileRepository:
    """Load built-in and file-backed profiles using the monolith JSON shape."""

    BUILTIN_PROFILES: dict[str, AgentProfile] = {
        "Built-in: Default": AgentProfile(name="Default", mode_default="Q&A"),
        "Built-in: Tutor": AgentProfile(
            name="Tutor",
            mode_default="Tutor",
            style_template="Teach concept first, then short quiz and optional flashcards.",
            citation_policy="Cite each factual teaching block using standard citation format.",
            retrieval_strategy={"retrieve_k": 24, "final_k": 6, "mmr_lambda": 0.55},
            iteration_strategy={"agentic_mode": True, "max_iterations": 2},
            retrieval_mode="hierarchical",
            digest_usage=True,
        ),
        "Built-in: Summary": AgentProfile(
            name="Summary",
            mode_default="Summary",
            style_template="Deliver concise key ideas with timeline-aware synthesis.",
            citation_policy="Each major section should include at least one supporting citation.",
            retrieval_strategy={"retrieve_k": 20, "final_k": 4, "mmr_lambda": 0.6},
            retrieval_mode="hierarchical",
            digest_usage=True,
        ),
        "Built-in: Research": AgentProfile(
            name="Research",
            mode_default="Research",
            style_template="Structure output as claims, arguments, and counterclaims.",
            citation_policy="Every claim and counterclaim requires citation.",
            retrieval_strategy={"retrieve_k": 30, "final_k": 7, "mmr_lambda": 0.4},
            iteration_strategy={"agentic_mode": True, "max_iterations": 3},
            retrieval_mode="hierarchical",
            digest_usage=True,
        ),
        "Built-in: Evidence Pack": AgentProfile(
            name="Evidence Pack",
            mode_default="Evidence Pack",
            style_template="Produce a courtroom-ready packet with chronology and incidents.",
            citation_policy="Use [S#] citations for every factual line.",
            retrieval_strategy={"retrieve_k": 35, "final_k": 10, "mmr_lambda": 0.5},
            iteration_strategy={"agentic_mode": True, "max_iterations": 3},
            retrieval_mode="hierarchical",
            digest_usage=True,
        ),
    }

    def __init__(self, profiles_dir: str | pathlib.Path | None = None) -> None:
        self.profiles_dir = pathlib.Path(profiles_dir or _DEFAULT_PROFILES_DIR)

    def ensure_profiles_dir(self) -> pathlib.Path:
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        return self.profiles_dir

    def list_labels(self) -> list[str]:
        labels = list(self.BUILTIN_PROFILES.keys())
        labels.extend(self._file_labels())
        return labels

    def get_profile(self, label: str) -> AgentProfile:
        normalized = str(label or "").strip()
        if normalized in self.BUILTIN_PROFILES:
            return replace(self.BUILTIN_PROFILES[normalized])
        path = self.path_from_label(normalized)
        if path and path.exists():
            try:
                return self.load_file(path)
            except (OSError, json.JSONDecodeError) as exc:
                log.warning("Could not load profile from %s: %s", path, exc)
        return replace(self.BUILTIN_PROFILES["Built-in: Default"])

    def load_file(self, path: str | pathlib.Path) -> AgentProfile:
        payload = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        profile = AgentProfile.from_payload(payload if isinstance(payload, dict) else {})
        if not profile.name:
            profile.name = pathlib.Path(path).stem
        return profile

    def save_profile(
        self,
        profile: AgentProfile,
        *,
        target_path: str | pathlib.Path | None = None,
    ) -> pathlib.Path:
        self.ensure_profiles_dir()
        path = (
            pathlib.Path(target_path)
            if target_path is not None
            else self.profiles_dir / f"{_slugify(profile.name)}.json"
        )
        path.write_text(
            json.dumps(profile.to_payload(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def duplicate_profile(
        self,
        label: str,
        *,
        target_path: str | pathlib.Path | None = None,
        new_name: str | None = None,
    ) -> pathlib.Path:
        source = self.get_profile(label)
        clone = replace(source)
        clone.name = str(new_name or f"{source.name} Copy").strip()
        return self.save_profile(clone, target_path=target_path)

    def label_for_path(self, path: str | pathlib.Path) -> str:
        return f"File: {pathlib.Path(path).name}"

    def path_from_label(self, label: str) -> pathlib.Path | None:
        text = str(label or "").strip()
        if not text.startswith("File: "):
            return None
        return self.profiles_dir / text.replace("File: ", "", 1)

    def _file_labels(self) -> list[str]:
        self.ensure_profiles_dir()
        labels: list[str] = []
        for path in sorted(self.profiles_dir.glob("*.json")):
            labels.append(self.label_for_path(path))
        return labels
