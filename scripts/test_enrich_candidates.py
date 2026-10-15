import json
import sys

import enrich_candidates

ISSUE_REPO = "bacluc-agent/agent-vshn-todo"


def write_json(path, data):
    path.write_text(json.dumps(data))
    return path


def run(
    tmp_path,
    monkeypatch,
    capsys,
    items,
    *pr_files,
    comments_path=None,
    issue_repository=ISSUE_REPO,
):
    search = write_json(tmp_path / "search.json", items)
    argv = [
        "enrich_candidates",
        "--search-json",
        str(search),
        "--issue-repository",
        issue_repository,
    ]
    if comments_path is not None:
        argv += ["--comments-json", str(comments_path)]
    argv += [str(path) for path in pr_files]
    monkeypatch.setattr(sys, "argv", argv)
    status = enrich_candidates.main()
    return status, capsys.readouterr().out.splitlines()


def pr(
    number,
    state,
    head_ref,
    title,
    updated_at,
    repo="bacluc-agent/agent-vshn-runner",
    body="",
):
    return {
        "number": number,
        "state": state,
        "title": title,
        "headRefName": head_ref,
        "url": f"https://github.com/{repo}/pull/{number}",
        "updatedAt": updated_at,
        "body": body,
    }


def test_free_fields_formatted(tmp_path, monkeypatch, capsys):
    items = [
        {
            "number": 15,
            "title": "Fix the thing",
            "labels": [{"name": "bug"}, {"name": "ready-for-implementation"}],
            "created_at": "2026-09-11T07:42:48Z",
            "comments": 3,
            "body": "First line\nsecond line",
        }
    ]
    status, lines = run(tmp_path, monkeypatch, capsys, items)
    assert status == 0
    assert lines == [
        "15: Fix the thing | labels=bug,ready-for-implementation | created=2026-09-11 "
        '| comments=3 | pr=none | last-human=none | body="First line second line"'
    ]


def test_pr_branch_match(tmp_path, monkeypatch, capsys):
    items = [{"number": 15, "title": "Fix the thing"}]
    prs = write_json(
        tmp_path / "prs.json",
        [pr(5, "OPEN", "issue-15", "fix: cache", "2026-09-11T00:00:00Z")],
    )
    _, lines = run(tmp_path, monkeypatch, capsys, items, prs)
    assert "pr=bacluc-agent/agent-vshn-runner#5:OPEN@2026-09-11T00:00:00Z" in lines[0]


def test_branch_issue_150_does_not_match_candidate_15(tmp_path, monkeypatch, capsys):
    items = [{"number": 15, "title": "Fix the thing"}]
    prs = write_json(
        tmp_path / "prs.json",
        [pr(5, "OPEN", "issue-150", "fix: cache", "2026-09-11T00:00:00Z")],
    )
    _, lines = run(tmp_path, monkeypatch, capsys, items, prs)
    assert "pr=none" in lines[0]


def test_branch_with_suffix_matches_candidate(tmp_path, monkeypatch, capsys):
    items = [{"number": 15, "title": "Fix the thing"}]
    prs = write_json(
        tmp_path / "prs.json",
        [pr(5, "OPEN", "issue-15-fix", "fix: cache", "2026-09-11T00:00:00Z")],
    )
    _, lines = run(tmp_path, monkeypatch, capsys, items, prs)
    assert "pr=bacluc-agent/agent-vshn-runner#5:OPEN@2026-09-11T00:00:00Z" in lines[0]


def test_tracker_qualified_title_match(tmp_path, monkeypatch, capsys):
    items = [{"number": 15, "title": "Fix the thing"}]
    prs = write_json(
        tmp_path / "prs.json",
        [
            pr(
                5,
                "OPEN",
                "fix/cache",
                "fix: cache (bacluc-agent/agent-vshn-todo#15)",
                "2026-09-11T00:00:00Z",
            )
        ],
    )
    _, lines = run(tmp_path, monkeypatch, capsys, items, prs)
    assert "pr=bacluc-agent/agent-vshn-runner#5:OPEN@2026-09-11T00:00:00Z" in lines[0]


def test_tracker_qualified_body_match(tmp_path, monkeypatch, capsys):
    items = [{"number": 70, "title": "Speed up selection"}]
    prs = write_json(
        tmp_path / "prs.json",
        [
            pr(
                40,
                "OPEN",
                "fix/faster-issue-selection",
                "feat(selection): pre-annotate issue candidates",
                "2026-09-11T00:00:00Z",
                body="Tracking issue: [bacluc-agent/agent-vshn-todo#70](https://example.invalid)",
            )
        ],
    )
    _, lines = run(tmp_path, monkeypatch, capsys, items, prs)
    assert "pr=bacluc-agent/agent-vshn-runner#40:OPEN@2026-09-11T00:00:00Z" in lines[0]


def test_bare_hash_body_ignored(tmp_path, monkeypatch, capsys):
    items = [{"number": 15, "title": "Fix the thing"}]
    prs = write_json(
        tmp_path / "prs.json",
        [
            pr(
                5,
                "OPEN",
                "fix/foo",
                "fix: unrelated",
                "2026-09-11T00:00:00Z",
                body="Closes #15 and also #16.",
            )
        ],
    )
    _, lines = run(tmp_path, monkeypatch, capsys, items, prs)
    assert "pr=none" in lines[0]


