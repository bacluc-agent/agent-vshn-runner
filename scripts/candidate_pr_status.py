#!/usr/bin/env python3

import json
import re
import sys

BRANCH_RE = re.compile(r"^issue-(\d+)")
TITLE_RE = re.compile(r"#(\d+)|issue[- ]#?(\d+)")


def issue_numbers_for_pr(pr: dict) -> set[int]:
    numbers = set()
    match = BRANCH_RE.match(pr.get("headRefName") or "")
    if match:
        numbers.add(int(match.group(1)))
    for match in TITLE_RE.finditer(pr.get("title") or ""):
        numbers.add(int(match.group(1) or match.group(2)))
    return numbers


def main() -> int:
    with open(sys.argv[1]) as candidates_file:
        candidates = {int(line) for line in candidates_file if line.strip()}

    prs_by_number = {}
    for path in sys.argv[2:]:
        with open(path) as prs_file:
            for pr in json.load(prs_file):
                prs_by_number[pr["number"]] = pr  # later inputs win

    matches = {}
    for pr in prs_by_number.values():
        for issue in issue_numbers_for_pr(pr):
            if issue not in candidates:
                continue
            current = matches.get(issue)
            if current is None or (pr.get("updatedAt", ""), pr["number"]) > (
                current.get("updatedAt", ""),
                current["number"],
            ):
                matches[issue] = pr

    for issue in sorted(matches):
        pr = matches[issue]
        print(f"{issue}\t{pr['url']} ({pr['state']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())