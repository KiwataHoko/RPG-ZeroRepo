"""Domain schema primitives for the standalone graph core."""

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional, Tuple


def symbol_value(value: Any) -> Optional[str]:
    """Normalize enums and string-like domain symbols to strings."""
    if value is None:
        return None
    raw = getattr(value, "value", value)
    return str(raw)


class SchemaViolation(ValueError):
    """Raised when strict schema validation rejects a domain symbol."""


@dataclass(frozen=True)
class RelationSpec:
    """Describe a relation understood by a domain schema."""

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
    """Serializable vocabulary and relation semantics for one graph domain.

    Schemas are open-world by default: arbitrary string entity types and
    relations remain valid. Closed-vocabulary consumers can enable strict
    validation on ``DomainGraph``.
    """

    name: str
    entity_types: Tuple[str, ...] = field(default_factory=tuple)
    relations: Tuple[RelationSpec, ...] = field(default_factory=tuple)

    def relation_spec(self, relation: Any) -> Optional[RelationSpec]:
        relation_name = symbol_value(relation)
        if relation_name is None:
            return None
        relation_name = relation_name.lower()
        return next(
            (
                spec
                for spec in self.relations
                if spec.name.lower() == relation_name
            ),
            None,
        )

    def has_entity_type(self, entity_type: Any) -> bool:
        value = symbol_value(entity_type)
        return value is not None and value in self.entity_types

    def has_relation(self, relation: Any) -> bool:
        return self.relation_spec(relation) is not None

    def validate_entity_type(self, entity_type: Any, *, strict: bool = False) -> str:
        value = symbol_value(entity_type)
        if not value:
            raise SchemaViolation("entity_type must be a non-empty string")
        if strict and self.entity_types and value not in self.entity_types:
            raise SchemaViolation(
                f"entity type {value!r} is not declared by schema {self.name!r}"
            )
        return value

    def validate_relation(self, relation: Any, *, strict: bool = False) -> str:
        value = symbol_value(relation)
        if not value:
            raise SchemaViolation("relation must be a non-empty string")
        if strict and self.relations and self.relation_spec(value) is None:
            raise SchemaViolation(
                f"relation {value!r} is not declared by schema {self.name!r}"
            )
        return value

    def is_hierarchy(self, relation: Any) -> bool:
        spec = self.relation_spec(relation)
        return bool(spec and spec.hierarchy)

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
            item
            if isinstance(item, RelationSpec)
            else RelationSpec.from_dict(item)
            if isinstance(item, dict)
            else RelationSpec(name=str(item))
            for item in relation_data
        )
        return cls(
            name=str(data.get("name", "domain")),
            entity_types=tuple(str(item) for item in data.get("entity_types", ())),
            relations=relations,
        )
