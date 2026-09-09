"""Stable adapter boundary for domain-specific integrations."""

from typing import Any, Optional

from .graph import DomainGraph
from .schema import DomainSchema, symbol_value


class DomainAdapter:
    """Translate domain-specific symbols into the standalone graph core."""

    def __init__(self, schema: DomainSchema):
        self.schema = schema

    def entity_type(self, value: Any) -> Optional[str]:
        return symbol_value(value)

    def relation(self, value: Any) -> Optional[str]:
        return symbol_value(value)

    def create_graph(
        self,
        name: str,
        *,
        strict_schema: bool = False,
    ) -> DomainGraph:
        return DomainGraph(
            name=name,
            domain_schema=self.schema,
            strict_schema=strict_schema,
        )
