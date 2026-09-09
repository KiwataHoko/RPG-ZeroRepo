"""Compatibility exports for the standalone :mod:`domain_graph` core."""

import sys
from pathlib import Path


try:
    from domain_graph import (
        DomainAdapter,
        DomainEdge,
        DomainGraph,
        DomainGraphError,
        DomainNode,
        DomainSchema,
        DuplicateNodeError,
        HierarchyCycleError,
        NodeNotFoundError,
        RelationSpec,
        SchemaViolation,
        ValidationIssue,
        symbol_value,
    )
except ModuleNotFoundError as exc:
    if exc.name != "domain_graph":
        raise
    repo_root = Path(__file__).resolve().parents[3]
    if not (repo_root / "domain_graph").is_dir():
        raise
    sys.path.insert(0, str(repo_root))
    from domain_graph import (  # type: ignore[no-redef]
        DomainAdapter,
        DomainEdge,
        DomainGraph,
        DomainGraphError,
        DomainNode,
        DomainSchema,
        DuplicateNodeError,
        HierarchyCycleError,
        NodeNotFoundError,
        RelationSpec,
        SchemaViolation,
        ValidationIssue,
        symbol_value,
    )

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
