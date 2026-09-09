"""Deterministic edge-case coverage for the domain graph v1 wire format."""

import json

import pytest

from domain_graph import (
    DomainGraph,
    DomainSchema,
    DuplicateNodeError,
    HierarchyCycleError,
    NodeNotFoundError,
    RelationSpec,
)


def _schema() -> DomainSchema:
    return DomainSchema(
        "兼容性 / v1",
        entity_types=("父节点", "子节点"),
        relations=(
            RelationSpec("包含 / hierarchy", hierarchy=True),
            RelationSpec("关联"),
        ),
    )


def _graph_with_json_native_data() -> DomainGraph:
    graph = DomainGraph("研究\n\"实验\" / 🧪", _schema(), strict_schema=True)
    graph.add_node(
        "父/😀",
        "父节点",
        name="根节点\n含引号\"和反斜杠\\",
        data={
            "null": None,
            "bool": True,
            "integer": 2**80 + 123,
            "float": -12345.6789,
            "nested": {
                "列表": [None, False, {"特殊键\t": "值\u0000"}],
                "空对象": {},
            },
        },
    )
    graph.add_node("子/\tline\n", "子节点", data={"enabled": False})
    graph.add_edge(
        "父/😀",
        "子/\tline\n",
        "包含 / hierarchy",
        data={"weight": 0.125, "metadata": ["第一项", {"ok": True}]},
    )
    return graph


def test_json_round_trip_preserves_unicode_special_characters_and_native_data():
    graph = _graph_with_json_native_data()

    payload = graph.to_json()

    assert "研究" in payload
    assert "😀" in payload
    assert "\\n" in payload
    assert "\\u0000" in payload
    restored = DomainGraph.from_json(payload)

    assert restored.to_dict() == graph.to_dict()
    assert restored.get_node("父/😀").data["integer"] == 2**80 + 123
    assert restored.get_node("父/😀").data["nested"]["列表"][2]["特殊键\t"] == "值\u0000"


@pytest.mark.parametrize("payload", [None, [], "text", 0, True])
def test_from_dict_rejects_non_object_top_level_payloads(payload):
    with pytest.raises(ValueError, match="object"):
        DomainGraph.from_dict(payload)


@pytest.mark.parametrize("payload", ["[]", "null", '"text"', "not json"])
def test_from_json_rejects_malformed_top_level_payloads(payload):
    with pytest.raises(ValueError):
        DomainGraph.from_json(payload)


def test_restore_rejects_edge_with_missing_endpoint():
    payload = _graph_with_json_native_data().to_dict()
    payload["edges"].append(
        {
            "source": "父/😀",
            "target": "missing",
            "relation": "关联",
            "data": {},
        }
    )

    with pytest.raises(NodeNotFoundError, match="missing"):
        DomainGraph.from_dict(payload)


def test_restore_rejects_duplicate_node_ids():
    payload = _graph_with_json_native_data().to_dict()
    payload["nodes"].append(payload["nodes"][0].copy())

    with pytest.raises(DuplicateNodeError, match="already exists"):
        DomainGraph.from_dict(payload)


def test_restore_rejects_hierarchy_cycle():
    schema = DomainSchema(
        "cycle",
        entity_types=("node",),
        relations=(RelationSpec("contains", hierarchy=True),),
    )
    payload = DomainGraph("cycle", schema).to_dict()
    payload["nodes"] = [
        {"id": "a", "entity_type": "node", "name": "", "data": {}},
        {"id": "b", "entity_type": "node", "name": "", "data": {}},
    ]
    payload["edges"] = [
        {"source": "a", "target": "b", "relation": "contains", "data": {}},
        {"source": "b", "target": "a", "relation": "contains", "data": {}},
    ]

    with pytest.raises(HierarchyCycleError, match="creates a cycle"):
        DomainGraph.from_dict(payload)


@pytest.mark.parametrize("location", ["node", "edge"])
def test_to_json_rejects_non_json_serializable_data(location):
    graph = DomainGraph("non-json", _schema())
    graph.add_node("parent", "父节点")
    graph.add_node("child", "子节点")
    if location == "node":
        graph.get_node("parent").data["bad"] = object()
    else:
        graph.add_edge("parent", "child", "关联", data={"bad": object()})

    with pytest.raises(TypeError):
        graph.to_json()


def test_restore_ignores_unknown_extra_fields_and_emits_canonical_v1():
    graph = _graph_with_json_native_data()
    payload = graph.to_dict()
    payload["future_graph_field"] = {"version": 2}
    payload["schema"]["future_schema_field"] = "ignored"
    payload["schema"]["relations"][0]["future_relation_field"] = True
    payload["nodes"][0]["future_node_field"] = [1, 2, 3]
    payload["edges"][0]["future_edge_field"] = None

    restored = DomainGraph.from_dict(payload)

    assert restored.to_dict() == graph.to_dict()


def test_repeated_semantic_round_trips_are_stable():
    expected = _graph_with_json_native_data().to_dict()
    current = DomainGraph.from_dict(expected)

    for _ in range(5):
        current = DomainGraph.from_json(current.to_json())
        assert current.to_dict() == expected
        assert json.loads(current.to_json()) == expected


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_to_json_rejects_non_finite_floats_in_nested_data(value):
    graph = DomainGraph("finite", _schema())
    graph.add_node("parent", "父节点", data={"nested": [{"value": value}]})

    with pytest.raises(ValueError, match="finite"):
        graph.to_json()


@pytest.mark.parametrize("key", [1, 1.5, None, True, ("tuple",)])
def test_to_json_rejects_non_string_mapping_keys_before_coercion(key):
    graph = DomainGraph("string-keys", _schema())
    graph.add_node("parent", "父节点", data={"nested": {key: "value"}})

    with pytest.raises(TypeError, match="string"):
        graph.to_json()


def test_to_json_rejects_nested_tuples_without_coercion():
    graph = DomainGraph("tuple", _schema())
    graph.add_node("parent", "父节点", data={"nested": [{"value": ("a", "b")}]})

    with pytest.raises(TypeError, match="tuple"):
        graph.to_json()
