"""Domain-neutral graph schema primitives for RPG."""

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional, Tuple


def symbol_value(value: Any) -> Optional[str]:
    """Return the string value for enums and string-like domain symbols."""
    if value is None:
        return None
    raw = getattr(value, "value", value)
    return str(raw)


@dataclass(frozen=True)
class RelationSpec:
    """Describe one relation understood by a domain schema."""

    name: str
    hierarchy: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "hierarchy": self.hierarchy}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RelationSpec":
        return cls(
            name=str(data["name"]),
            hierarchy=bool(data.get("hierarchy", False)),
        )


@dataclass(frozen=True)
class DomainSchema:
    """Serializable entity/relation vocabulary for a graph domain.

    The vocabulary is descriptive rather than restrictive: callers may still
    use arbitrary string entity types and relations. Relation specifications
    primarily carry graph semantics such as whether an edge is hierarchical.
    """

    name: str
    entity_types: Tuple[str, ...] = field(default_factory=tuple)
    relations: Tuple[RelationSpec, ...] = field(default_factory=tuple)

    def is_hierarchy(self, relation: Any) -> bool:
        relation_name = symbol_value(relation)
        if relation_name is None:
            return False
        relation_name = relation_name.lower()
        return any(
            spec.name.lower() == relation_name and spec.hierarchy
            for spec in self.relations
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "entity_types": list(self.entity_types),
            "relations": [spec.to_dict() for spec in self.relations],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DomainSchema":
        relation_data: Iterable[Any] = data.get("relations", ())
        relations = tuple(
            item if isinstance(item, RelationSpec)
            else RelationSpec.from_dict(item) if isinstance(item, dict)
            else RelationSpec(name=str(item))
            for item in relation_data
        )
        return cls(
            name=str(data.get("name", "domain")),
            entity_types=tuple(str(item) for item in data.get("entity_types", ())),
            relations=relations,
        )


class DomainAdapter:
    """Compatibility boundary between domain-specific symbols and RPG."""

    def __init__(self, schema: DomainSchema):
        self.schema = schema

    def entity_type(self, value: Any) -> Optional[str]:
        return symbol_value(value)

    def relation(self, value: Any) -> Optional[str]:
        return symbol_value(value)

