#!/usr/bin/env python3

import json
import re
import sys

BRANCH_RE = re.compile(r"^issue-(\d+)(?=$|[^A-Za-z0-9])")
TITLE_RE = re.compile(r"#(\d+)(?=$|[^A-Za-z0-9])|issue[- ]#?(\d+)(?=$|[^A-Za-z0-9])")
FENCE_RE = re.compile(r"</?candidate-data>", re.IGNORECASE)


def sanitize_untrusted(value) -> str:
    return FENCE_RE.sub(lambda match: match.group(0).replace("<", "[").replace(">", "]"), str(value))


def issue_numbers_for_pr(pr: dict) -> set[int]:
    numbers = set()
    match = BRANCH_RE.match(pr.get("headRefName") or "")
    if match:
        numbers.add(int(match.group(1)))
    for match in TITLE_RE.finditer(pr.get("title") or ""):
        numbers.add(int(match.group(1) or match.group(2)))
    return numbers


def is_bot_author(author) -> bool:
    if isinstance(author, str):
        login, kind = author, ""
    else:
        author = author or {}
        login = author.get("login") or ""
        kind = author.get("type") or ""
    return login == "bacluc-agent" or login.endswith("[bot]") or kind == "Bot"


def last_human_feedback(comments) -> str | None:
    times = [
        comment.get("created_at", "")
        for comment in comments
        if not is_bot_author(comment.get("author") or comment.get("user"))
    ]
    times = [created for created in times if created]
    return max(times) if times else None


def render_candidate(item, pr, feedback) -> str:
    number = item.get("number", "")
    created = (item.get("created_at") or "")[:10] or "unknown"
    labels = ", ".join(sanitize_untrusted(label.get("name", "")) for label in (item.get("labels") or []))
    line = f"#{number} [created {created}] [{labels}] {sanitize_untrusted(item.get('title', ''))}".rstrip()
    if pr is None:
        line += " | PR: none"
    else:
        line += f" | PR: {sanitize_untrusted(pr.get('repo', ''))}#{pr['number']} {pr['state']} {pr.get('updatedAt', '')}"
    line += f" | last-human-feedback: {feedback or 'none'}"
    return line


def recent_picks(prs, limit=15) -> list[str]:
    picks = []
    for pr in prs:
        if pr.get("repo") != "bacluc-agent/agent-vshn-runner":
            continue
        head = pr.get("headRefName") or ""
        if BRANCH_RE.match(head):
            picks.append(sanitize_untrusted(head))
            if len(picks) >= limit:
                break
    return picks


def annotate(items, feedback_map, prs) -> list[str]:
    matches = {}
    for pr in prs:
        for issue in issue_numbers_for_pr(pr):
            current = matches.get(issue)
            if current is None or (pr.get("updatedAt", ""), pr["number"]) > (
                current.get("updatedAt", ""),
                current["number"],
            ):
                matches[issue] = pr

    lines = [render_candidate(item, matches.get(item.get("number")), feedback_map.get(str(item.get("number")))) for item in items]
    picks = recent_picks(prs)
    lines.append("recent-picks: " + (", ".join(picks) if picks else "none"))
    return lines


def _load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def load_json_list(path) -> list:
    data = _load_json(path, [])
    return data if isinstance(data, list) else []


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
        print(f"{issue}\t{pr.get('url', '')} ({pr['state']})")
    return 0


def main_annotate() -> int:
    candidates_path = sys.argv[2]
    search_path = sys.argv[3]
    feedback_path = sys.argv[4]
    prs_paths = sys.argv[5:]

    try:
        with open(candidates_path) as candidates_file:
            candidates = {int(line) for line in candidates_file if line.strip()}
    except (OSError, ValueError):
        candidates = set()

    items = load_json_list(search_path)
    if items:
        items = [item for item in items if item.get("number") in candidates]
    else:
        items = [{"number": number} for number in sorted(candidates)]

    feedback_map = {}
    feedback_data = _load_json(feedback_path, {})
    if isinstance(feedback_data, dict):
        for key, value in feedback_data.items():
            if isinstance(value, str):
                feedback_map[str(key)] = value
            elif isinstance(value, list):
                latest = last_human_feedback(value)
                if latest:
                    feedback_map[str(key)] = latest

    prs = []
    for path in prs_paths:
        prs.extend(load_json_list(path))

    for line in annotate(items, feedback_map, prs):
        print(line)
    return 0


def main_fallback() -> int:
    for item in load_json_list(sys.argv[2]):
        print(f"#{item.get('number', '')} {sanitize_untrusted(item.get('title', ''))}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--annotate":
        sys.exit(main_annotate())
    if len(sys.argv) > 1 and sys.argv[1] == "--fallback":
        sys.exit(main_fallback())
    sys.exit(main())
