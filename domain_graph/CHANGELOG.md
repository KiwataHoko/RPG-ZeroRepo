# Changelog

## 0.2.0 - 2026-09-10

- Add `ContentDomainAdapter` for format-neutral documents, sections, content
  blocks, assets, citations, and cross-graph source references.
- Provide focused builders for document structure and citation provenance while
  keeping research-to-content transformation and rendering outside the adapter.
- Add `ResearchToContentMapper` with stable source references, selective claim
  mapping, evidence citations, and claim-coverage reporting.
- Add dependency-free Markdown and escaped HTML renderers for validated content
  graphs, including explicit sibling ordering and citation references.
- Add an immutable v1 content fixture and retain compatibility checks against
  the published 0.1.0 reader.
- Add neutral `research-content` and `publish-content` skills without coupling
  cross-domain content workflows to the CoderMind CLI namespace.

## 0.1.1 - 2026-09-09

- Document the v1 compatibility policy: v1 payloads and public imports remain
  backward compatible within the `0.1.x` release line; readers reject
  unsupported wire versions rather than guessing their meaning.
- Define immutable v1 golden fixtures as the compatibility baseline. Restore
  and query semantics must remain equivalent; JSON byte-for-byte output is not
  required because formatting and key order may differ.
- Record the adapter acceptance contract: a real adapter must preserve domain
  identifiers, symbols, relations, and JSON-native data, pass validation for
  its declared schema, and survive a semantic JSON round-trip.
- Clarify that node and edge data must be JSON-native. Before introducing wire
  format v2, the project must publish an explicit migration path and coverage
  for reading all supported historical fixtures.

## 0.1.0 - 2026-09-09

- Establish `domain_graph` as an independently installable Python package.
- Freeze the initial public core API exported from `domain_graph`.
- Add `ResearchDomainAdapter` as the first non-code reference adapter.
- Keep schemas open-world by default with opt-in strict validation.
- Add release metadata, license packaging, clean wheel/sdist install checks,
  checksums, and a tag-driven GitHub Release workflow.

Compatibility policy: serialized graph format version 1 remains readable across
the `0.x` release lines. Public imports remain backward compatible within each
minor release line. Breaking API or wire-format changes require an explicit
migration, version increment, and changelog entry.
