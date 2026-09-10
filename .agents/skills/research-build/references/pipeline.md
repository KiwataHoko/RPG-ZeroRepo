# Research pipeline protocol

Use the project interpreter when one is specified, for example
`.venv/bin/domain-graph-research`; otherwise use `domain-graph-research`.

## Initialize or resume

```bash
domain-graph-research --workspace . status
domain-graph-research --workspace . init \
  --question "Research question" \
  --constraint "Material constraint" \
  --success-criterion "Observable completion criterion"
```

`status` is authoritative. Execute every ready task, repeat after each
completion, and stop only after `complete` is true.

## Execute one task

```bash
domain-graph-research --workspace . start TASK_ID
domain-graph-research --workspace . complete TASK_ID \
  --result-file .research/results/TASK_ID.json
```

Record a failed attempt instead of hiding it:

```bash
domain-graph-research --workspace . fail TASK_ID \
  --result-file .research/results/TASK_ID.failure.json
```

Required non-empty result fields:

| Task | Fields |
| --- | --- |
| `define-concepts` | `concepts`, `distinctions`, `acceptance_tests` |
| `candidate-theories` | `theories` with at least two stable IDs |
| `textbook-search` | `sources`, including a verified textbook |
| `evidence-search` | `sources`, `claim_ids` |
| `counterexample-search` | `sources`, `counterexamples` containing `claim_id` |
| `discriminatory-tests` | `comparisons` |
| `synthesize` | `claim_ids`, `revisions` |

Every retrieved source record contains `id`, `source_type`, `locator`, and
`accessed_at`. The locator is the URL, DOI, ISBN, repository path, or document
ID actually opened. Preserve page, chapter, section, table, or timestamp in the
evidence node.

## Validate and finalize

```bash
domain-graph-research --workspace . validate --graph draft-research.json
domain-graph-research --workspace . finalize --graph draft-research.json
```

Finalization cross-checks the graph against retrieval and counterexample
checkpoints, performs semantic validation and a JSON round trip, then writes
`.research/research.domain-graph.json` and `.research/coverage-report.json`.
