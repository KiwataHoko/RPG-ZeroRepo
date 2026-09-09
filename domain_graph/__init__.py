"""Stable public API for the standalone domain graph core."""

from .adapter import DomainAdapter
from .graph import (
    DomainGraph,
    DomainGraphError,
    DuplicateNodeError,
    HierarchyCycleError,
    NodeNotFoundError,
    ValidationIssue,
)
from .model import DomainEdge, DomainNode
from .schema import DomainSchema, RelationSpec, SchemaViolation, symbol_value

__all__ = [
    "DomainAdapter",
    "DomainEdge",
    "DomainGraph",
    "DomainGraphError",
    "DomainNode",
    "DomainSchema",
    "DuplicateNodeError",
    "HierarchyCycleError",
    "NodeNotFoundError",
    "RelationSpec",
    "SchemaViolation",
    "ValidationIssue",
    "symbol_value",
]
