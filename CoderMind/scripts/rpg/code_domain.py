"""Code-domain compatibility vocabulary for the RPG graph core."""

from enum import Enum

from .domain import DomainAdapter, DomainSchema, RelationSpec


class NodeType(str, Enum):
    """Legacy code entity types retained for API compatibility."""

    DIRECTORY = "directory"
    FILE = "file"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    COMPONENT = "component"
    DATA = "data"
    INTERFACE = "interface"
    VARIABLE = "variable"
    IMPORT = "import"
    REPO = "repo"
    MODULE = "module"
    PACKAGE = "package"

    def __str__(self):
        return self.value


class EdgeType(str, Enum):
    """Legacy code relation types retained for API compatibility."""

    COMPOSES = "composes"
    CONTAINS = "contains"
    INHERITS = "inherits"
    INVOKES = "invokes"
    REFERENCES = "references"
    SAME_UNIT = "same_unit"
    IMPORTS = "imports"
    CONTAINS_BASE_CLASS = "contains_base_class"

    def __str__(self):
        return self.value

    @classmethod
    def is_hierarchy(cls, relation) -> bool:
        return CODE_DOMAIN_SCHEMA.is_hierarchy(relation)


CODE_DOMAIN_SCHEMA = DomainSchema(
    name="code",
    entity_types=tuple(member.value for member in NodeType),
    relations=tuple(
        RelationSpec(
            name=member.value,
            hierarchy=member in {
                EdgeType.COMPOSES,
                EdgeType.CONTAINS,
                EdgeType.CONTAINS_BASE_CLASS,
            },
        )
        for member in EdgeType
    ),
)


class CodeDomainAdapter(DomainAdapter):
    """Adapter exposing the legacy code vocabulary through DomainAdapter."""

    def __init__(self):
        super().__init__(CODE_DOMAIN_SCHEMA)
