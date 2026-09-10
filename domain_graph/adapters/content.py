"""Content-domain adapter for reusable, source-traceable publications."""

from typing import Any

from ..adapter import DomainAdapter
from ..graph import DomainGraph, ValidationIssue
from ..model import DomainNode
from ..schema import DomainSchema, RelationSpec

CONTENT_DOMAIN_SCHEMA = DomainSchema(
    name="content",
    entity_types=(
        "document",
        "section",
        "block",
        "asset",
        "citation",
        "source_ref",
    ),
    relations=(
        RelationSpec("contains", hierarchy=True),
        RelationSpec("precedes"),
        RelationSpec("derived_from"),
        RelationSpec("cites"),
        RelationSpec("explains"),
        RelationSpec("summarizes"),
        RelationSpec("variant_of"),
    ),
)


def _merge_data(data: dict[str, Any] | None, **fields: Any) -> dict[str, Any]:
    payload = dict(data or {})
    payload.update({key: value for key, value in fields.items() if value is not None})
    return payload


class ContentDomainAdapter(DomainAdapter):
    """Build reusable content graphs without coupling them to an output format."""

    def __init__(self):
        super().__init__(CONTENT_DOMAIN_SCHEMA)

    def create_document(
        self,
        name: str,
        document_id: str,
        *,
        title: str = "",
        content_type: str = "article",
        data: dict[str, Any] | None = None,
        strict_schema: bool = True,
    ) -> DomainGraph:
        """Create a content graph with its document root."""
        graph = self.create_graph(name, strict_schema=strict_schema)
        graph.add_node(
            document_id,
            "document",
            name=title,
            data=_merge_data(data, content_type=str(content_type)),
        )
        return graph

    def add_section(
        self,
        graph: DomainGraph,
        section_id: str,
        parent_id: str,
        *,
        title: str = "",
        data: dict[str, Any] | None = None,
    ) -> DomainNode:
        """Add a section below a document or another section."""
        self._require_parent(graph, parent_id, {"document", "section"})
        node = graph.add_node(section_id, "section", name=title, data=data)
        graph.add_edge(parent_id, section_id, "contains")
        return node

    def add_block(
        self,
        graph: DomainGraph,
        block_id: str,
        parent_id: str,
        *,
        kind: str,
        text: str = "",
        data: dict[str, Any] | None = None,
    ) -> DomainNode:
        """Add an ordered-content candidate below a document section."""
        self._require_parent(graph, parent_id, {"document", "section", "block"})
        node = graph.add_node(
            block_id,
            "block",
            data=_merge_data(data, kind=str(kind), text=str(text)),
        )
        graph.add_edge(parent_id, block_id, "contains")
        return node

    def add_asset(
        self,
        graph: DomainGraph,
        asset_id: str,
        parent_id: str,
        *,
        name: str = "",
        uri: str,
        media_type: str = "",
        alt: str = "",
        data: dict[str, Any] | None = None,
    ) -> DomainNode:
        """Add a format-neutral content asset below a structural parent."""
        self._require_parent(graph, parent_id, {"document", "section", "block"})
        if not str(uri):
            raise ValueError("asset uri must be a non-empty string")
        node = graph.add_node(
            asset_id,
            "asset",
            name=name,
            data=_merge_data(
                data,
                uri=str(uri),
                media_type=str(media_type),
                alt=str(alt),
            ),
        )
        graph.add_edge(parent_id, asset_id, "contains")
        return node

    def add_source_ref(
        self,
        graph: DomainGraph,
        source_ref_id: str,
        *,
        source_graph: str,
        source_node_id: str,
        name: str = "",
        snapshot_version: int | None = None,
        data: dict[str, Any] | None = None,
    ) -> DomainNode:
        """Add a stable reference to a node owned by another domain graph."""
        self._require_content_graph(graph)
        if not str(source_graph):
            raise ValueError("source_graph must be a non-empty string")
        if not str(source_node_id):
            raise ValueError("source_node_id must be a non-empty string")
        return graph.add_node(
            source_ref_id,
            "source_ref",
            name=name,
            data=_merge_data(
                data,
                source_graph=str(source_graph),
                source_node_id=str(source_node_id),
                snapshot_version=snapshot_version,
            ),
        )

    def add_citation(
        self,
        graph: DomainGraph,
        citation_id: str,
        parent_id: str,
        source_ref_id: str,
        *,
        locator: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> DomainNode:
        """Add a citation at a content location and link it to its source."""
        self._require_parent(graph, parent_id, {"block"})
        source_ref = graph.get_node(source_ref_id)
        if source_ref.entity_type != "source_ref":
            raise ValueError(f"citation target {source_ref_id!r} is not a source_ref")
        node = graph.add_node(
            citation_id,
            "citation",
            data=_merge_data(data, locator=locator),
        )
        graph.add_edge(parent_id, citation_id, "contains")
        graph.add_edge(citation_id, source_ref_id, "cites")
        return node

    def validate_content(self, graph: DomainGraph) -> tuple[ValidationIssue, ...]:
        """Validate content structure and cross-graph provenance conventions."""
        issues = list(graph.validate())
        if graph.domain_schema != self.schema:
            issues.append(
                ValidationIssue(
                    kind="domain_schema",
                    value=graph.domain_schema.name,
                    location="graph",
                    message="content graph must use the content domain schema",
                )
            )

        documents = graph.get_nodes_by_type("document")
        if not documents:
            issues.append(
                ValidationIssue(
                    kind="document_root",
                    value="document",
                    location="graph",
                    message="content graph must contain at least one document",
                )
            )
        reachable = {
            node.id for document in documents for node in graph.descendants(document.id)
        }
        structural_types = {"section", "block", "asset", "citation"}
        allowed_parent_types = {
            "section": {"document", "section"},
            "block": {"document", "section", "block"},
            "asset": {"document", "section", "block"},
            "citation": {"block"},
        }
        for node in graph.nodes.values():
            if node.entity_type in structural_types and node.id not in reachable:
                issues.append(
                    ValidationIssue(
                        kind="orphan_content",
                        value=node.id,
                        location=f"node:{node.id}",
                        message="content node is not contained by a document",
                    )
                )
            hierarchy_parents = tuple(
                graph.get_node(edge.source)
                for edge in graph.edges
                if edge.target == node.id and edge.relation == "contains"
            )
            if node.entity_type in structural_types and (
                len(hierarchy_parents) > 1
                or any(
                    parent.entity_type not in allowed_parent_types[node.entity_type]
                    for parent in hierarchy_parents
                )
            ):
                issues.append(
                    ValidationIssue(
                        kind="content_parent",
                        value=node.id,
                        location=f"node:{node.id}",
                        message="content node has invalid or multiple hierarchy parents",
                    )
                )
            if node.entity_type == "source_ref":
                for field in ("source_graph", "source_node_id"):
                    if not node.data.get(field):
                        issues.append(
                            ValidationIssue(
                                kind="source_reference",
                                value=field,
                                location=f"node:{node.id}",
                                message=f"source_ref requires non-empty {field}",
                            )
                        )

        for edge in graph.edges:
            if edge.relation in {"cites", "derived_from"}:
                target = graph.get_node(edge.target)
                if target.entity_type != "source_ref":
                    issues.append(
                        ValidationIssue(
                            kind="provenance_target",
                            value=edge.target,
                            location=f"edge:{edge.source}->{edge.target}",
                            message=f"{edge.relation} must target a source_ref",
                        )
                    )

        for citation in graph.get_nodes_by_type("citation"):
            citation_edges = tuple(
                edge
                for edge in graph.edges
                if edge.source == citation.id and edge.relation == "cites"
            )
            if len(citation_edges) != 1:
                issues.append(
                    ValidationIssue(
                        kind="citation_target",
                        value=citation.id,
                        location=f"node:{citation.id}",
                        message="citation must have exactly one outgoing cites edge",
                    )
                )

        return tuple(issues)

    def _require_parent(
        self,
        graph: DomainGraph,
        parent_id: str,
        allowed_types: set[str],
    ) -> DomainNode:
        self._require_content_graph(graph)
        parent = graph.get_node(parent_id)
        if parent.entity_type not in allowed_types:
            expected = ", ".join(sorted(allowed_types))
            raise ValueError(
                f"parent {parent_id!r} must have one of these types: {expected}"
            )
        return parent

    def _require_content_graph(self, graph: DomainGraph) -> None:
        if graph.domain_schema != self.schema:
            raise ValueError("graph must use the content domain schema")
