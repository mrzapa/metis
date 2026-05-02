"""M16 personal-eval persistence package.

Phase 2 surface: a dedicated SQLite store (``evals.db``) with the
three-table schema locked by ADR 0017, an ``EvalTask`` dataclass that
mirrors the on-disk seed shape produced by
``ArtifactConverter.export_as_eval``, and a content-addressed
``generation_id`` so M18's LoRA gate can compare candidate vs current
companions across the same surface used by interactive runs.

The runner (Phase 3), grading lanes (ADR 0016), and report surface
(Phase 5) layer on top of this package — none of them ship in Phase 2.
"""

from .corpus import (
    EvalTask,
    eval_task_from_jsonl_row,
    import_seed_jsonl,
)
from .generation import (
    GENERATION_SETTINGS,
    bump_if_needed,
    current_generation_id,
)
from .store import (
    DEFAULT_DB_ENV_VAR,
    EvalGeneration,
    EvalRun,
    EvalStore,
    EvalTaskRow,
    get_default_store,
    reset_default_store_for_tests,
)

__all__ = [
    "DEFAULT_DB_ENV_VAR",
    "EvalGeneration",
    "EvalRun",
    "EvalStore",
    "EvalTask",
    "EvalTaskRow",
    "GENERATION_SETTINGS",
    "bump_if_needed",
    "current_generation_id",
    "eval_task_from_jsonl_row",
    "get_default_store",
    "import_seed_jsonl",
    "reset_default_store_for_tests",
]
