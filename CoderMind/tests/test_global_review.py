from __future__ import annotations

import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from code_gen import global_review as gr  # noqa: E402


def test_extract_review_checklist_parses_cli_screen_count() -> None:
    response = """\
### Tool Usage
- Pages inspected: 0
- Forms tested: 0
- Screenshots taken: 0
- CLI screens inspected: 1
"""

    checklist = gr._extract_review_checklist(response)

    assert checklist["cli_screens_inspected"] == 1


def test_cli_project_accepts_cli_screen_evidence_without_screenshots() -> None:
    checklist = {
        "pages_inspected": 0,
        "screenshots_taken": 0,
        "cli_screens_inspected": 1,
    }
    feature_spec = {"meta": {"project_types": ["CLI", "PIPELINE"]}}

    used, requirement = gr._review_tool_evidence(checklist, feature_spec)

    assert used is True
    assert requirement == "cli"


def test_web_project_still_requires_browser_or_screenshot_evidence() -> None:
    checklist = {
        "pages_inspected": 0,
        "screenshots_taken": 0,
        "cli_screens_inspected": 1,
    }
    feature_spec = {"meta": {"project_types": ["WEB", "CLI"]}}

    used, requirement = gr._review_tool_evidence(checklist, feature_spec)

    assert used is False
    assert requirement == "visual"


def test_noninteractive_project_does_not_require_visual_evidence() -> None:
    checklist = {
        "pages_inspected": 0,
        "screenshots_taken": 0,
        "cli_screens_inspected": 0,
    }
    feature_spec = {"meta": {"project_types": ["LIBRARY"]}}

    used, requirement = gr._review_tool_evidence(checklist, feature_spec)

    assert used is True
    assert requirement == "none"


def test_missing_project_metadata_preserves_visual_evidence_requirement() -> None:
    checklist = {
        "pages_inspected": 0,
        "screenshots_taken": 0,
        "cli_screens_inspected": 1,
    }

    used, requirement = gr._review_tool_evidence(checklist, {})

    assert used is False
    assert requirement == "visual"
