"""Domain-neutral node and edge models."""

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class DomainNode:
    """One entity in a ``DomainGraph``."""

    id: str
    entity_type: str
    name: str = ""
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "entity_type": self.entity_type,
            "name": self.name,
            "data": dict(self.data),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DomainNode":
        return cls(
            id=str(data["id"]),
            entity_type=str(data["entity_type"]),
            name=str(data.get("name", "")),
            data=dict(data.get("data") or {}),
        )


@dataclass
class DomainEdge:
    """One directed relation between two domain entities."""

    source: str
    target: str
    relation: str
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "relation": self.relation,
            "data": dict(self.data),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DomainEdge":
        return cls(
            source=str(data["source"]),
            target=str(data["target"]),
            relation=str(data["relation"]),
            data=dict(data.get("data") or {}),
        )
