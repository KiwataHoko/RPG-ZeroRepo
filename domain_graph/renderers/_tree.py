"""Shared content-tree traversal and citation helpers."""

from ..adapters import ContentDomainAdapter
from ..graph import DomainGraph
from ..model import DomainNode


def select_document(graph: DomainGraph, document_id: str | None) -> DomainNode:
    issues = ContentDomainAdapter().validate_content(graph)
    if issues:
        summary = ", ".join(f"{issue.kind}@{issue.location}" for issue in issues)
        raise ValueError(f"invalid content graph: {summary}")
    if document_id is not None:
        document = graph.get_node(document_id)
        if document.entity_type != "document":
            raise ValueError(f"node {document_id!r} is not a document")
        return document
    documents = graph.get_nodes_by_type("document")
    if len(documents) != 1:
        raise ValueError("document_id is required when a graph has multiple documents")
    return documents[0]


def ordered_children(graph: DomainGraph, parent_id: str) -> tuple[DomainNode, ...]:
    children = list(graph.children(parent_id))
    if len(children) < 2:
        return tuple(children)
    positions = {node.id: index for index, node in enumerate(children)}
    adjacency = {node.id: set() for node in children}
    indegree = {node.id: 0 for node in children}
    for edge in graph.edges:
        if (
            edge.relation != "precedes"
            or edge.source not in positions
            or edge.target not in positions
            or edge.target in adjacency[edge.source]
        ):
            continue
        adjacency[edge.source].add(edge.target)
        indegree[edge.target] += 1

    ready = sorted(
        (node_id for node_id, degree in indegree.items() if degree == 0),
        key=positions.__getitem__,
    )
    result = []
    while ready:
        node_id = ready.pop(0)
        result.append(graph.get_node(node_id))
        for target in sorted(adjacency[node_id], key=positions.__getitem__):
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
                ready.sort(key=positions.__getitem__)
    if len(result) != len(children):
        raise ValueError(f"precedes cycle among children of {parent_id!r}")
    return tuple(result)


def citation_source(graph: DomainGraph, citation_id: str) -> DomainNode:
    targets = tuple(
        graph.get_node(edge.target)
        for edge in graph.edges
        if edge.source == citation_id and edge.relation == "cites"
    )
    if len(targets) != 1:
        raise ValueError(f"citation {citation_id!r} must cite exactly one source")
    return targets[0]
