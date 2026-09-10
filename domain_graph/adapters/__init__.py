"""Reference domain adapters built on the stable graph core."""

from .content import CONTENT_DOMAIN_SCHEMA, ContentDomainAdapter
from .research import RESEARCH_DOMAIN_SCHEMA, ResearchDomainAdapter

__all__ = [
    "CONTENT_DOMAIN_SCHEMA",
    "RESEARCH_DOMAIN_SCHEMA",
    "ContentDomainAdapter",
    "ResearchDomainAdapter",
]
