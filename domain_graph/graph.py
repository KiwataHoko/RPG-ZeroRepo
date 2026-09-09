"""Standalone domain graph implementation."""

from collections import deque
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
import json
import math
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional, Tuple

from .model import DomainEdge, DomainNode
from .schema import DomainSchema


class DomainGraphError(Exception):
    """Base error for graph operations."""


class DuplicateNodeError(DomainGraphError):
    """Raised when adding an existing node id."""


class NodeNotFoundError(DomainGraphError, KeyError):
    """Raised when an operation references a missing node."""


class HierarchyCycleError(DomainGraphError):
    """Raised when a hierarchy edge would introduce a cycle."""


@dataclass(frozen=True)
class ValidationIssue:
    """Structured schema validation finding."""

    kind: str
    value: str
    location: str
    message: str


class DomainGraph:
    """Domain-neutral directed graph with schema-defined hierarchy semantics."""

    FORMAT = "domain-graph"
    FORMAT_VERSION = 1

    def __init__(
        self,
        name: str,
        domain_schema: DomainSchema,
        *,
        strict_schema: bool = False,
    ) -> None:
        self.name = str(name)
        self.domain_schema = domain_schema
        self.strict_schema = bool(strict_schema)
        self._nodes: Dict[str, DomainNode] = {}
        self._edges: list[DomainEdge] = []

    @property
    def nodes(self) -> Mapping[str, DomainNode]:
        """Read-only mapping of node id to node."""
        return MappingProxyType(self._nodes)

    @property
    def edges(self) -> Tuple[DomainEdge, ...]:
        """Immutable view of graph edges."""
        return tuple(self._edges)

    def add_node(
        self,
        node_id: str,
        entity_type: Any,
        *,
        name: str = "",
        data: Optional[Dict[str, Any]] = None,
    ) -> DomainNode:
        node_id = str(node_id)
        if not node_id:
            raise ValueError("node_id must be a non-empty string")
        if node_id in self._nodes:
            raise DuplicateNodeError(f"node {node_id!r} already exists")
        normalized_type = self.domain_schema.validate_entity_type(
            entity_type,
            strict=self.strict_schema,
        )
        node = DomainNode(
            id=node_id,
            entity_type=normalized_type,
            name=str(name),
            data=dict(data or {}),
        )
        self._nodes[node_id] = node
        return node

    def remove_node(self, node_id: str) -> DomainNode:
        node = self.get_node(node_id)
        self._nodes.pop(node.id)
        self._edges = [
            edge
            for edge in self._edges
            if edge.source != node.id and edge.target != node.id
        ]
        return node

    def get_node(self, node_id: str) -> DomainNode:
        try:
            return self._nodes[str(node_id)]
        except KeyError as exc:
            raise NodeNotFoundError(f"node {node_id!r} does not exist") from exc

    def get_nodes_by_type(self, entity_type: Any) -> Tuple[DomainNode, ...]:
        normalized = self.domain_schema.validate_entity_type(entity_type)
        return tuple(
            node for node in self._nodes.values()
            if node.entity_type == normalized
        )

    def add_edge(
        self,
        source: str,
        target: str,
        relation: Any,
        *,
        data: Optional[Dict[str, Any]] = None,
    ) -> DomainEdge:
        source_node = self.get_node(source)
        target_node = self.get_node(target)
        normalized_relation = self.domain_schema.validate_relation(
            relation,
            strict=self.strict_schema,
        )
        if (
            self.domain_schema.is_hierarchy(normalized_relation)
            and self._hierarchy_reachable(target_node.id, source_node.id)
        ):
            raise HierarchyCycleError(
                f"hierarchy edge {source_node.id!r} -> {target_node.id!r} creates a cycle"
            )
        edge = DomainEdge(
            source=source_node.id,
            target=target_node.id,
            relation=normalized_relation,
            data=dict(data or {}),
        )
        self._edges.append(edge)
        return edge

    def remove_edge(
        self,
        source: str,
        target: str,
        relation: Optional[Any] = None,
    ) -> int:
        source = str(source)
        target = str(target)
        normalized_relation = (
            self.domain_schema.validate_relation(relation)
            if relation is not None
            else None
        )
        before = len(self._edges)
        self._edges = [
            edge
            for edge in self._edges
            if not (
                edge.source == source
                and edge.target == target
                and (normalized_relation is None or edge.relation == normalized_relation)
            )
        ]
        return before - len(self._edges)

    def neighbors(
        self,
        node_id: str,
        *,
        relation: Optional[Any] = None,
        direction: str = "out",
    ) -> Tuple[DomainNode, ...]:
        node = self.get_node(node_id)
        if direction not in {"out", "in", "both"}:
            raise ValueError("direction must be 'out', 'in', or 'both'")
        normalized_relation = (
            self.domain_schema.validate_relation(relation)
            if relation is not None
            else None
        )
        result: list[DomainNode] = []
        seen: set[str] = set()
        for edge in self._edges:
            if normalized_relation is not None and edge.relation != normalized_relation:
                continue
            candidate: Optional[str] = None
            if direction in {"out", "both"} and edge.source == node.id:
                candidate = edge.target
            elif direction in {"in", "both"} and edge.target == node.id:
                candidate = edge.source
            if candidate is not None and candidate not in seen:
                seen.add(candidate)
                result.append(self._nodes[candidate])
        return tuple(result)

    def children(self, node_id: str) -> Tuple[DomainNode, ...]:
        self.get_node(node_id)
        return self._hierarchy_neighbors(str(node_id), direction="out")

    def parents(self, node_id: str) -> Tuple[DomainNode, ...]:
        self.get_node(node_id)
        return self._hierarchy_neighbors(str(node_id), direction="in")

    def descendants(self, node_id: str) -> Tuple[DomainNode, ...]:
        return self._walk_hierarchy(node_id, direction="out")

    def ancestors(self, node_id: str) -> Tuple[DomainNode, ...]:
        return self._walk_hierarchy(node_id, direction="in")

    def validate(self) -> Tuple[ValidationIssue, ...]:
        """Report symbols outside the schema's declared vocabulary."""
        issues: list[ValidationIssue] = []
        if self.domain_schema.entity_types:
            for node in self._nodes.values():
                if not self.domain_schema.has_entity_type(node.entity_type):
                    issues.append(
                        ValidationIssue(
                            kind="unknown_entity_type",
                            value=node.entity_type,
                            location=f"node:{node.id}",
                            message=(
                                f"entity type {node.entity_type!r} is not declared by "
                                f"schema {self.domain_schema.name!r}"
                            ),
                        )
                    )
        if self.domain_schema.relations:
            for index, edge in enumerate(self._edges):
                if not self.domain_schema.has_relation(edge.relation):
                    issues.append(
                        ValidationIssue(
                            kind="unknown_relation",
                            value=edge.relation,
                            location=f"edge:{index}",
                            message=(
                                f"relation {edge.relation!r} is not declared by "
                                f"schema {self.domain_schema.name!r}"
                            ),
                        )
                    )
        return tuple(issues)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "format": self.FORMAT,
            "version": self.FORMAT_VERSION,
            "name": self.name,
            "schema": self.domain_schema.to_dict(),
            "strict_schema": self.strict_schema,
            "nodes": [node.to_dict() for node in self._nodes.values()],
            "edges": [edge.to_dict() for edge in self._edges],
        }

    def to_json(self, *, indent: Optional[int] = None) -> str:
        """Serialize the graph to the versioned JSON wire format."""
        payload = self.to_dict()
        _validate_json_payload(payload)
        return json.dumps(payload, ensure_ascii=False, indent=indent)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DomainGraph":
        if not isinstance(data, dict):
            raise ValueError("domain graph payload must contain an object")
        graph_format = data.get("format", cls.FORMAT)
        if graph_format != cls.FORMAT:
            raise ValueError(f"unsupported graph format: {graph_format!r}")
        version = int(data.get("version", cls.FORMAT_VERSION))
        if version != cls.FORMAT_VERSION:
            raise ValueError(f"unsupported domain graph version: {version}")
        graph = cls(
            name=str(data.get("name", "domain")),
            domain_schema=DomainSchema.from_dict(data.get("schema") or {}),
            strict_schema=bool(data.get("strict_schema", False)),
        )
        for node_data in data.get("nodes", ()):
            node = DomainNode.from_dict(node_data)
            graph.add_node(
                node.id,
                node.entity_type,
                name=node.name,
                data=node.data,
            )
        for edge_data in data.get("edges", ()):
            edge = DomainEdge.from_dict(edge_data)
            graph.add_edge(
                edge.source,
                edge.target,
                edge.relation,
                data=edge.data,
            )
        return graph

    @classmethod
    def from_json(cls, payload: str) -> "DomainGraph":
        """Restore a graph from :meth:`to_json` output."""
        data = json.loads(payload)
        if not isinstance(data, dict):
            raise ValueError("domain graph JSON must contain an object")
        return cls.from_dict(data)

    def _hierarchy_neighbors(
        self,
        node_id: str,
        *,
        direction: str,
    ) -> Tuple[DomainNode, ...]:
        result: list[DomainNode] = []
        seen: set[str] = set()
        for edge in self._edges:
            if not self.domain_schema.is_hierarchy(edge.relation):
                continue
            candidate: Optional[str] = None
            if direction == "out" and edge.source == node_id:
                candidate = edge.target
            elif direction == "in" and edge.target == node_id:
                candidate = edge.source
            if candidate is not None and candidate not in seen:
                seen.add(candidate)
                result.append(self._nodes[candidate])
        return tuple(result)

    def _walk_hierarchy(self, node_id: str, *, direction: str) -> Tuple[DomainNode, ...]:
        start = self.get_node(node_id)
        queue = deque([start.id])
        seen = {start.id}
        result: list[DomainNode] = []
        while queue:
            current = queue.popleft()
            for neighbor in self._hierarchy_neighbors(current, direction=direction):
                if neighbor.id in seen:
                    continue
                seen.add(neighbor.id)
                result.append(neighbor)
                queue.append(neighbor.id)
        return tuple(result)

    def _hierarchy_reachable(self, source: str, target: str) -> bool:
        if source == target:
            return True
        queue = deque([source])
        seen = {source}
        while queue:
            current = queue.popleft()
            for neighbor in self._hierarchy_neighbors(current, direction="out"):
                if neighbor.id == target:
                    return True
                if neighbor.id not in seen:
                    seen.add(neighbor.id)
                    queue.append(neighbor.id)
        return False


def _validate_json_payload(value: Any) -> None:
    """Reject values that json.dumps would encode lossy or non-standardly."""
    if isinstance(value, MappingABC):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON mapping keys must be strings")
            _validate_json_payload(item)
    elif isinstance(value, tuple):
        raise TypeError("JSON tuples are not supported")
    elif isinstance(value, list):
        for item in value:
            _validate_json_payload(item)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("JSON floats must be finite")
