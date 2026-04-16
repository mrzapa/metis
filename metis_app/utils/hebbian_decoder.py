"""metis_app.utils.hebbian_decoder — Online channel↔node association table.

Keeps a persistent, continuously-updated association weight between
SpatialFingerprint channels (from ``spatial_encoder``) and brain_graph
node ids.  When a query's fingerprint activates a channel and a node is
surfaced as the answer source, the (channel, node) weight increments;
weights decay over time so stale associations don't dominate.

At retrieval time, the table is consulted to re-rank candidate nodes:
``boost()`` adds a small, Hebbian-derived bonus to nodes whose historic
association with the query's active channels is strong.

Derived from the ``LearnedDecoder`` concept in
`4R7I5T/CL1_LLM_Encoder/encoder_v3.py`, adapted from per-token LLM
decoding to per-node retrieval ranking.
"""

from __future__ import annotations

import json
import logging
import pathlib
import threading
from typing import Iterable

_LOG = logging.getLogger(__name__)


class HebbianAssociations:
    """Persistent (channel → node → weight) association table.

    Parameters
    ----------
    storage_path:
        JSON file used for durable persistence.  ``None`` keeps the table
        in memory only (useful for tests).
    decay:
        Multiplicative weight decay applied at every ``update`` call.
        Values very close to ``1.0`` effectively disable decay; anything
        below ``0.9`` is aggressive forgetting.
    max_weight:
        Saturation cap to keep weights bounded under repeated reinforcement.
    """

    def __init__(
        self,
        storage_path: pathlib.Path | str | None = None,
        decay: float = 0.999,
        max_weight: float = 10.0,
    ) -> None:
        if not 0.0 < decay <= 1.0:
            raise ValueError("decay must be in (0, 1]")
        if max_weight <= 0.0:
            raise ValueError("max_weight must be positive")

        self.storage_path = pathlib.Path(storage_path) if storage_path else None
        self.decay = float(decay)
        self.max_weight = float(max_weight)
        self._lock = threading.RLock()
        # Layout: { channel(str): { node_id(str): weight(float) } }
        self._weights: dict[str, dict[str, float]] = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self.storage_path or not self.storage_path.exists():
            return
        try:
            raw = json.loads(self.storage_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cleaned: dict[str, dict[str, float]] = {}
                for ch, nodes in raw.items():
                    if not isinstance(nodes, dict):
                        continue
                    cleaned[str(ch)] = {
                        str(nid): float(w)
                        for nid, w in nodes.items()
                        if isinstance(w, (int, float))
                    }
                self._weights = cleaned
        except (OSError, ValueError) as exc:
            _LOG.warning("Hebbian store %s unreadable: %s", self.storage_path, exc)

    def save(self) -> None:
        if not self.storage_path:
            return
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.storage_path.with_suffix(self.storage_path.suffix + ".tmp")
            tmp.write_text(json.dumps(self._weights), encoding="utf-8")
            tmp.replace(self.storage_path)
        except OSError as exc:
            _LOG.warning("Failed to persist Hebbian store %s: %s", self.storage_path, exc)

    # ------------------------------------------------------------------
    # Updates
    # ------------------------------------------------------------------

    def update(
        self,
        channels: Iterable[int],
        node_id: str,
        *,
        reward: float = 1.0,
    ) -> None:
        """Reinforce (or weaken) associations between ``channels`` and ``node_id``.

        Positive ``reward`` strengthens the links; negative rewards (e.g.
        user thumbs-down) subtract weight and let decay/clipping prune
        them back to zero over time.
        """
        if not node_id:
            return
        chans = [str(int(c)) for c in channels]
        if not chans:
            return
        nid = str(node_id)
        with self._lock:
            # Global multiplicative decay on every touched channel.
            for ch in chans:
                bucket = self._weights.setdefault(ch, {})
                if self.decay < 1.0:
                    for key in list(bucket):
                        bucket[key] *= self.decay
                        if bucket[key] < 1e-4:
                            del bucket[key]
                new_val = bucket.get(nid, 0.0) + float(reward)
                new_val = max(-self.max_weight, min(self.max_weight, new_val))
                if new_val == 0.0:
                    bucket.pop(nid, None)
                else:
                    bucket[nid] = new_val

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def score(self, channels: Iterable[int], node_id: str) -> float:
        """Summed association weight of ``node_id`` across ``channels``."""
        if not node_id:
            return 0.0
        nid = str(node_id)
        total = 0.0
        with self._lock:
            for c in channels:
                bucket = self._weights.get(str(int(c)))
                if bucket:
                    total += bucket.get(nid, 0.0)
        return float(total)

    def boost(
        self,
        channels: Iterable[int],
        candidates: list[tuple[str, float]],
        *,
        weight: float = 0.15,
    ) -> list[tuple[str, float]]:
        """Return a re-ranked copy of ``candidates`` with Hebbian bonuses added.

        ``candidates`` is a list of ``(node_id, base_score)``.  The Hebbian
        score for each node is normalised against the max seen so it acts
        as a bounded bonus proportional to ``weight``.
        """
        chan_list = [int(c) for c in channels]
        if not chan_list or not candidates:
            return list(candidates)

        scored = []
        raw = []
        for node_id, base in candidates:
            h = self.score(chan_list, node_id)
            raw.append(h)
            scored.append((node_id, base))

        peak = max((abs(x) for x in raw), default=0.0)
        if peak <= 0.0:
            return list(candidates)
        w = float(weight)
        adjusted = [
            (nid, base + w * (r / peak))
            for (nid, base), r in zip(scored, raw)
        ]
        adjusted.sort(key=lambda pair: pair[1], reverse=True)
        return adjusted

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        with self._lock:
            return sum(len(v) for v in self._weights.values())

    def stats(self) -> dict[str, float]:
        """Summary stats for debugging / API exposure."""
        with self._lock:
            total = 0
            positive = 0
            acc = 0.0
            for bucket in self._weights.values():
                for w in bucket.values():
                    total += 1
                    acc += w
                    if w > 0:
                        positive += 1
            return {
                "channels_used": float(len(self._weights)),
                "associations": float(total),
                "positive_associations": float(positive),
                "mean_weight": float(acc / total) if total else 0.0,
            }
