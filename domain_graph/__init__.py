"""Stable public API for the standalone domain graph core."""

__version__ = "0.2.0"

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
    "__version__",
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
