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
| `candidate-theories` | `theories` with at least two normalized theory records |
| `textbook-search` | `sources`, including a verified textbook |
| `evidence-search` | `sources`, `claims`, `evidence` |
| `counterexample-search` | `sources`, normalized `counterexamples` |
| `discriminatory-tests` | `comparisons` |
| `synthesize` | `claim_ids`, `revisions` |

Every retrieved source record contains `id`, `source_type`, `locator`, and
`accessed_at`. The locator is the URL, DOI, ISBN, repository path, or document
ID actually opened. Preserve page, chapter, section, table, or timestamp in the
evidence node.

Each theory contains `id`, `name`, `mechanism`, `boundary_conditions`,
`failure_conditions`, and `predictions`. Each claim contains `id`, `name`, and
`theory_ids`. Evidence and counterexample records contain `id`, `name`,
`claim_id`, `source_id`, `locator`, and `relation`; their relations are
`supports` and `contradicts`, respectively.

When an upgraded result contract invalidates an older checkpoint, reopen it and
its transitive dependents:

```bash
domain-graph-research --workspace . reopen TASK_ID
```

## Validate and finalize

```bash
domain-graph-research --workspace . materialize
domain-graph-research --workspace . validate \
  --graph .research/draft-research.json
domain-graph-research --workspace . finalize
```

Finalization cross-checks the graph against retrieval and counterexample
checkpoints, performs semantic validation and a JSON round trip, then writes
`.research/research.domain-graph.json` and `.research/coverage-report.json`.
