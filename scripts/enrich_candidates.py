#!/usr/bin/env python3
"""Annotate issue candidates with labels, dates, PR status, and last human feedback."""

import argparse
import json
import re
import sys
from pathlib import Path

BOT_LOGIN = "bacluc-agent"
BODY_EXCERPT_LEN = 160


def issue_numbers_for_pr(pr, issue_repository):
    numbers = set()
    match = re.match(r"^issue-(\d+)", pr.get("headRefName") or "")
    if match:
        numbers.add(int(match.group(1)))
    title = pr.get("title") or ""
    for match in re.finditer(r"issue[- ]#?(\d+)(?![0-9])", title):
        numbers.add(int(match.group(1)))
    if issue_repository:
        tracker_re = re.compile(rf"{re.escape(issue_repository)}#(\d+)")
        for text in (title, pr.get("body") or ""):
            for match in tracker_re.finditer(text):
                numbers.add(int(match.group(1)))
    return numbers


def pr_repo(pr):
    match = re.search(r"github\.com/([^/]+/[^/]+)/pull/", pr.get("url") or "")
    return match.group(1) if match else ""


def load_prs(paths, issue_repository):
    prs_by_number = {}
    for path in paths:
        try:
            data = json.loads(Path(path).read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(data, list):
            continue
        for pr in data:
            if not isinstance(pr, dict) or not isinstance(pr.get("number"), int):
                continue
            prs_by_number[(pr_repo(pr), pr["number"])] = pr
    matches = {}
    for pr in prs_by_number.values():
        for issue in issue_numbers_for_pr(pr, issue_repository):
            current = matches.get(issue)
            if current is None or (pr.get("updatedAt", ""), pr["number"]) > (
                current.get("updatedAt", ""),
                current["number"],
            ):
                matches[issue] = pr
    return matches


def is_bot(login):
    return login == BOT_LOGIN or (login or "").endswith("[bot]")


def last_human_feedback(comments_json_path):
    try:
        data = json.loads(Path(comments_json_path).read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    data_body = data.get("data")
    repository = data_body.get("repository") if isinstance(data_body, dict) else None
    if not isinstance(repository, dict):
        return {}
    result = {}
    for alias, issue in repository.items():
        match = re.fullmatch(r"i(\d+)", alias or "")
        if not match or not isinstance(issue, dict):
            continue
        comments = issue.get("comments")
        nodes = comments.get("nodes") if isinstance(comments, dict) else None
        if not isinstance(nodes, list):
            nodes = []
        human = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            author = node.get("author")
            login = author.get("login") if isinstance(author, dict) else None
            if node.get("createdAt") and not is_bot(login):
                human.append(node["createdAt"])
        if human:
            result[int(match.group(1))] = max(human)
    return result


def body_excerpt(body):
    text = re.sub(r"\s+", " ", body or "").strip().replace('"', "'")
    return text[:BODY_EXCERPT_LEN]


def format_candidate(item, pr, last_human):
    labels = ",".join(label.get("name", "") for label in item.get("labels") or [])
    created = (item.get("created_at") or "")[:10]
    comments = item.get("comments") or 0
    if pr is None:
        pr_field = "none"
    else:
        pr_field = f"{pr_repo(pr)}#{pr['number']}:{pr['state']}@{pr.get('updatedAt', '')}"
    return (
        f"{item['number']}: {item['title']} | labels={labels} | created={created} "
        f"| comments={comments} | pr={pr_field} | last-human={last_human or 'none'} "
        f'| body="{body_excerpt(item.get("body"))}"'
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search-json", required=True)
    parser.add_argument("--issue-repository", required=True)
    parser.add_argument("--comments-json")
    parser.add_argument("pr_files", nargs="*")
    args = parser.parse_args(argv)

    try:
        items = json.loads(Path(args.search_json).read_text())
    except (OSError, ValueError):
        return 1
    if not isinstance(items, list):
        return 1

    prs = load_prs(args.pr_files, args.issue_repository)
    feedback = last_human_feedback(args.comments_json) if args.comments_json else {}
    for item in items:
        if not isinstance(item, dict):
            continue
        number = item.get("number")
        print(format_candidate(item, prs.get(number), feedback.get(number)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