def test_issue_hash_title_match(tmp_path, monkeypatch, capsys):
    items = [{"number": 25, "title": "Pin opencode"}]
    prs = write_json(
        tmp_path / "prs.json",
        [
            pr(
                18,
                "OPEN",
                "chore/pin-opencode",
                "chore(setup-opencode): pin opencode-ai@1.18.30 (issue #25)",
                "2026-09-11T00:00:00Z",
            )
        ],
    )
    _, lines = run(tmp_path, monkeypatch, capsys, items, prs)
    assert "pr=bacluc-agent/agent-vshn-runner#18:OPEN@2026-09-11T00:00:00Z" in lines[0]


def test_bare_hash_title_ignored(tmp_path, monkeypatch, capsys):
    items = [{"number": 15, "title": "Fix the thing"}]
    prs = write_json(
        tmp_path / "prs.json",
        [pr(5, "OPEN", "fix/foo", "fix: unrelated (#15)", "2026-09-11T00:00:00Z")],
    )
    _, lines = run(tmp_path, monkeypatch, capsys, items, prs)
    assert "pr=none" in lines[0]


def test_cross_repo_title_ignored(tmp_path, monkeypatch, capsys):
    items = [{"number": 15, "title": "Fix the thing"}]
    prs = write_json(
        tmp_path / "prs.json",
        [
            pr(
                5,
                "OPEN",
                "fix/foo",
                "fix: cache (acme/other-repo#15)",
                "2026-09-11T00:00:00Z",
            )
        ],
    )
    _, lines = run(tmp_path, monkeypatch, capsys, items, prs)
    assert "pr=none" in lines[0]


def test_newest_pr_wins(tmp_path, monkeypatch, capsys):
    items = [{"number": 22, "title": "Port model_choice"}]
    prs = write_json(
        tmp_path / "prs.json",
        [
            pr(10, "CLOSED", "issue-22", "fix: cache", "2026-09-11T07:42:48Z"),
            pr(15, "OPEN", "issue-22", "fix: cache", "2026-09-11T23:08:57Z"),
        ],
    )
    _, lines = run(tmp_path, monkeypatch, capsys, items, prs)
    assert "pr=bacluc-agent/agent-vshn-runner#15:OPEN@2026-09-11T23:08:57Z" in lines[0]


def test_pr_none_when_no_match(tmp_path, monkeypatch, capsys):
    items = [{"number": 1, "title": "Unrelated"}]
    prs = write_json(
        tmp_path / "prs.json",
        [pr(5, "OPEN", "issue-15", "fix: cache", "2026-09-11T00:00:00Z")],
    )
    _, lines = run(tmp_path, monkeypatch, capsys, items, prs)
    assert "pr=none" in lines[0]


def test_multiple_pr_files_keyed_by_repo_and_number(tmp_path, monkeypatch, capsys):
    items = [
        {"number": 15, "title": "Fix the thing"},
        {"number": 26, "title": "Other thing"},
    ]
    runner_prs = write_json(
        tmp_path / "runner-prs.json",
        [pr(5, "OPEN", "issue-15", "fix: cache", "2026-09-11T00:00:00Z")],
    )
    todo_prs = write_json(
        tmp_path / "todo-prs.json",
        [
            pr(
                5,
                "OPEN",
                "issue-26",
                "fix: other",
                "2026-09-11T00:00:00Z",
                repo="bacluc-agent/agent-vshn-todo",
            )
        ],
    )
    _, lines = run(tmp_path, monkeypatch, capsys, items, runner_prs, todo_prs)
    assert lines[0].startswith("15: Fix the thing")
    assert "pr=bacluc-agent/agent-vshn-runner#5:OPEN@2026-09-11T00:00:00Z" in lines[0]
    assert lines[1].startswith("26: Other thing")
    assert "pr=bacluc-agent/agent-vshn-todo#5:OPEN@2026-09-11T00:00:00Z" in lines[1]


def test_last_human_max_non_bot(tmp_path, monkeypatch, capsys):
    items = [{"number": 15, "title": "Fix the thing"}]
    comments = write_json(
        tmp_path / "comments.json",
        {
            "data": {
                "repository": {
                    "i15": {
                        "comments": {
                            "nodes": [
                                {
                                    "createdAt": "2026-09-11T00:00:00Z",
                                    "author": {"login": "bacluc-agent"},
                                },
                                {
                                    "createdAt": "2026-09-12T00:00:00Z",
                                    "author": {"login": "BacLuc"},
                                },
                                {
                                    "createdAt": "2026-09-13T00:00:00Z",
                                    "author": {"login": "bacluc-agent"},
                                },
                            ]
                        }
                    }
                }
            }
        },
    )
    _, lines = run(tmp_path, monkeypatch, capsys, items, comments_path=comments)
    assert "last-human=2026-09-12T00:00:00Z" in lines[0]


