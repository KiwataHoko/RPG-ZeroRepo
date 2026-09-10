"""HTML renderer for content-domain graphs."""

import re
from html import escape

from ..graph import DomainGraph
from ..model import DomainNode
from ._tree import citation_source, ordered_children, select_document


def _html_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-") or "item"


class HtmlRenderer:
    """Render a validated content document as an HTML article fragment."""

    def render(self, graph: DomainGraph, *, document_id: str | None = None) -> str:
        document = select_document(graph, document_id)
        self._citations: list[tuple[DomainNode, DomainNode]] = []
        lines = [
            f'<article data-document-id="{escape(document.id, quote=True)}">',
            f"  <h1>{escape(document.name or document.id)}</h1>",
        ]
        for child in ordered_children(graph, document.id):
            lines.extend(self._render_node(graph, child, heading_level=2, indent="  "))
        if self._citations:
            lines.extend(
                [
                    '  <section class="references">',
                    "    <h2>References</h2>",
                    "    <ol>",
                ]
            )
            for citation, source in self._citations:
                citation_id = _html_id(citation.id)
                label = escape(
                    source.name or str(source.data.get("source_node_id", source.id))
                )
                url = source.data.get("url")
                reference = (
                    f'<a href="{escape(str(url), quote=True)}">{label}</a>'
                    if url
                    else label
                )
                locator = citation.data.get("locator")
                if locator:
                    reference += f", {escape(str(locator))}"
                lines.append(f'      <li id="{citation_id}">{reference}</li>')
            lines.extend(["    </ol>", "  </section>"])
        lines.append("</article>")
        return "\n".join(lines) + "\n"

    def _render_node(
        self,
        graph: DomainGraph,
        node: DomainNode,
        *,
        heading_level: int,
        indent: str,
    ) -> list[str]:
        if node.entity_type == "section":
            level = min(heading_level, 6)
            lines = [
                f'{indent}<section data-section-id="{escape(node.id, quote=True)}">',
                f"{indent}  <h{level}>{escape(node.name or node.id)}</h{level}>",
            ]
            for child in ordered_children(graph, node.id):
                lines.extend(
                    self._render_node(
                        graph,
                        child,
                        heading_level=heading_level + 1,
                        indent=indent + "  ",
                    )
                )
            lines.append(f"{indent}</section>")
            return lines
        if node.entity_type == "block":
            return self._render_block(graph, node, heading_level, indent)
        if node.entity_type == "asset":
            alt = escape(str(node.data.get("alt") or node.name or "asset"), quote=True)
            url = escape(
                str(
                    node.data.get("uri")
                    or node.data.get("url")
                    or node.data.get("path")
                    or ""
                ),
                quote=True,
            )
            return [f'{indent}<img src="{url}" alt="{alt}">']
        return []

    def _render_block(
        self,
        graph: DomainGraph,
        node: DomainNode,
        heading_level: int,
        indent: str,
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
            language = escape(str(node.data.get("language", "")), quote=True)
            lines = [
                f'{indent}<pre><code data-language="{language}">{escape(text)}</code></pre>'
            ]
        elif kind == "quote":
            lines = [f"{indent}<blockquote>{escape(text)}</blockquote>"]
        elif kind == "list":
            items = node.data.get("items")
            values = items if isinstance(items, list) else text.splitlines()
            lines = [f"{indent}<ul>"]
            lines.extend(f"{indent}  <li>{escape(str(item))}</li>" for item in values)
            lines.append(f"{indent}</ul>")
        else:
            lines = [f"{indent}<p>{escape(text)}{markers}</p>"]
        if markers and kind in {"code", "quote", "list"}:
            lines.append(f'{indent}<p class="citations">{markers}</p>')
        for child in ordered_children(graph, node.id):
            if child.entity_type != "citation":
                lines.extend(
                    self._render_node(
                        graph,
                        child,
                        heading_level=heading_level,
                        indent=indent,
                    )
                )
        return lines

    def _citation_marker(self, graph: DomainGraph, citation: DomainNode) -> str:
        source = citation_source(graph, citation.id)
        self._citations.append((citation, source))
        citation_id = _html_id(citation.id)
        number = len(self._citations)
        return f'<sup><a href="#{citation_id}">[{number}]</a></sup>'
