"""Markdown renderer for content-domain graphs."""

from ..graph import DomainGraph
from ..model import DomainNode
from ._tree import citation_source, ordered_children, select_document


class MarkdownRenderer:
    """Render a validated content document as portable Markdown."""

    def render(self, graph: DomainGraph, *, document_id: str | None = None) -> str:
        document = select_document(graph, document_id)
        self._footnotes: list[str] = []
        lines = [f"# {document.name or document.id}", ""]
        for child in ordered_children(graph, document.id):
            lines.extend(self._render_node(graph, child, heading_level=2))
        if self._footnotes:
            lines.extend(["---", "", *self._footnotes])
        return "\n".join(lines).rstrip() + "\n"

    def _render_node(
        self,
        graph: DomainGraph,
        node: DomainNode,
        *,
        heading_level: int,
    ) -> list[str]:
        if node.entity_type == "section":
            lines = [f"{'#' * min(heading_level, 6)} {node.name or node.id}", ""]
            for child in ordered_children(graph, node.id):
                lines.extend(
                    self._render_node(graph, child, heading_level=heading_level + 1)
                )
            return lines
        if node.entity_type == "block":
            return self._render_block(graph, node, heading_level)
        if node.entity_type == "asset":
            alt = str(node.data.get("alt") or node.name or "asset")
            url = str(node.data.get("url") or node.data.get("path") or "")
            return [f"![{alt}]({url})", ""]
        return []

    def _render_block(
        self,
        graph: DomainGraph,
        node: DomainNode,
        heading_level: int,
    ) -> list[str]:
        kind = str(node.data.get("kind", "paragraph"))
        text = str(node.data.get("text", ""))
        citations = tuple(
            child
            for child in ordered_children(graph, node.id)
            if child.entity_type == "citation"
        )
        markers = "".join(
            self._citation_marker(graph, citation) for citation in citations
        )
        if kind == "code":
            language = str(node.data.get("language", ""))
            lines = [f"```{language}", text, "```", ""]
        elif kind == "quote":
            lines = [*(f"> {line}" for line in text.splitlines()), ""]
        elif kind == "list":
            items = node.data.get("items")
            values = items if isinstance(items, list) else text.splitlines()
            lines = [*(f"- {item}" for item in values), ""]
        else:
            lines = [f"{text}{markers}", ""]
        if markers and kind in {"code", "quote", "list"}:
            lines[-1:-1] = [markers]
        for child in ordered_children(graph, node.id):
            if child.entity_type != "citation":
                lines.extend(
                    self._render_node(graph, child, heading_level=heading_level)
                )
        return lines

    def _citation_marker(self, graph: DomainGraph, citation: DomainNode) -> str:
        source = citation_source(graph, citation.id)
        label = source.name or str(source.data.get("source_node_id", source.id))
        url = source.data.get("url")
        reference = f"[{label}]({url})" if url else label
        locator = citation.data.get("locator")
        if locator:
            reference += f", {locator}"
        self._footnotes.append(f"[^{citation.id}]: {reference}")
        return f"[^{citation.id}]"
