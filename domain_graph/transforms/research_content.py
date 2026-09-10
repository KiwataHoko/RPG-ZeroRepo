"""Deterministic research-to-content structure and provenance mapping."""

from collections.abc import Iterable
from dataclasses import dataclass

from ..adapters import ContentDomainAdapter
from ..graph import DomainGraph, ValidationIssue
from ..model import DomainNode


@dataclass(frozen=True)
class ContentBrief:
    """Audience and editorial constraints for a content transformation."""

    title: str
    audience: str = "general"
    purpose: str = ""
    content_type: str = "article"
    tone: str = ""
    locale: str = "en"
    depth: str = "standard"
    findings_title: str = "Additional findings"
    selected_claim_ids: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ContentMappingResult:
    """Mapped graph plus claim-coverage information for editorial review."""

    graph: DomainGraph
    used_claim_ids: tuple[str, ...]
    unused_claim_ids: tuple[str, ...]
    unsupported_claim_ids: tuple[str, ...]
    validation_issues: tuple[ValidationIssue, ...]


class ResearchToContentMapper:
    """Map research questions, claims, evidence, and sources into content."""

    def __init__(self, content_adapter: ContentDomainAdapter | None = None):
        self.content_adapter = content_adapter or ContentDomainAdapter()

    def convert(
        self,
        research_graph: DomainGraph,
        brief: ContentBrief,
        *,
        name: str | None = None,
        document_id: str = "document",
        source_graph_id: str | None = None,
        snapshot_version: int | None = None,
    ) -> ContentMappingResult:
        if research_graph.domain_schema.name != "research":
            raise ValueError("source graph must use the research domain schema")
        source_issues = research_graph.validate()
        if source_issues:
            summary = ", ".join(
                f"{issue.kind}@{issue.location}" for issue in source_issues
            )
            raise ValueError(f"invalid research graph: {summary}")

        claims = research_graph.get_nodes_by_type("claim")
        claim_by_id = {claim.id: claim for claim in claims}
        selected_ids = self._selected_claim_ids(claims, brief.selected_claim_ids)
        unknown = tuple(
            claim_id for claim_id in selected_ids if claim_id not in claim_by_id
        )
        if unknown:
            raise ValueError(f"unknown selected claim IDs: {', '.join(unknown)}")

        selected_set = set(selected_ids)
        content_graph = self.content_adapter.create_document(
            name or f"{research_graph.name}:content",
            document_id,
            title=brief.title,
            content_type=brief.content_type,
            data={
                "audience": brief.audience,
                "purpose": brief.purpose,
                "tone": brief.tone,
                "locale": brief.locale,
                "depth": brief.depth,
            },
        )
        source_graph_id = source_graph_id or research_graph.name

        question_claims = self._question_claims(research_graph, selected_set)
        mapped_claims: set[str] = set()
        previous_section_id: str | None = None
        for question in research_graph.get_nodes_by_type("question"):
            related_claims = question_claims.get(question.id, ())
            if not related_claims:
                continue
            section_id = f"section:question:{question.id}"
            self.content_adapter.add_section(
                content_graph,
                section_id,
                document_id,
                title=question.name or question.id,
                data={"kind": "research_question"},
            )
            self._add_source_ref(
                content_graph,
                research_graph,
                question,
                source_graph_id,
                snapshot_version,
            )
            content_graph.add_edge(
                section_id,
                f"source_ref:{question.id}",
                "derived_from",
            )
            if previous_section_id is not None:
                content_graph.add_edge(previous_section_id, section_id, "precedes")
            previous_section_id = section_id
            self._map_claims(
                content_graph,
                research_graph,
                related_claims,
                section_id,
                source_graph_id,
                snapshot_version,
            )
            mapped_claims.update(claim.id for claim in related_claims)

        remaining = tuple(
            claim_by_id[claim_id]
            for claim_id in selected_ids
            if claim_id not in mapped_claims
        )
        if remaining:
            section_id = "section:additional-findings"
            self.content_adapter.add_section(
                content_graph,
                section_id,
                document_id,
                title=brief.findings_title,
                data={"kind": "findings"},
            )
            if previous_section_id is not None:
                content_graph.add_edge(previous_section_id, section_id, "precedes")
            self._map_claims(
                content_graph,
                research_graph,
                remaining,
                section_id,
                source_graph_id,
                snapshot_version,
            )

        supported_claim_ids = {
            edge.target
            for edge in research_graph.edges
            if edge.relation == "supports"
            and research_graph.get_node(edge.source).entity_type == "evidence"
            and edge.target in selected_set
        }
        unused_ids = tuple(claim.id for claim in claims if claim.id not in selected_set)
        unsupported_ids = tuple(
            claim_id for claim_id in selected_ids if claim_id not in supported_claim_ids
        )
        issues = self.content_adapter.validate_content(content_graph)
        return ContentMappingResult(
            graph=content_graph,
            used_claim_ids=selected_ids,
            unused_claim_ids=unused_ids,
            unsupported_claim_ids=unsupported_ids,
            validation_issues=issues,
        )

    @staticmethod
    def _selected_claim_ids(
        claims: Iterable[DomainNode],
        selected: tuple[str, ...] | None,
    ) -> tuple[str, ...]:
        values = (claim.id for claim in claims) if selected is None else selected
        return tuple(dict.fromkeys(str(value) for value in values))

    @staticmethod
    def _question_claims(
        research_graph: DomainGraph,
        selected_claim_ids: set[str],
    ) -> dict[str, tuple[DomainNode, ...]]:
        grouped: dict[str, list[DomainNode]] = {}
        assigned: set[str] = set()
        for edge in research_graph.edges:
            if (
                edge.relation != "contains"
                or edge.target not in selected_claim_ids
                or edge.target in assigned
            ):
                continue
            source = research_graph.get_node(edge.source)
            target = research_graph.get_node(edge.target)
            if source.entity_type == "question" and target.entity_type == "claim":
                grouped.setdefault(source.id, []).append(target)
                assigned.add(target.id)
        return {key: tuple(value) for key, value in grouped.items()}

    def _map_claims(
        self,
        content_graph: DomainGraph,
        research_graph: DomainGraph,
        claims: Iterable[DomainNode],
        section_id: str,
        source_graph_id: str,
        snapshot_version: int | None,
    ) -> None:
        previous_block_id: str | None = None
        for claim in claims:
            claim_block_id = f"block:claim:{claim.id}"
            self.content_adapter.add_block(
                content_graph,
                claim_block_id,
                section_id,
                kind="claim",
                text=claim.name,
                data={"status": "outline"},
            )
            self._add_source_ref(
                content_graph,
                research_graph,
                claim,
                source_graph_id,
                snapshot_version,
            )
            content_graph.add_edge(
                claim_block_id,
                f"source_ref:{claim.id}",
                "derived_from",
            )
            if previous_block_id is not None:
                content_graph.add_edge(previous_block_id, claim_block_id, "precedes")
            previous_block_id = claim_block_id

            for evidence in self._supporting_evidence(research_graph, claim.id):
                evidence_block_id = f"block:evidence:{evidence.id}:{claim.id}"
                self.content_adapter.add_block(
                    content_graph,
                    evidence_block_id,
                    section_id,
                    kind="evidence",
                    text=evidence.name,
                    data={"status": "outline"},
                )
                self._add_source_ref(
                    content_graph,
                    research_graph,
                    evidence,
                    source_graph_id,
                    snapshot_version,
                )
                content_graph.add_edge(
                    evidence_block_id,
                    f"source_ref:{evidence.id}",
                    "derived_from",
                )
                content_graph.add_edge(evidence_block_id, claim_block_id, "explains")
                content_graph.add_edge(previous_block_id, evidence_block_id, "precedes")
                previous_block_id = evidence_block_id
                self._map_citations(
                    content_graph,
                    research_graph,
                    evidence,
                    claim,
                    evidence_block_id,
                    source_graph_id,
                    snapshot_version,
                )

    @staticmethod
    def _supporting_evidence(
        research_graph: DomainGraph,
        claim_id: str,
    ) -> tuple[DomainNode, ...]:
        evidence_ids = dict.fromkeys(
            edge.source
            for edge in research_graph.edges
            if edge.relation == "supports"
            and edge.target == claim_id
            and research_graph.get_node(edge.source).entity_type == "evidence"
        )
        return tuple(
            research_graph.get_node(evidence_id) for evidence_id in evidence_ids
        )

    def _map_citations(
        self,
        content_graph: DomainGraph,
        research_graph: DomainGraph,
        evidence: DomainNode,
        claim: DomainNode,
        evidence_block_id: str,
        source_graph_id: str,
        snapshot_version: int | None,
    ) -> None:
        cited_sources: set[str] = set()
        for edge in research_graph.edges:
            if edge.source != evidence.id or edge.relation != "derived_from":
                continue
            source = research_graph.get_node(edge.target)
            if source.entity_type != "source" or source.id in cited_sources:
                continue
            cited_sources.add(source.id)
            self._add_source_ref(
                content_graph,
                research_graph,
                source,
                source_graph_id,
                snapshot_version,
            )
            locator = edge.data.get("locator")
            if locator is None and edge.data.get("page") is not None:
                locator = f"p. {edge.data['page']}"
            self.content_adapter.add_citation(
                content_graph,
                f"citation:{source.id}:{evidence.id}:{claim.id}",
                evidence_block_id,
                f"source_ref:{source.id}",
                locator=str(locator) if locator is not None else None,
            )

    def _add_source_ref(
        self,
        content_graph: DomainGraph,
        research_graph: DomainGraph,
        source_node: DomainNode,
        source_graph_id: str,
        snapshot_version: int | None,
    ) -> None:
        source_ref_id = f"source_ref:{source_node.id}"
        if source_ref_id in content_graph.nodes:
            return
        self.content_adapter.add_source_ref(
            content_graph,
            source_ref_id,
            source_graph=source_graph_id,
            source_node_id=source_node.id,
            name=source_node.name,
            snapshot_version=snapshot_version,
            data={"source_entity_type": source_node.entity_type, **source_node.data},
        )
