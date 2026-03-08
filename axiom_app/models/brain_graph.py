"""Unified graph model for the Brain tab."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import math
from typing import Any


@dataclass(slots=True)
class BrainNode:
    node_id: str
    node_type: str
    label: str
    metadata: dict[str, Any] = field(default_factory=dict)
    x: float = 0.0
    y: float = 0.0


@dataclass(slots=True)
class BrainEdge:
    source_id: str
    target_id: str
    edge_type: str


class BrainGraph:
    """Lightweight graph used by the Brain canvas."""

    def __init__(self) -> None:
        self.nodes: dict[str, BrainNode] = {}
        self.edges: list[BrainEdge] = []

    def clear(self) -> None:
        self.nodes.clear()
        self.edges.clear()

    def add_node(self, node: BrainNode) -> BrainNode:
        self.nodes[node.node_id] = node
        return node

    def add_edge(self, edge: BrainEdge) -> None:
        if edge.source_id not in self.nodes or edge.target_id not in self.nodes:
            return
        key = (edge.source_id, edge.target_id, edge.edge_type)
        if any((item.source_id, item.target_id, item.edge_type) == key for item in self.edges):
            return
        self.edges.append(edge)

    def get_node(self, node_id: str) -> BrainNode | None:
        return self.nodes.get(str(node_id or ""))

    def category_members(self, category_id: str) -> list[BrainNode]:
        members: list[BrainNode] = []
        for edge in self.edges:
            if edge.edge_type != "category_member" or edge.target_id != category_id:
                continue
            node = self.get_node(edge.source_id)
            if node is not None:
                members.append(node)
        return sorted(members, key=lambda item: item.label.casefold())

    def neighbors(
        self,
        node_id: str,
        *,
        edge_type: str | None = None,
        include_incoming: bool = True,
        include_outgoing: bool = True,
    ) -> list[BrainNode]:
        neighbors: list[BrainNode] = []
        target_id = str(node_id or "")
        for edge in self.edges:
            if edge_type and edge.edge_type != edge_type:
                continue
            if include_outgoing and edge.source_id == target_id:
                node = self.get_node(edge.target_id)
                if node is not None:
                    neighbors.append(node)
            if include_incoming and edge.target_id == target_id:
                node = self.get_node(edge.source_id)
                if node is not None:
                    neighbors.append(node)
        deduped: dict[str, BrainNode] = {node.node_id: node for node in neighbors}
        return sorted(deduped.values(), key=lambda item: item.label.casefold())

    def copy_positions_from(self, other: BrainGraph | None) -> None:
        if other is None:
            return
        for node_id, node in self.nodes.items():
            previous = other.get_node(node_id)
            if previous is None:
                continue
            node.x = float(previous.x)
            node.y = float(previous.y)

    def build_from_indexes_and_sessions(self, indexes: list[Any], sessions: list[Any]) -> BrainGraph:
        self.clear()

        root = self.add_node(
            BrainNode(
                node_id="category:brain",
                node_type="category",
                label="Axiom Brain",
                metadata={"category_kind": "root"},
            )
        )
        indexes_category = self.add_node(
            BrainNode(
                node_id="category:indexes",
                node_type="category",
                label="Indexes",
                metadata={"category_kind": "indexes"},
            )
        )
        sessions_category = self.add_node(
            BrainNode(
                node_id="category:sessions",
                node_type="category",
                label="Sessions",
                metadata={"category_kind": "sessions"},
            )
        )
        self.add_edge(BrainEdge(indexes_category.node_id, root.node_id, "category_member"))
        self.add_edge(BrainEdge(sessions_category.node_id, root.node_id, "category_member"))

        index_lookup: dict[str, str] = {}
        for row in list(indexes or []):
            index_id = str(row.get("index_id", "") or row.get("collection_name", "") or "").strip()
            if not index_id:
                continue
            label = str(row.get("index_id") or row.get("collection_name") or index_id)
            node_id = f"index:{index_id}"
            metadata = {
                "path": str(row.get("path", "") or ""),
                "vector_backend": str(row.get("vector_backend", "") or ""),
                "created_at": str(row.get("created_at", "") or ""),
                "document_count": int(row.get("document_count", 0) or 0),
                "chunk_count": int(row.get("chunk_count", 0) or 0),
                "collection_name": str(row.get("collection_name", "") or ""),
                "embedding_signature": str(row.get("embedding_signature", "") or ""),
                "source_files": list(row.get("source_files") or []),
                "manifest_path": str(row.get("manifest_path", "") or ""),
                "legacy_compat": bool(row.get("legacy_compat", False)),
            }
            self.add_node(
                BrainNode(
                    node_id=node_id,
                    node_type="index",
                    label=label,
                    metadata=metadata,
                )
            )
            self.add_edge(BrainEdge(node_id, indexes_category.node_id, "category_member"))
            index_lookup[index_id] = node_id
            collection_name = metadata["collection_name"]
            if collection_name:
                index_lookup[str(collection_name)] = node_id

        mode_categories: dict[str, str] = {}
        skill_categories: dict[str, str] = {}
        for summary in list(sessions or []):
            session_id = str(getattr(summary, "session_id", "") or "").strip()
            if not session_id:
                continue
            mode = str(getattr(summary, "mode", "") or "Q&A").strip() or "Q&A"
            skill_ids = [str(item).strip() for item in (getattr(summary, "skill_ids", []) or []) if str(item).strip()]
            primary_skill_id = str(
                getattr(summary, "primary_skill_id", "")
                or getattr(summary, "active_profile", "")
                or ""
            ).strip()
            if primary_skill_id and primary_skill_id not in skill_ids:
                skill_ids.insert(0, primary_skill_id)
            if not skill_ids:
                fallback_skill = str(getattr(summary, "active_profile", "") or "Unskilled").strip() or "Unskilled"
                skill_ids = [fallback_skill]
                primary_skill_id = primary_skill_id or fallback_skill
            title = str(getattr(summary, "title", "") or session_id)
            node_id = f"session:{session_id}"
            metadata = {
                "session_id": session_id,
                "created_at": str(getattr(summary, "created_at", "") or ""),
                "updated_at": str(getattr(summary, "updated_at", "") or ""),
                "summary": str(getattr(summary, "summary", "") or ""),
                "active_profile": primary_skill_id,
                "primary_skill_id": primary_skill_id,
                "skill_ids": list(skill_ids),
                "skill_reasons": dict(getattr(summary, "skill_reasons", {}) or {}),
                "mode": mode,
                "index_id": str(getattr(summary, "index_id", "") or ""),
                "vector_backend": str(getattr(summary, "vector_backend", "") or ""),
                "llm_provider": str(getattr(summary, "llm_provider", "") or ""),
                "llm_model": str(getattr(summary, "llm_model", "") or ""),
                "embed_model": str(getattr(summary, "embed_model", "") or ""),
                "retrieve_k": int(getattr(summary, "retrieve_k", 0) or 0),
                "final_k": int(getattr(summary, "final_k", 0) or 0),
                "mmr_lambda": float(getattr(summary, "mmr_lambda", 0.0) or 0.0),
                "agentic_iterations": int(getattr(summary, "agentic_iterations", 0) or 0),
            }
            self.add_node(
                BrainNode(
                    node_id=node_id,
                    node_type="session",
                    label=title,
                    metadata=metadata,
                )
            )
            self.add_edge(BrainEdge(node_id, sessions_category.node_id, "category_member"))

            if mode not in mode_categories:
                mode_node_id = f"category:mode:{mode.casefold()}"
                mode_categories[mode] = mode_node_id
                self.add_node(
                    BrainNode(
                        node_id=mode_node_id,
                        node_type="category",
                        label=mode,
                        metadata={"category_kind": "mode", "mode": mode},
                    )
                )
                self.add_edge(BrainEdge(mode_node_id, sessions_category.node_id, "category_member"))
            self.add_edge(BrainEdge(node_id, mode_categories[mode], "category_member"))

            for skill_id in skill_ids:
                if skill_id not in skill_categories:
                    skill_node_id = f"category:skill:{skill_id.casefold()}"
                    skill_categories[skill_id] = skill_node_id
                    self.add_node(
                        BrainNode(
                            node_id=skill_node_id,
                            node_type="category",
                            label=skill_id,
                            metadata={"category_kind": "skill", "skill_id": skill_id},
                        )
                    )
                    self.add_edge(BrainEdge(skill_node_id, sessions_category.node_id, "category_member"))
                self.add_edge(BrainEdge(node_id, skill_categories[skill_id], "category_member"))

            if not primary_skill_id and skill_ids:
                primary_skill_id = skill_ids[0]
            if primary_skill_id:
                self.nodes[node_id].metadata["primary_skill_id"] = primary_skill_id

            index_id = str(getattr(summary, "index_id", "") or "").strip()
            target_index_id = index_lookup.get(index_id)
            if target_index_id:
                self.add_edge(BrainEdge(node_id, target_index_id, "uses_index"))

        self._refresh_category_metadata()
        self._seed_positions()
        self.apply_force_layout()
        return self

    def apply_force_layout(self, iterations: int = 100) -> BrainGraph:
        if not self.nodes:
            return self

        fixed_nodes = {"category:brain"}
        node_ids = list(self.nodes.keys())
        repulsion = 18_000.0
        spring_strength = 0.018
        center_pull = 0.015
        category_pull = 0.012
        max_step = 28.0

        for _ in range(max(1, int(iterations))):
            forces = {node_id: [0.0, 0.0] for node_id in node_ids}
            for left_index, left_id in enumerate(node_ids):
                left = self.nodes[left_id]
                for right_id in node_ids[left_index + 1:]:
                    right = self.nodes[right_id]
                    dx = left.x - right.x
                    dy = left.y - right.y
                    distance_sq = dx * dx + dy * dy + 0.01
                    distance = math.sqrt(distance_sq)
                    force = repulsion / distance_sq
                    fx = force * dx / distance
                    fy = force * dy / distance
                    forces[left_id][0] += fx
                    forces[left_id][1] += fy
                    forces[right_id][0] -= fx
                    forces[right_id][1] -= fy

                    if left.node_type == right.node_type and left.node_type != "category":
                        forces[left_id][0] -= category_pull * dx
                        forces[left_id][1] -= category_pull * dy
                        forces[right_id][0] += category_pull * dx
                        forces[right_id][1] += category_pull * dy

            for edge in self.edges:
                source = self.get_node(edge.source_id)
                target = self.get_node(edge.target_id)
                if source is None or target is None:
                    continue
                dx = target.x - source.x
                dy = target.y - source.y
                distance = math.sqrt(dx * dx + dy * dy) + 0.01
                ideal = 160.0 if edge.edge_type == "uses_index" else 110.0
                stretch = distance - ideal
                force = spring_strength * stretch
                fx = force * dx / distance
                fy = force * dy / distance
                forces[source.node_id][0] += fx
                forces[source.node_id][1] += fy
                forces[target.node_id][0] -= fx
                forces[target.node_id][1] -= fy

            for node_id, node in self.nodes.items():
                if node_id in fixed_nodes:
                    node.x = 0.0
                    node.y = 0.0
                    continue
                forces[node_id][0] -= node.x * center_pull
                forces[node_id][1] -= node.y * center_pull
                step_x = max(-max_step, min(max_step, forces[node_id][0]))
                step_y = max(-max_step, min(max_step, forces[node_id][1]))
                node.x += step_x
                node.y += step_y

        return self

    def _refresh_category_metadata(self) -> None:
        for node in self.nodes.values():
            if node.node_type != "category":
                continue
            members = self.category_members(node.node_id)
            node.metadata["member_ids"] = [item.node_id for item in members]
            node.metadata["member_count"] = len(members)
            node.metadata["session_count"] = len([item for item in members if item.node_type == "session"])
            node.metadata["index_count"] = len([item for item in members if item.node_type == "index"])

    def _seed_positions(self) -> None:
        if not self.nodes:
            return

        root = self.get_node("category:brain")
        if root is not None:
            root.x = 0.0
            root.y = 0.0

        anchors = {
            "category:indexes": (-320.0, -40.0),
            "category:sessions": (320.0, 40.0),
        }
        for node_id, (x_pos, y_pos) in anchors.items():
            node = self.get_node(node_id)
            if node is not None and node.x == 0.0 and node.y == 0.0:
                node.x = x_pos
                node.y = y_pos

        for node in self.nodes.values():
            if node.node_id in {"category:brain", *anchors.keys()}:
                continue
            if node.x != 0.0 or node.y != 0.0:
                continue
            parent_id = self._primary_category_for(node.node_id)
            center_x, center_y = anchors.get(parent_id, (0.0, 0.0))
            radius = 180.0 if node.node_type == "index" else 220.0 if node.node_type == "session" else 120.0
            angle = self._stable_angle(node.node_id)
            node.x = center_x + math.cos(angle) * radius
            node.y = center_y + math.sin(angle) * radius

    def _primary_category_for(self, node_id: str) -> str:
        for edge in self.edges:
            if edge.edge_type == "category_member" and edge.source_id == node_id:
                return edge.target_id
        return "category:brain"

    @staticmethod
    def _stable_angle(value: str) -> float:
        digest = hashlib.sha1(str(value).encode("utf-8")).hexdigest()
        sample = int(digest[:8], 16)
        return (sample / 0xFFFFFFFF) * math.tau