def test_last_human_ignores_other_bots(tmp_path, monkeypatch, capsys):
    items = [{"number": 15, "title": "Fix the thing"}]
    comments = write_json(
        tmp_path / "comments.json",
        {
            "data": {
                "repository": {
                    "i15": {
                        "comments": {
                            "nodes": [
                                {
                                    "createdAt": "2026-09-13T00:00:00Z",
                                    "author": {"login": "renovate[bot]"},
                                },
                                {
                                    "createdAt": "2026-09-12T00:00:00Z",
                                    "author": {"login": "BacLuc"},
                                },
                            ]
                        }
                    }
                }
            }
        },
    )
    _, lines = run(tmp_path, monkeypatch, capsys, items, comments_path=comments)
    assert "last-human=2026-09-12T00:00:00Z" in lines[0]


def test_last_human_none_when_all_bot(tmp_path, monkeypatch, capsys):
    items = [{"number": 15, "title": "Fix the thing"}]
    comments = write_json(
        tmp_path / "comments.json",
        {
            "data": {
                "repository": {
                    "i15": {
                        "comments": {
                            "nodes": [
                                {
                                    "createdAt": "2026-09-11T00:00:00Z",
                                    "author": {"login": "bacluc-agent"},
                                }
                            ]
                        }
                    }
                }
            }
        },
    )
    _, lines = run(tmp_path, monkeypatch, capsys, items, comments_path=comments)
    assert "last-human=none" in lines[0]


def test_last_human_none_when_comments_file_missing(tmp_path, monkeypatch, capsys):
    items = [{"number": 15, "title": "Fix the thing"}]
    _, lines = run(
        tmp_path,
        monkeypatch,
        capsys,
        items,
        comments_path=tmp_path / "missing.json",
    )
    assert "last-human=none" in lines[0]


def test_malformed_comments_shape_degrades(tmp_path, monkeypatch, capsys):
    items = [{"number": 15, "title": "Fix the thing"}]
    shapes = [
        [1, 2],
        {"errors": [{"message": "boom"}]},
        {"data": {"repository": {"i15": {"comments": "boom"}}}},
        {"data": {"repository": {"i15": {"comments": {"nodes": ["boom"]}}}}},
    ]
    for shape in shapes:
        comments = write_json(tmp_path / "comments.json", shape)
        status, lines = run(
            tmp_path, monkeypatch, capsys, items, comments_path=comments
        )
        assert status == 0
        assert "last-human=none" in lines[0]


def test_body_excerpt_truncated_and_single_line(tmp_path, monkeypatch, capsys):
    items = [
        {
            "number": 15,
            "title": "Fix the thing",
            "body": 'line one\n\nline two "quoted" ' + "y" * 200,
        }
    ]
    _, lines = run(tmp_path, monkeypatch, capsys, items)
    excerpt = lines[0].split('body="', 1)[1].rstrip('"')
    assert "\n" not in excerpt
    assert len(excerpt) == enrich_candidates.BODY_EXCERPT_LEN
    assert '"' not in excerpt
    assert excerpt.startswith("line one line two 'quoted' y")


def test_bad_search_json_returns_1(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "enrich_candidates",
            "--search-json",
            str(tmp_path / "missing.json"),
            "--issue-repository",
            ISSUE_REPO,
        ],
    )
    assert enrich_candidates.main() == 1


def test_composition_pr_and_feedback(tmp_path, monkeypatch, capsys):
    items = [
        {
            "number": 4,
            "title": "meta: standing task",
            "labels": [{"name": "agent-refined"}],
            "created_at": "2026-09-07T07:16:00Z",
            "comments": 68,
            "body": "## Goal\n\nPort improvements.",
        }
    ]
    prs = write_json(
        tmp_path / "prs.json",
        [
            pr(
                34,
                "MERGED",
                "issue-4-drop-unused-workflow-permissions",
                "Port improvement from agent-runner",
                "2026-09-26T07:54:58Z",
            )
        ],
    )
    comments = write_json(
        tmp_path / "comments.json",
        {
            "data": {
                "repository": {
                    "i4": {
                        "comments": {
                            "nodes": [
                                {
                                    "createdAt": "2026-09-25T10:54:54Z",
                                    "author": {"login": "bacluc-agent"},
                                },
                                {
                                    "createdAt": "2026-09-26T08:00:00Z",
                                    "author": {"login": "BacLuc"},
                                },
                            ]
                        }
                    }
                }
            }
        },
    )
    _, lines = run(tmp_path, monkeypatch, capsys, items, prs, comments_path=comments)
    assert lines == [
        "4: meta: standing task | labels=agent-refined | created=2026-09-07 | comments=68 "
        "| pr=bacluc-agent/agent-vshn-runner#34:MERGED@2026-09-26T07:54:58Z "
        '| last-human=2026-09-26T08:00:00Z | body="## Goal Port improvements."'
    ]


def test_search_json_object_not_list_returns_1(tmp_path, monkeypatch, capsys):
    search = write_json(tmp_path / "search.json", {"items": []})
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "enrich_candidates",
            "--search-json",
            str(search),
            "--issue-repository",
            ISSUE_REPO,
        ],
    )
    assert enrich_candidates.main() == 1
