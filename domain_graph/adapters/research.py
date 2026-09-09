"""Reference adapter for research and evidence graphs."""

from ..adapter import DomainAdapter
from ..schema import DomainSchema, RelationSpec


RESEARCH_DOMAIN_SCHEMA = DomainSchema(
    name="research",
    entity_types=("question", "claim", "evidence", "source"),
    relations=(
        RelationSpec("contains", hierarchy=True),
        RelationSpec("supports"),
        RelationSpec("contradicts"),
        RelationSpec("derived_from"),
    ),
)


class ResearchDomainAdapter(DomainAdapter):
    """Adapter exposing a compact research/evidence vocabulary."""

    def __init__(self):
        super().__init__(RESEARCH_DOMAIN_SCHEMA)
