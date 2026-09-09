# Changelog

## Unreleased

- Add `ContentDomainAdapter` for format-neutral documents, sections, content
  blocks, assets, citations, and cross-graph source references.
- Provide focused builders for document structure and citation provenance while
  keeping research-to-content transformation and rendering outside the adapter.

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

Compatibility policy for the `0.1.x` line: serialized graph format version 1
and public imports remain backward compatible within the patch-release line.
Breaking API or wire-format changes require a version increment and changelog
entry.
