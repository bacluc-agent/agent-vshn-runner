import json
import types
from datetime import datetime, timezone
from pathlib import Path

import model_availability
import pytest


CONFIG = {
    "provider": {
        "vshn-us-ai": {"options": {"baseURL": "https://vshn.example.com/v1"}},
    }
}
PIPE_STDOUT_LIMIT = 65_536


def fake_debug_config(config, kwargs):
    output = json.dumps(config)
    if "stdout" in kwargs:
        kwargs["stdout"].write(output)
        kwargs["stdout"].flush()
        return types.SimpleNamespace(stdout="")
    return types.SimpleNamespace(
        stdout=output.encode("utf-8")[:PIPE_STDOUT_LIMIT].decode(
            "utf-8", errors="ignore"
        )
    )


def fake_run(args, *a, **kw):
    if args == ["opencode", "models"]:
        return types.SimpleNamespace(stdout="opencode/a-free\n")
    if args == ["opencode", "debug", "config"]:
        return fake_debug_config(CONFIG, kw)
    raise AssertionError(f"unexpected args: {args}")


class TestDiscoverModels:
    def test_discovers_models_per_provider(self, monkeypatch):
        captured = {}
        monkeypatch.setenv("VSHN_US_AI_API_KEY", "test-key")

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"data": [{"id": "glm-5.2"}]}'

        def fake_urlopen(request, timeout=30):
            captured["headers"] = request.headers
            captured["full_url"] = request.full_url
            return FakeResponse()

        monkeypatch.setattr(model_availability.urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setattr(model_availability.subprocess, "run", fake_run)
        free_models, provider_models = model_availability.discover_models()
        assert free_models == ["opencode/a-free"]
        assert provider_models == {
            "vshn-us-ai": ["glm-5.2"],
        }
        assert captured["headers"]["User-agent"] == "curl/8.5.0"
        assert captured["headers"].get("Authorization") == "Bearer test-key"
        assert not any("Python-urllib" in v for v in captured["headers"].values())
        assert any(k.lower() == "x-opencode-session" for k in captured["headers"])
        assert captured["full_url"].endswith("/models")

    def test_endpoint_failure_per_provider(self, monkeypatch):
        def fail(request, timeout=30):
            raise RuntimeError("403 Forbidden")

        monkeypatch.setattr(model_availability.urllib.request, "urlopen", fail)
        monkeypatch.setattr(model_availability.subprocess, "run", fake_run)
        free_models, provider_models = model_availability.discover_models()
        assert free_models == ["opencode/a-free"]
        assert provider_models == {
            "vshn-us-ai": [],
        }

    def test_missing_baseurl_per_provider(self, monkeypatch):
        config = {
            "provider": {
                "vshn-us-ai": {"options": {}},
            }
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"data": [{"id": "glm-5.2"}]}'

        def fake_run_missing(args, *a, **kw):
            if args == ["opencode", "models"]:
                return types.SimpleNamespace(stdout="opencode/a-free\n")
            if args == ["opencode", "debug", "config"]:
                return fake_debug_config(config, kw)
            raise AssertionError(f"unexpected args: {args}")

        monkeypatch.setattr(
            model_availability.urllib.request, "urlopen", lambda *a, **kw: FakeResponse()
        )
        monkeypatch.setattr(model_availability.subprocess, "run", fake_run_missing)
        free_models, provider_models = model_availability.discover_models()
        assert free_models == ["opencode/a-free"]
        assert provider_models == {}

    def test_config_read_failure(self, monkeypatch):
        def fail_config(args, *a, **kw):
            if args == ["opencode", "models"]:
                return types.SimpleNamespace(stdout="opencode/a-free\n")
            raise RuntimeError("opencode failed")

        monkeypatch.setattr(model_availability.subprocess, "run", fail_config)
        free_models, provider_models = model_availability.discover_models()
        assert free_models == ["opencode/a-free"]
        assert provider_models == {}


class TestParseFreeModels:
    def test_extracts_free_models(self):
        output = (
            "opencode/big-pickle\n"
            "opencode/ling-3.0-flash-fin-free\n"
            "opencode/mimo-v2.5-free\n"
            "custom-provider/other-free\n"
            "custom-provider/big-pickle\n"
            "standalone-free\n"
            "big-pickle\n"
            "opencode/paid-model\n"
            "other/paid-model\n"
        )
        assert model_availability.parse_free_models(output) == [
            "big-pickle",
            "custom-provider/big-pickle",
            "custom-provider/other-free",
            "opencode/big-pickle",
            "opencode/ling-3.0-flash-fin-free",
            "opencode/mimo-v2.5-free",
            "standalone-free",
        ]

    def test_deduplicates(self):
        assert model_availability.parse_free_models("opencode/a-free\nopencode/a-free\n") == [
            "opencode/a-free"
        ]


class TestParseGoModelIds:
    def test_extracts_and_deduplicates_ids(self):
        data = json.dumps(
            {"data": [{"id": "glm-5.2"}, {"id": "qwen3.8-flash"}, {"id": "glm-5.2"}]}
        )
        assert model_availability.parse_go_model_ids(data) == ["glm-5.2", "qwen3.8-flash"]

    def test_invalid_json_returns_empty(self):
        assert model_availability.parse_go_model_ids("not json") == []


class TestBuildCandidates:
    def test_skips_providers_without_api_key(self):
        env = {}
        assert model_availability.build_candidates(
            ["opencode/a-free"],
            {"vshn-us-ai": ["glm-5.2"]},
            env,
        ) == [
            "opencode/a-free",
        ]

    def test_free_models_last(self):
        env = {"VSHN_US_AI_API_KEY": "key1"}
        candidates = model_availability.build_candidates(
            ["opencode/a-free"],
            {"vshn-us-ai": ["glm-5.2"]},
            env,
        )
        assert candidates == ["vshn-us-ai/glm-5.2", "opencode/a-free"]


class TestIsCacheFresh:
    def test_fresh_available(self):
        now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
        entry = {"ok": True, "checked": "2026-09-06T10:00:00Z"}
        assert model_availability.is_cache_fresh(entry, now)

    def test_expired_available(self):
        now = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
        entry = {"ok": True, "checked": "2026-09-06T10:00:00Z"}
        assert not model_availability.is_cache_fresh(entry, now)

    def test_fresh_failed(self):
        now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
        entry = {"ok": False, "checked": "2026-09-06T11:00:00Z"}
        assert model_availability.is_cache_fresh(entry, now)

    def test_expired_failed(self):
        now = datetime(2026, 9, 6, 15, 0, tzinfo=timezone.utc)
        entry = {"ok": False, "checked": "2026-09-06T11:00:00Z"}
        assert not model_availability.is_cache_fresh(entry, now)

    def test_missing_or_malformed_entry(self):
        now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
        assert not model_availability.is_cache_fresh(None, now)
        assert not model_availability.is_cache_fresh({"ok": "yes"}, now)
        assert not model_availability.is_cache_fresh({"ok": True}, now)

    def test_timeout_fresh_within_one_hour(self):
        now = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
        entry = {"ok": False, "reason": "timeout", "checked": "2026-09-06T11:30:00Z"}
        assert model_availability.is_cache_fresh(entry, now)

    def test_timeout_stale_after_one_hour(self):
        now = datetime(2026, 9, 6, 13, 30, tzinfo=timezone.utc)
        timeout = {"ok": False, "reason": "timeout", "checked": "2026-09-06T12:00:00Z"}
        failed = {"ok": False, "checked": "2026-09-06T12:00:00Z"}
        assert not model_availability.is_cache_fresh(timeout, now)
        assert model_availability.is_cache_fresh(failed, now)


class TestMergeResults:
    def test_merges_and_overwrites(self):
        cache = {"opencode/a-free": {"ok": True, "checked": "old"}}
        results = {"opencode/a-free": False, "vshn-us-ai/glm-5.2": True}
        assert model_availability.merge_results(cache, results, "2026-09-06T12:00:00Z") == {
            "opencode/a-free": {"ok": False, "checked": "2026-09-06T12:00:00Z"},
            "vshn-us-ai/glm-5.2": {"ok": True, "checked": "2026-09-06T12:00:00Z"},
        }

    def test_timeout_result_records_reason(self):
        cache = {"opencode/a-free": {"ok": True, "checked": "old"}}
        merged = model_availability.merge_results(
            cache, {"opencode/a-free": None}, "2026-09-06T12:00:00Z"
        )
        assert merged["opencode/a-free"] == {
            "ok": False,
            "reason": "timeout",
            "checked": "2026-09-06T12:00:00Z",
        }


class TestAvailableModels:
    def test_free_first_then_paid(self):
        cache = {
            "vshn-us-ai/glm-5.2": {"ok": True, "checked": "x"},
            "opencode/a-free": {"ok": True, "checked": "x"},
            "opencode/b-free": {"ok": False, "checked": "x"},
        }
        assert model_availability.available_models(
            cache,
            ["opencode/a-free", "opencode/b-free"],
            {"vshn-us-ai": ["glm-5.2"]},
        ) == [
            "opencode/a-free",
            "vshn-us-ai/glm-5.2",
        ]


class TestResolveCacheIssue:
    def test_env_var_wins(self, monkeypatch):
        monkeypatch.setenv("MODEL_AVAILABILITY_CACHE_ISSUE", "7")
        monkeypatch.delenv("ISSUE_REPOSITORY", raising=False)
        assert model_availability.resolve_cache_issue() == "7"

    def test_auto_detect_by_title(self, monkeypatch):
        monkeypatch.delenv("MODEL_AVAILABILITY_CACHE_ISSUE", raising=False)
        monkeypatch.setenv("ISSUE_REPOSITORY", "bacluc-agent/agent-vshn-todo")
        monkeypatch.setattr(
            model_availability,
            "run_gh",
            lambda *args: "3",
        )
        assert model_availability.resolve_cache_issue() == "3"

    def test_no_repo_returns_none(self, monkeypatch):
        monkeypatch.delenv("MODEL_AVAILABILITY_CACHE_ISSUE", raising=False)
        monkeypatch.delenv("ISSUE_REPOSITORY", raising=False)
        assert model_availability.resolve_cache_issue() is None

    def test_search_failure_returns_none(self, monkeypatch):
        monkeypatch.delenv("MODEL_AVAILABILITY_CACHE_ISSUE", raising=False)
        monkeypatch.setenv("ISSUE_REPOSITORY", "bacluc-agent/agent-vshn-todo")

        def fail(*args):
            raise RuntimeError("gh failed")

        monkeypatch.setattr(model_availability, "run_gh", fail)
        assert model_availability.resolve_cache_issue() is None


class TestReadCache:
    def test_reads_issue_body(self, monkeypatch):
        monkeypatch.setenv("ISSUE_REPOSITORY", "bacluc-agent/agent-vshn-todo")
        monkeypatch.setattr(
            model_availability,
            "run_gh",
            lambda *args: '{"opencode/a-free": {"ok": true, "checked": "x"}}',
        )
        assert model_availability.read_cache("3") == {
            "opencode/a-free": {"ok": True, "checked": "x"}
        }

    def test_returns_empty_on_failure(self, monkeypatch):
        monkeypatch.setenv("ISSUE_REPOSITORY", "bacluc-agent/agent-vshn-todo")

        def fail(*args):
            raise RuntimeError("gh failed")

        monkeypatch.setattr(model_availability, "run_gh", fail)
        assert model_availability.read_cache("3") == {}


class TestWriteCache:
    def test_writes_issue_body(self, monkeypatch):
        monkeypatch.setenv("ISSUE_REPOSITORY", "bacluc-agent/agent-vshn-todo")
        calls = []

        def fake_run_gh(*args):
            calls.append(args)

        monkeypatch.setattr(model_availability, "run_gh", fake_run_gh)
        model_availability.write_cache("3", {"a": 1})
        assert calls == [
            ("issue", "edit", "3", "-R", "bacluc-agent/agent-vshn-todo", "--body", '{"a": 1}')
        ]

    def test_warns_on_failure(self, monkeypatch, capsys):
        monkeypatch.setenv("ISSUE_REPOSITORY", "bacluc-agent/agent-vshn-todo")

        def fail(*args):
            raise RuntimeError("gh failed")

        monkeypatch.setattr(model_availability, "run_gh", fail)
        model_availability.write_cache("3", {"a": 1})
        assert "failed to write cache issue 3" in capsys.readouterr().err

    def test_skips_oversized_body(self, monkeypatch, capsys):
        monkeypatch.setenv("ISSUE_REPOSITORY", "bacluc-agent/agent-vshn-todo")
        # record only the body size, so a failure here does not dump 70 KB
        sizes = []
        monkeypatch.setattr(
            model_availability, "run_gh", lambda *args: sizes.append(len(args[-1]))
        )
        model_availability.write_cache("3", {"k": "x" * 70_000})
        assert sizes == []
        assert "exceeding" in capsys.readouterr().err


class TestUpdateCache:
    def test_writes_when_body_unchanged(self, monkeypatch):
        monkeypatch.setattr(
            model_availability,
            "read_cache_raw",
            lambda issue: '{"a": {"ok": true, "checked": "old"}}',
        )
        written = []
        monkeypatch.setattr(
            model_availability, "write_cache", lambda issue, cache: written.append(cache)
        )
        merged = model_availability.update_cache(
            "3", lambda c: {**c, "b": {"ok": True, "checked": "new"}}
        )
        assert merged == {
            "a": {"ok": True, "checked": "old"},
            "b": {"ok": True, "checked": "new"},
        }
        assert written == [merged]

    def test_retries_on_concurrent_change(self, monkeypatch):
        bodies = iter(
            [
                '{"a": {"ok": true, "checked": "old"}}',
                '{"a": {"ok": true, "checked": "old"}, "concurrent": {"ok": true, "checked": "c"}}',
                '{"a": {"ok": true, "checked": "old"}, "concurrent": {"ok": true, "checked": "c"}}',
                '{"a": {"ok": true, "checked": "old"}, "concurrent": {"ok": true, "checked": "c"}}',
            ]
        )
        monkeypatch.setattr(model_availability, "read_cache_raw", lambda issue: next(bodies))
        written = []
        monkeypatch.setattr(
            model_availability, "write_cache", lambda issue, cache: written.append(cache)
        )
        merged = model_availability.update_cache(
            "3", lambda c: {**c, "b": {"ok": True, "checked": "new"}}
        )
        assert merged["concurrent"] == {"ok": True, "checked": "c"}
        assert written == [merged]

    def test_gives_up_after_max_attempts(self, monkeypatch, capsys):
        reads = {"count": 0}

        def changing_read(issue):
            reads["count"] += 1
            return f'{{"v": {reads["count"]}}}'

        monkeypatch.setattr(model_availability, "read_cache_raw", changing_read)
        written = []
        monkeypatch.setattr(
            model_availability, "write_cache", lambda issue, cache: written.append(cache)
        )
        assert model_availability.update_cache("3", lambda c: c) is None
        assert written == []
        assert reads["count"] == model_availability.CAS_MAX_ATTEMPTS * 2
        assert "cache issue 3 changed concurrently" in capsys.readouterr().err

    def test_read_failure_skips_write(self, monkeypatch, capsys):
        monkeypatch.setattr(model_availability, "read_cache_raw", lambda issue: None)
        written = []
        monkeypatch.setattr(
            model_availability, "write_cache", lambda issue, cache: written.append(cache)
        )
        assert model_availability.update_cache("3", lambda c: c) is None
        assert written == []
        assert "could not read cache issue 3" in capsys.readouterr().err


class TestMarkFailed:
    def test_marks_single_model(self, monkeypatch):
        captured = {}

        def fake_update(issue, mutate):
            merged = mutate(
                {
                    "a/x": {"ok": True, "checked": "old"},
                    "b/y": {"ok": True, "checked": "old"},
                }
            )
            captured.update(merged)
            return merged

        monkeypatch.setattr(model_availability, "update_cache", fake_update)
        model_availability.mark_failed("3", model="opencode/a-free")
        entry = captured["opencode/a-free"]
        assert entry["ok"] is False
        assert "reason" not in entry
        datetime.fromisoformat(entry["checked"].replace("Z", "+00:00"))
        assert captured["a/x"] == {"ok": True, "checked": "old"}

    def test_marks_provider_wide(self, monkeypatch):
        captured = {}

        def fake_update(issue, mutate):
            merged = mutate(
                {
                    "prov-1/a": {"ok": True, "checked": "old"},
                    "prov-1/b": {"ok": True, "checked": "old"},
                    "prov-10/c": {"ok": True, "checked": "old"},
                    "prov-2/d": {"ok": True, "checked": "old"},
                    "free-model": {"ok": True, "checked": "old"},
                }
            )
            captured.update(merged)
            return merged

        monkeypatch.setattr(model_availability, "update_cache", fake_update)
        model_availability.mark_failed("3", provider="prov-1")
        assert captured["prov-1/a"]["ok"] is False
        assert captured["prov-1/b"]["ok"] is False
        assert captured["prov-10/c"] == {"ok": True, "checked": "old"}
        assert captured["prov-2/d"] == {"ok": True, "checked": "old"}
        assert captured["free-model"] == {"ok": True, "checked": "old"}


class TestCli:
    def test_mark_failed_model_uses_env_resolved_issue(self, monkeypatch):
        monkeypatch.setenv("MODEL_AVAILABILITY_CACHE_ISSUE", "7")
        calls = []
        monkeypatch.setattr(
            model_availability,
            "mark_failed",
            lambda issue, model=None, provider=None: calls.append((issue, model, provider)),
        )
        assert model_availability.cli(["--mark-failed", "--model", "opencode/a-free"]) == 0
        assert calls == [("7", "opencode/a-free", None)]

    def test_mark_failed_without_target_warns(self, monkeypatch, capsys):
        monkeypatch.setenv("MODEL_AVAILABILITY_CACHE_ISSUE", "7")
        monkeypatch.setattr(
            model_availability,
            "mark_failed",
            lambda *a, **kw: pytest.fail("mark_failed should not be called"),
        )
        assert model_availability.cli(["--mark-failed"]) == 0
        assert "--mark-failed requires" in capsys.readouterr().err

    def test_no_cache_issue_resolved_warns_and_skips(self, monkeypatch, capsys):
        monkeypatch.delenv("MODEL_AVAILABILITY_CACHE_ISSUE", raising=False)
        monkeypatch.delenv("ISSUE_REPOSITORY", raising=False)
        monkeypatch.setattr(
            model_availability,
            "mark_failed",
            lambda *a, **kw: pytest.fail("mark_failed should not be called"),
        )
        assert model_availability.cli(["--mark-failed", "--model", "m"]) == 0
        assert "no cache issue resolved" in capsys.readouterr().err

    def test_no_args_runs_main(self, monkeypatch):
        monkeypatch.setattr(model_availability, "main", lambda: 0)
        assert model_availability.cli([]) == 0


class TestModelsEndpointFor:
    def test_openai_style(self):
        assert (
            model_availability.models_endpoint_for("https://opencode.ai/zen/go/v1")
            == "https://opencode.ai/zen/go/v1/models"
        )

    def test_anthropic_style(self):
        assert (
            model_availability.models_endpoint_for("https://opencode.ai/zen/go/v1/messages")
            == "https://opencode.ai/zen/go/v1/models"
        )

    def test_trailing_slash(self):
        assert (
            model_availability.models_endpoint_for("https://opencode.ai/zen/go/v1/")
            == "https://opencode.ai/zen/go/v1/models"
        )
        assert (
            model_availability.models_endpoint_for("https://opencode.ai/zen/go/v1/messages/")
            == "https://opencode.ai/zen/go/v1/models"
        )


class TestLoadProviderBaseUrls:
    def test_returns_base_urls(self, monkeypatch):
        config = {
            "provider": {
                "vshn-us-ai": {"options": {"baseURL": "https://vshn.example.com/v1"}},
                "no-base-url": {"options": {}},
            }
        }
        temp_files = []

        def fake_run(*args, **kwargs):
            if "stdout" in kwargs:
                temp_files.append(kwargs["stdout"])
            return fake_debug_config(config, kwargs)

        monkeypatch.setattr(model_availability.subprocess, "run", fake_run)
        assert model_availability.load_provider_base_urls() == {
            "vshn-us-ai": "https://vshn.example.com/v1",
        }
        assert temp_files[0].closed
        assert not Path(temp_files[0].name).exists()

    def test_reads_output_larger_than_pipe_limit(self, monkeypatch):
        config = {
            "provider": {
                "vshn-us-ai": {"options": {"baseURL": "https://vshn.example.com/v1"}},
            },
            "padding": "x" * PIPE_STDOUT_LIMIT,
        }
        payload = json.dumps(config)
        assert len(payload.encode("utf-8")) > PIPE_STDOUT_LIMIT
        with pytest.raises(json.JSONDecodeError):
            json.loads(payload.encode("utf-8")[:PIPE_STDOUT_LIMIT].decode("utf-8"))

        def fake_run(args, **kwargs):
            assert args == ["opencode", "debug", "config"]
            return fake_debug_config(config, kwargs)

        monkeypatch.setattr(model_availability.subprocess, "run", fake_run)
        assert model_availability.load_provider_base_urls() == {
            "vshn-us-ai": "https://vshn.example.com/v1",
        }

    def test_returns_empty_on_failure(self, monkeypatch):
        temp_files = []

        def fail(args, **kwargs):
            if args == ["opencode", "debug", "config"] and "stdout" in kwargs:
                temp_files.append(kwargs["stdout"])
            raise RuntimeError("opencode failed")

        monkeypatch.setattr(model_availability.subprocess, "run", fail)
        assert model_availability.load_provider_base_urls() == {}
        assert temp_files[0].closed
        assert not Path(temp_files[0].name).exists()


class TestProbeModelLogging:
    def test_writes_probe_log_with_stdout_and_stderr(self, tmp_path, monkeypatch):
        class FakeResult:
            returncode = 0
            stdout = "OK\n"
            stderr = "debug: loaded model\n"

        monkeypatch.setattr(
            model_availability.subprocess, "run", lambda *args, **kwargs: FakeResult()
        )
        assert (
            model_availability.probe_model("opencode-go-openai/glm-5.2", str(tmp_path))
            is True
        )
        log = tmp_path / "model-probes" / "probe-opencode-go-openai-glm-5.2.log"
        assert log.read_text() == "OK\ndebug: loaded model\n"

    def test_writes_probe_log_even_when_probe_fails(self, tmp_path, monkeypatch):
        class FakeResult:
            returncode = 1
            stdout = "model unavailable\n"
            stderr = ""

        monkeypatch.setattr(
            model_availability.subprocess, "run", lambda *args, **kwargs: FakeResult()
        )
        assert model_availability.probe_model("opencode/a-free", str(tmp_path)) is False
        log = tmp_path / "model-probes" / "probe-opencode-a-free.log"
        assert log.read_text() == "model unavailable\n"

    def test_writes_probe_log_on_timeout(self, tmp_path, monkeypatch):
        def raise_timeout(*args, **kwargs):
            raise model_availability.subprocess.TimeoutExpired(
                cmd="opencode", timeout=7
            )

        monkeypatch.setattr(model_availability.subprocess, "run", raise_timeout)
        assert (
            model_availability.probe_model("opencode/a-free", str(tmp_path), timeout=7)
            is None
        )
        log = tmp_path / "model-probes" / "probe-opencode-a-free.log"
        assert log.read_text() == "TIMEOUT after 7s\n"


class TestDiscoverModelsLogging:
    def test_writes_opencode_models_log(self, tmp_path, monkeypatch):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"data": []}'

        def fake_run_logging(args, *a, **kw):
            if args == ["opencode", "models"]:
                return types.SimpleNamespace(
                    stdout="opencode/a-free\nopencode/big-pickle\n", stderr=""
                )
            if args == ["opencode", "debug", "config"]:
                return fake_debug_config(CONFIG, kw)
            raise AssertionError(f"unexpected args: {args}")

        monkeypatch.setattr(model_availability.subprocess, "run", fake_run_logging)
        monkeypatch.setattr(
            model_availability.urllib.request,
            "urlopen",
            lambda *args, **kwargs: FakeResponse(),
        )
        monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
        free_models, provider_models = model_availability.discover_models()
        assert free_models == ["opencode/a-free", "opencode/big-pickle"]
        assert provider_models == {"vshn-us-ai": []}
        log = tmp_path / "model-probes" / "opencode-models.log"
        assert log.read_text() == "opencode/a-free\nopencode/big-pickle\n"


class TestMainReReadsCache:
    def test_reread_preserves_concurrent_updates(self, monkeypatch):
        monkeypatch.setattr(model_availability, "resolve_cache_issue", lambda: "3")
        monkeypatch.setattr(model_availability, "read_cache", lambda issue: {})
        monkeypatch.setattr(model_availability, "discover_models", lambda: ([], {}))
        monkeypatch.setattr(model_availability, "probe_candidates", lambda c, w: {})
        concurrent = {"model-a": {"ok": True, "checked": "2026-09-12T00:00:00Z"}}

        def fake_update_cache(issue, mutate):
            return mutate(dict(concurrent))

        monkeypatch.setattr(model_availability, "update_cache", fake_update_cache)
        captured = {}
        monkeypatch.setattr(
            model_availability,
            "write_outputs",
            lambda cache, available, issue: captured.update(cache),
        )
        assert model_availability.main() == 0
        assert "model-a" in captured