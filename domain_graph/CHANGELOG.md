# Changelog

## 0.1.0 - 2026-09-09

- Establish `domain_graph` as an independently installable Python package.
- Freeze the initial public core API exported from `domain_graph`.
- Add `ResearchDomainAdapter` as the first non-code reference adapter.
- Keep schemas open-world by default with opt-in strict validation.
- Add release metadata, license packaging, clean wheel/sdist install checks,
  checksums, and a tag-driven GitHub Release workflow.

Compatibility policy for the 0.x series: serialized graph format version 1 and
public imports remain backward compatible within a minor release. Breaking API
or wire-format changes require a version increment and changelog entry.
