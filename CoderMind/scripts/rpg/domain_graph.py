"""Domain-oriented public graph facade."""

from typing import List, Optional

from .code_domain import CODE_DOMAIN_SCHEMA
from .domain import DomainSchema
from .models import RPG


class DomainGraph(RPG):
    """RPG graph with an explicit domain schema."""

    def __init__(
        self,
        repo_name: str,
        domain_schema: Optional[DomainSchema] = None,
        repo_info: str = "",
        excluded_files: Optional[List[str]] = None,
    ):
        super().__init__(
            repo_name=repo_name,
            repo_info=repo_info,
            excluded_files=excluded_files or [],
            domain_schema=domain_schema or CODE_DOMAIN_SCHEMA,
        )
