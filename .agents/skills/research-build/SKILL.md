---
name: research-build
description: Research a question and build a validated, source-traceable ResearchDomainGraph. Use when starting from a question, hypothesis, or topic; converting completed research into a reading belongs to research-content.
---

# Research Build

Run the checkpointed `ResearchBuildPipeline`. The pipeline owns completion;
research is unfinished until its task DAG and semantic quality gates pass.

## Workflow

1. Read [the pipeline protocol](references/pipeline.md), then run
   `domain-graph-research --workspace . status`. Initialize only when the
   workspace has no research checkpoint.
2. Execute only task IDs returned in `ready_task_ids`. Start a task before doing
   its work, use the relevant source tools, and save the required result record
   before marking it complete.
3. Continue through specification, discovery, challenge, and synthesis. A
   failed task remains a checkpointed retry; resume it instead of replacing the
   plan or writing the final graph directly.
4. Run `materialize` after every task is complete. It deterministically creates
   the draft graph from checkpoints. If it reports an invalid checkpoint, use
   `reopen` on each named task and execute the reopened dependency chain.
5. Run `validate` on the materialized draft, resolve every issue, then run
   `finalize` without supplying another graph. Treat successful `finalize` as
   the only completion signal.
6. Deliver `.research/research.domain-graph.json`, the plan and coverage report,
   plus a compact summary of surviving explanations, contradictions, source
   quality, unsupported claims, and uncertainty.

## Graph contract

- Create the graph with `ResearchDomainAdapter().create_graph(...,
  strict_schema=True)`.
- Use `question`, `theory`, `claim`, `evidence`, and `source` nodes. Link each
  theory to claims with `explains`; retain `contains`, `supports`,
  `contradicts`, and `derived_from` semantics.
- Keep node IDs stable and descriptive across revisions. Store JSON-native
  metadata in `data`; keep the human-readable assertion or observation in
  `name` or a documented `data` field.
- Every delivered claim belongs to a question. Every support or contradiction
  is represented by evidence, and every evidence node identifies at least one
  source. Label inference or synthesis explicitly instead of assigning it false
  source provenance.
- Do not manufacture agreement by dropping contrary findings. Report a claim as
  unsupported when adequate evidence was not found.
- A source counts only when its stable locator and access date were captured in
  a completed retrieval task. A theory counts only when it has both explained
  claims and contradictory evidence.

When `domain-graph-research` is unavailable or lacks these commands, report the
missing workflow version. A handwritten replacement graph is not a fallback.

The adapter contract and a runnable graph example live in the
[Domain Graph 0.2.0 guide](https://github.com/KiwataHoko/RPG-ZeroRepo/blob/domain-graph-v0.2.0/domain_graph/README.md).
This skill stops at the research graph. Use `$research-content` to map validated
findings into a content graph, then `$publish-content` to render Markdown or
HTML.
