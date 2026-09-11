"""Adapter and semantic validation for research and evidence graphs."""

import re
from urllib.parse import urlsplit, urlunsplit

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

ALLOWED_SOURCE_TYPES = frozenset(
    {
        "book",
        "dataset",
        "government_report",
        "official_statistics",
        "paper",
        "peer_reviewed_article",
        "primary_document",
        "standards_document",
        "textbook",
        "working_paper",
    }
)


def normalize_isbn(value: str) -> str:
    if not re.fullmatch(r"[0-9Xx\s-]+", value.strip()):
        raise ValueError(f"invalid ISBN-13: {value}")
    isbn = re.sub(r"[^0-9Xx]", "", value)
    if len(isbn) != 13 or not isbn.isdigit():
        raise ValueError(f"invalid ISBN-13: {value}")
    expected = (10 - sum((1 if index % 2 == 0 else 3) * int(digit) for index, digit in enumerate(isbn[:12])) % 10) % 10
    if int(isbn[-1]) != expected:
        raise ValueError(f"invalid ISBN-13 checksum: {value}")
    return isbn


def normalize_doi(value: str) -> str:
    doi = value.strip().lower()
    doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi\s*:?\s*)", "", doi)
    if not re.fullmatch(r"10\.\d{4,9}/\S+", doi):
        raise ValueError(f"invalid DOI: {value}")
    return doi.rstrip(".,;)")


def normalize_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"invalid URL: {value}")
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/") or "/", parsed.query, "")
    )


def canonical_source_locator(data: dict) -> tuple[str, str]:
    """Return a canonical identifier suitable for validation and deduplication."""
    if data.get("doi"):
        return "doi", normalize_doi(str(data["doi"]))
    if data.get("isbn"):
        return "isbn", normalize_isbn(str(data["isbn"]))
    if data.get("url"):
        url = normalize_url(str(data["url"]))
        parsed = urlsplit(url)
        if parsed.netloc.removeprefix("www.") in {"doi.org", "dx.doi.org"}:
            return "doi", normalize_doi(parsed.path.lstrip("/"))
        return "url", url
    if data.get("locator"):
        locator = str(data["locator"]).strip()
        if locator.upper().startswith("ISBN "):
            return "isbn", normalize_isbn(locator[5:])
        if locator.upper().startswith("DOI "):
            return "doi", normalize_doi(locator[4:])
        if locator.startswith(("https://", "http://")):
            return "url", normalize_url(locator)
    for field in ("path", "document_id"):
        if data.get(field):
            return field, str(data[field]).strip()
    raise ValueError("source requires a stable URL, DOI, ISBN, path, or document ID")


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
            for field_name in ("observation", "reasoning"):
                if not evidence.data.get(field_name):
                    issues.append(
                        _issue(
                            f"evidence_{field_name}",
                            evidence.id,
                            f"node:{evidence.id}",
                            f"evidence requires a concrete {field_name}",
                        )
                    )
            if evidence.data.get("role") == "counterexample":
                for field_name in (
                    "challenged_prediction",
                    "conflict_reason",
                    "rival_theory_id",
                    "rival_prediction",
                ):
                    if not evidence.data.get(field_name):
                        issues.append(
                            _issue(
                                f"counterexample_{field_name}",
                                evidence.id,
                                f"node:{evidence.id}",
                                f"counterexample requires {field_name}",
                            )
                        )
                review = evidence.data.get("logic_review", {})
                if not isinstance(review, dict) or review.get("status") != "passed" or not review.get("reason"):
                    issues.append(
                        _issue(
                            "counterexample_logic_review",
                            evidence.id,
                            f"node:{evidence.id}",
                            "counterexample requires a passed logic review with a reason",
                        )
                    )
                challenged_claims = [
                    edge.target
                    for edge in outgoing.get((evidence.id, "contradicts"), ())
                    if graph.get_node(edge.target).entity_type == "claim"
                ]
                challenged_theories = {
                    edge.source
                    for claim_id in challenged_claims
                    for edge in incoming.get((claim_id, "explains"), ())
                    if graph.get_node(edge.source).entity_type == "theory"
                }
                challenged_prediction = evidence.data.get("challenged_prediction")
                if challenged_prediction and not any(
                    challenged_prediction
                    in graph.get_node(theory_id).data.get("predictions", ())
                    for theory_id in challenged_theories
                ):
                    issues.append(
                        _issue(
                            "counterexample_prediction_link",
                            evidence.id,
                            f"node:{evidence.id}",
                            "challenged_prediction must be declared by a theory explaining the challenged claim",
                        )
                    )
                rival_id = evidence.data.get("rival_theory_id")
                try:
                    rival = graph.get_node(rival_id) if rival_id else None
                except KeyError:
                    rival = None
                if (
                    rival is None
                    or rival.entity_type != "theory"
                    or rival_id in challenged_theories
                    or evidence.data.get("rival_prediction")
                    not in rival.data.get("predictions", ())
                ):
                    issues.append(
                        _issue(
                            "counterexample_rival_link",
                            evidence.id,
                            f"node:{evidence.id}",
                            "counterexample must cite a different theory and one of its declared predictions",
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
        canonical_sources: dict[tuple[str, str], str] = {}
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
            elif source.data["source_type"] not in ALLOWED_SOURCE_TYPES:
                issues.append(
                    _issue(
                        "source_type",
                        source.id,
                        f"node:{source.id}",
                        f"source_type must be one of: {', '.join(sorted(ALLOWED_SOURCE_TYPES))}",
                    )
                )
            try:
                canonical = canonical_source_locator(source.data)
            except ValueError as exc:
                issues.append(_issue("source_locator_format", source.id, f"node:{source.id}", str(exc)))
            else:
                if canonical in canonical_sources:
                    issues.append(
                        _issue(
                            "duplicate_source",
                            source.id,
                            f"node:{source.id}",
                            f"source duplicates {canonical_sources[canonical]!r} after locator normalization",
                        )
                    )
                else:
                    canonical_sources[canonical] = source.id
            review = source.data.get("authenticity_review", {})
            if not isinstance(review, dict) or review.get("status") != "passed" or not review.get("method"):
                issues.append(
                    _issue(
                        "source_authenticity",
                        source.id,
                        f"node:{source.id}",
                        "source requires a passed authenticity review with its verification method",
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
