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

Both `--constraint` and `--success-criterion` are repeatable and each group must
contain at least one non-empty value. `status` is authoritative. Execute every
ready task, repeat after each completion, and stop only after `complete` is true.

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

The CLI copies the exact submitted payload to
`.research/checkpoints/TASK_ID/attempt-NNNN.completed.json` or
`attempt-NNNN.failed.json` and removes write permission. Treat these files as
the audit record; create a new attempt instead of editing one.

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

Every retrieved source record contains `id`, `source_type`, `locator`,
`accessed_at`, and `authenticity_review`. The review has `status: "passed"` and
a non-empty `method` describing the publisher, repository, registry, or primary
record checked. Allowed source types are `book`, `dataset`,
`government_report`, `official_statistics`, `paper`,
`peer_reviewed_article`, `primary_document`, `standards_document`, `textbook`,
and `working_paper`; a self-authored analysis is not a source.

Use a URL, DOI, ISBN-13, repository path, or document ID that was actually
opened. URL and DOI syntax and the ISBN-13 checksum must pass. Sources are
normalized and deduplicated by DOI first, ISBN second, then URL; aliases resolve
to one graph source and therefore cannot inflate coverage.

Each theory contains `id`, `name`, `mechanism`, `boundary_conditions`,
`failure_conditions`, and `predictions`. Each claim contains `id`, `name`, and
`theory_ids`. Supporting evidence contains `id`, `name`, `claim_id`,
`source_id`, `locator`, `relation: "supports"`, a concrete `observation`, and
`reasoning` that states why the observation supports the claim.

A counterexample contains `id`, `name`, `claim_id`, `source_id`, `locator`,
`relation: "contradicts"`, `challenged_prediction`, `observation`,
`conflict_reason`, `rival_theory_id`, `rival_prediction`, and `logic_review`.
The logic review has `status: "passed"` and a reason. The challenged prediction
must be declared by a theory explaining the claim; the rival prediction must be
declared by a different candidate theory. Preserve page, chapter, section,
table, or timestamp in every evidence locator.

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
checkpoints, counts only authenticity- and logic-reviewed coverage, performs
semantic validation and a JSON round trip, then writes
`.research/research.domain-graph.json` and `.research/coverage-report.json`.
