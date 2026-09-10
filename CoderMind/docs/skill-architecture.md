# Skill architecture

CoderMind skills are user-facing workflow entry points, not homes for domain
models or reusable business logic. Keep each concern in one layer:

```text
skill -> pipeline/service -> domain adapter -> domain graph -> renderer/codec
```

## Naming boundary

The `cmind-` prefix is reserved for workflows that invoke the `cmind` CLI or
operate on CoderMind-owned artifacts. Cross-domain capabilities use neutral,
action-oriented names. For example, `research-content` converts grounded
research into a portable content graph, while `publish-content` renders a valid
content graph. Neither depends on CoderMind.

## Sources of truth

- `templates/commands/*.md` defines CoderMind workflows.
- `src/cmind_cli/agent_adapters.py` materializes those workflows for Codex, Pi,
  and oh-my-pi.
- A generated workspace stores the host execution protocol once at
  `.agents/cmind/host-protocol.md` or `.omp/cmind/host-protocol.md`.
- Generated `cmind-*` skill folders point to that shared protocol and can be
  regenerated safely.
- Standalone cross-domain skills live directly under `.agents/skills/` and are
  tracked independently of generated CoderMind skills.

## Growth rules

Create a new skill only for a distinct user intent. Adding a domain adapter,
validator, transformation, output format, or storage backend does not by itself
require another skill. Prefer one skill that selects among compatible pipelines
over a skill for every input/output combination.

Keep the main `SKILL.md` focused on routing, required state checks, irreversible
boundaries, and completion criteria. Move branch-specific procedures to linked
references and deterministic repeated operations to scripts. Runtime schemas,
serialization contracts, and graph invariants belong in code and tests.

## Current migration

The first migration removes the repeated host-model protocol from every
generated skill. Later passes should target the largest command templates,
starting with `rpg_edit.md` and `feature_construct.md`, and extract only details
that are conditional or already discoverable from CLI help. Existing command
behavior and invocation names remain compatible during that work.
