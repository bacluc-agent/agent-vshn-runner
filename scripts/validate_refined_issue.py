"""Validate refiner output. #120 owns this contract; #124 exercises it offline."""

import argparse
import re
import sys
from pathlib import Path

_FENCE_OPEN_RE = re.compile(r"^`{3,}\s*[A-Za-z0-9_-]*\s*$")
_FENCE_CLOSE_RE = re.compile(r"^`{3,}\s*$")
# ponytail: illustrative marker/secret shapes, not a secret scanner; extend when a real leak shape appears
_HOSTILE_RE = re.compile(
    r"begin_prompt|end_prompt|selected_issue:"
    r"|ignore (all |the )?(previous|prior) instructions"
    r"|sk-[a-z0-9]{16,}|gh[pousr]_[a-z0-9]{16,}|github_pat_[a-z0-9_]{16,}",
    re.IGNORECASE,
)
_REQUIRED_HEADINGS = ("## Goal", "## How to implement")


def _section_empty(stripped: list[str], heading_idx: int) -> bool:
    # ponytail: only top-level "## " headings bound a section; nested structure is not parsed
    for line in stripped[heading_idx + 1 :]:
        if line.startswith("## "):
            break
        if line:
            return False
    return True


def validate_refined_body(text: str) -> tuple[bool, str]:
    stripped = [line.strip() for line in text.splitlines()]
    if not any(stripped):
        return False, "empty"
    content = [line for line in stripped if line]
    # ponytail: fence detection reads only first/last non-blank lines; unbalanced or
    # interior fences fall through to the structural checks below and get rejected there
    if (
        len(content) >= 2
        and _FENCE_OPEN_RE.match(content[0])
        and _FENCE_CLOSE_RE.match(content[-1])
    ):
        return False, "fenced_output"
    goal_idx = stripped.index("## Goal") if "## Goal" in stripped else -1
    impl_idx = (
        stripped.index("## How to implement")
        if "## How to implement" in stripped
        else -1
    )
    if goal_idx == -1:
        return False, "missing_goal_heading"
    if impl_idx == -1:
        return False, "missing_impl_heading"
    if impl_idx < goal_idx:
        return False, "wrong_order"
    if _section_empty(stripped, goal_idx):
        return False, "empty_goal"
    if _section_empty(stripped, impl_idx):
        return False, "empty_how_to_implement"
    if any(
        # ponytail: exact-match headings only; "##  Goal" (double space) counts as an extra section
        line.startswith("## ") and line not in _REQUIRED_HEADINGS
        for line in content
    ):
        return False, "extra_sections"
    if _HOSTILE_RE.search(text):
        return False, "hostile_text"
    return True, "ok"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True)
    args = parser.parse_args(argv)
    try:
        text = Path(args.file).read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""  # ponytail: unreadable file fails safely as empty; the workflow tee guarantees the file exists
    ok, reason = validate_refined_body(text)
    print(f"REFINE_VALIDATION: {reason}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
