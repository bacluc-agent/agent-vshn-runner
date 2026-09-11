import json
import sys

import candidate_pr_status


def run(candidates, *pr_files, monkeypatch, capsys):
    monkeypatch.setattr(
        sys, "argv", ["candidate_pr_status", str(candidates), *map(str, pr_files)]
    )
    assert candidate_pr_status.main() == 0
    return capsys.readouterr().out.splitlines()


def write_prs(path, prs):
    path.write_text(json.dumps(prs))
    return path


class TestMain:
    def test_found_by_branch_name(self, tmp_path, monkeypatch, capsys):
        candidates = tmp_path / "candidates.txt"
        candidates.write_text("15\n")
        prs = write_prs(
            tmp_path / "prs.json",
            [
                {
                    "number": 5,
                    "state": "OPEN",
                    "title": "fix: update cache on selection failure",
                    "headRefName": "issue-15",
                    "url": "https://github.com/bacluc-agent/agent-vshn-runner/pull/5",
                    "updatedAt": "2026-09-11T00:00:00Z",
                }
            ],
        )
        assert run(candidates, prs, monkeypatch=monkeypatch, capsys=capsys) == [
            "15\thttps://github.com/bacluc-agent/agent-vshn-runner/pull/5 (OPEN)"
        ]

    def test_found_via_title_number(self, tmp_path, monkeypatch, capsys):
        candidates = tmp_path / "candidates.txt"
        candidates.write_text("15\n")
        prs = write_prs(
            tmp_path / "prs.json",
            [
                {
                    "number": 5,
                    "state": "OPEN",
                    "title": "fix: update cache on selection failure (#15)",
                    "headRefName": "fix/cache",
                    "url": "https://github.com/bacluc-agent/agent-vshn-runner/pull/5",
                    "updatedAt": "2026-09-11T00:00:00Z",
                }
            ],
        )
        assert run(candidates, prs, monkeypatch=monkeypatch, capsys=capsys) == [
            "15\thttps://github.com/bacluc-agent/agent-vshn-runner/pull/5 (OPEN)"
        ]

    def test_title_number_not_in_candidates_ignored(self, tmp_path, monkeypatch, capsys):
        candidates = tmp_path / "candidates.txt"
        candidates.write_text("22\n")
        prs = write_prs(
            tmp_path / "prs.json",
            [
                {
                    "number": 5,
                    "state": "OPEN",
                    "title": "fix: unrelated (#15)",
                    "headRefName": "fix/foo",
                    "url": "https://github.com/bacluc-agent/agent-vshn-runner/pull/5",
                    "updatedAt": "2026-09-11T00:00:00Z",
                }
            ],
        )
        assert run(candidates, prs, monkeypatch=monkeypatch, capsys=capsys) == []

    def test_newest_pr_wins(self, tmp_path, monkeypatch, capsys):
        candidates = tmp_path / "candidates.txt"
        candidates.write_text("22\n")
        prs = write_prs(
            tmp_path / "prs.json",
            [
                {
                    "number": 10,
                    "state": "CLOSED",
                    "title": "fix: cache",
                    "headRefName": "issue-22",
                    "url": "https://github.com/bacluc-agent/agent-vshn-runner/pull/10",
                    "updatedAt": "2026-09-11T07:42:48Z",
                },
                {
                    "number": 15,
                    "state": "OPEN",
                    "title": "fix: cache",
                    "headRefName": "issue-22",
                    "url": "https://github.com/bacluc-agent/agent-vshn-runner/pull/15",
                    "updatedAt": "2026-09-11T23:08:57Z",
                },
            ],
        )
        assert run(candidates, prs, monkeypatch=monkeypatch, capsys=capsys) == [
            "22\thttps://github.com/bacluc-agent/agent-vshn-runner/pull/15 (OPEN)"
        ]

    def test_no_matches_empty_output(self, tmp_path, monkeypatch, capsys):
        candidates = tmp_path / "candidates.txt"
        candidates.write_text("1\n")
        prs = write_prs(
            tmp_path / "prs.json",
            [
                {
                    "number": 5,
                    "state": "OPEN",
                    "title": "fix: update cache on selection failure (#15)",
                    "headRefName": "fix/cache",
                    "url": "https://github.com/bacluc-agent/agent-vshn-runner/pull/5",
                    "updatedAt": "2026-09-11T00:00:00Z",
                }
            ],
        )
        assert run(candidates, prs, monkeypatch=monkeypatch, capsys=capsys) == []

    def test_branch_prefix_match(self, tmp_path, monkeypatch, capsys):
        candidates = tmp_path / "candidates.txt"
        candidates.write_text("11\n")
        prs = write_prs(
            tmp_path / "prs.json",
            [
                {
                    "number": 6,
                    "state": "MERGED",
                    "title": "Port model probe logging",
                    "headRefName": "issue-11-model-probe-logging",
                    "url": "https://github.com/bacluc-agent/agent-vshn-runner/pull/6",
                    "updatedAt": "2026-09-11T00:00:00Z",
                }
            ],
        )
        assert run(candidates, prs, monkeypatch=monkeypatch, capsys=capsys) == [
            "11\thttps://github.com/bacluc-agent/agent-vshn-runner/pull/6 (MERGED)"
        ]

    def test_no_cross_number_branch_match(self, tmp_path, monkeypatch, capsys):
        candidates = tmp_path / "candidates.txt"
        candidates.write_text("1\n")
        prs = write_prs(
            tmp_path / "prs.json",
            [
                {
                    "number": 5,
                    "state": "OPEN",
                    "title": "fix: cache",
                    "headRefName": "issue-10",
                    "url": "https://github.com/bacluc-agent/agent-vshn-runner/pull/5",
                    "updatedAt": "2026-09-11T00:00:00Z",
                }
            ],
        )
        assert run(candidates, prs, monkeypatch=monkeypatch, capsys=capsys) == []

    def test_title_issue_number_matches(self, tmp_path, monkeypatch, capsys):
        candidates = tmp_path / "candidates.txt"
        candidates.write_text("25\n")
        prs = write_prs(
            tmp_path / "prs.json",
            [
                {
                    "number": 18,
                    "state": "OPEN",
                    "title": "chore(setup-opencode): pin opencode-ai@1.18.30 (issue #25)",
                    "headRefName": "chore/pin-opencode",
                    "url": "https://github.com/bacluc-agent/agent-vshn-runner/pull/18",
                    "updatedAt": "2026-09-11T00:00:00Z",
                }
            ],
        )
        assert run(candidates, prs, monkeypatch=monkeypatch, capsys=capsys) == [
            "25\thttps://github.com/bacluc-agent/agent-vshn-runner/pull/18 (OPEN)"
        ]

    def test_title_number_does_not_annotate_other_candidate(self, tmp_path, monkeypatch, capsys):
        candidates = tmp_path / "candidates.txt"
        candidates.write_text("22\n")
        prs = write_prs(
            tmp_path / "prs.json",
            [
                {
                    "number": 5,
                    "state": "OPEN",
                    "title": "fix(scripts): add validate_refined_issue.py (#13)",
                    "headRefName": "issue-13-validator",
                    "url": "https://github.com/bacluc-agent/agent-vshn-runner/pull/5",
                    "updatedAt": "2026-09-11T00:00:00Z",
                }
            ],
        )
        assert run(candidates, prs, monkeypatch=monkeypatch, capsys=capsys) == []

    def test_later_input_wins_for_same_pr_number(self, tmp_path, monkeypatch, capsys):
        candidates = tmp_path / "candidates.txt"
        candidates.write_text("22\n")
        first = write_prs(
            tmp_path / "first.json",
            [
                {
                    "number": 15,
                    "state": "OPEN",
                    "title": "fix: cache",
                    "headRefName": "issue-22",
                    "url": "https://github.com/bacluc-agent/agent-vshn-runner/pull/15",
                    "updatedAt": "2026-09-11T00:00:00Z",
                }
            ],
        )
        second = write_prs(
            tmp_path / "second.json",
            [
                {
                    "number": 15,
                    "state": "MERGED",
                    "title": "fix: cache",
                    "headRefName": "issue-22",
                    "url": "https://github.com/bacluc-agent/agent-vshn-runner/pull/15",
                    "updatedAt": "2026-09-11T00:00:00Z",
                }
            ],
        )
        assert run(candidates, first, second, monkeypatch=monkeypatch, capsys=capsys) == [
            "22\thttps://github.com/bacluc-agent/agent-vshn-runner/pull/15 (MERGED)"
        ]