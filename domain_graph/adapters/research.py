"""Adapter and semantic validation for research and evidence graphs."""

from ..adapter import DomainAdapter
from ..graph import DomainGraph, ValidationIssue
from ..schema import DomainSchema, RelationSpec

RESEARCH_DOMAIN_SCHEMA = DomainSchema(
    name="research",
    entity_types=("question", "theory", "claim", "evidence", "source"),
    relations=(
        RelationSpec("contains", hierarchy=True),
        RelationSpec("supports"),
        RelationSpec("contradicts"),
        RelationSpec("derived_from"),
        RelationSpec("explains"),
    ),
)


class ResearchDomainAdapter(DomainAdapter):
    """Adapter exposing a compact research/evidence vocabulary."""

    def __init__(self):
        super().__init__(RESEARCH_DOMAIN_SCHEMA)

    def validate_research(
        self,
        graph: DomainGraph,
        *,
        minimum_theories: int = 2,
        minimum_sources: int = 2,
        require_counterexamples: bool = True,
    ) -> tuple[ValidationIssue, ...]:
        """Validate provenance, question ownership, and theory challenge coverage."""
        issues = list(graph.validate())
        if graph.domain_schema != self.schema:
            issues.append(
                _issue(
                    "research_schema",
                    graph.name,
                    "graph",
                    "graph must use the research schema",
                )
            )
            return tuple(issues)

        incoming = {}
        outgoing = {}
        for edge in graph.edges:
            incoming.setdefault((edge.target, edge.relation), []).append(edge)
            outgoing.setdefault((edge.source, edge.relation), []).append(edge)

        for claim in graph.get_nodes_by_type("claim"):
            question_edges = [
                edge
                for edge in incoming.get((claim.id, "contains"), ())
                if graph.get_node(edge.source).entity_type == "question"
            ]
            if len(question_edges) != 1:
                issues.append(
                    _issue(
                        "claim_question",
                        claim.id,
                        f"node:{claim.id}",
                        "claim must belong to exactly one question",
                    )
                )
            support = [
                edge
                for edge in incoming.get((claim.id, "supports"), ())
                if graph.get_node(edge.source).entity_type == "evidence"
            ]
            if not support and claim.data.get("status") != "unsupported":
                issues.append(
                    _issue(
                        "unsupported_claim",
                        claim.id,
                        f"node:{claim.id}",
                        "claim needs supporting evidence or unsupported status",
                    )
                )

        for evidence in graph.get_nodes_by_type("evidence"):
            sources = [
                edge
                for edge in outgoing.get((evidence.id, "derived_from"), ())
                if graph.get_node(edge.target).entity_type == "source"
            ]
            if not sources:
                issues.append(
                    _issue(
                        "evidence_source",
                        evidence.id,
                        f"node:{evidence.id}",
                        "evidence must identify a source",
                    )
                )
            if not evidence.data.get("locator"):
                issues.append(
                    _issue(
                        "evidence_locator",
                        evidence.id,
                        f"node:{evidence.id}",
                        "evidence requires a page, section, table, or timestamp locator",
                    )
                )
            if not any(
                edge.source == evidence.id
                and edge.relation in {"supports", "contradicts"}
                and graph.get_node(edge.target).entity_type == "claim"
                for edge in graph.edges
            ):
                issues.append(
                    _issue(
                        "orphan_evidence",
                        evidence.id,
                        f"node:{evidence.id}",
                        "evidence must support or contradict a claim",
                    )
                )

        locator_fields = ("url", "doi", "isbn", "path", "document_id")
        sources = graph.get_nodes_by_type("source")
        if len(sources) < minimum_sources:
            issues.append(
                _issue(
                    "source_coverage",
                    str(len(sources)),
                    "graph",
                    f"research requires at least {minimum_sources} sources",
                )
            )
        for source in sources:
            if not any(source.data.get(field) for field in locator_fields):
                issues.append(
                    _issue(
                        "source_locator",
                        source.id,
                        f"node:{source.id}",
                        "source requires a stable locator",
                    )
                )
            if source.data.get("url") and not (
                source.data.get("accessed_at") or source.data.get("access_date")
            ):
                issues.append(
                    _issue(
                        "source_access_date",
                        source.id,
                        f"node:{source.id}",
                        "remote source requires an access date",
                    )
                )
            if not source.data.get("source_type"):
                issues.append(
                    _issue(
                        "source_type",
                        source.id,
                        f"node:{source.id}",
                        "source requires a source_type",
                    )
                )
            if not any(
                edge.target == source.id
                and edge.relation == "derived_from"
                and graph.get_node(edge.source).entity_type == "evidence"
                for edge in graph.edges
            ):
                issues.append(
                    _issue(
                        "unused_source",
                        source.id,
                        f"node:{source.id}",
                        "source must ground at least one evidence node",
                    )
                )

        theories = graph.get_nodes_by_type("theory")
        if len(theories) < minimum_theories:
            issues.append(
                _issue(
                    "theory_coverage",
                    str(len(theories)),
                    "graph",
                    f"research requires at least {minimum_theories} competing theories",
                )
            )
        for theory in theories:
            claims = [edge.target for edge in outgoing.get((theory.id, "explains"), ())]
            if not claims:
                issues.append(
                    _issue(
                        "theory_claim",
                        theory.id,
                        f"node:{theory.id}",
                        "theory must explain at least one claim",
                    )
                )
                continue
            if require_counterexamples and not any(
                incoming.get((claim_id, "contradicts")) for claim_id in claims
            ):
                issues.append(
                    _issue(
                        "missing_counterexample",
                        theory.id,
                        f"node:{theory.id}",
                        "theory must be challenged by contradictory evidence",
                    )
                )
        return tuple(issues)


def _issue(kind: str, value: str, location: str, message: str) -> ValidationIssue:
    return ValidationIssue(kind=kind, value=value, location=location, message=message)
