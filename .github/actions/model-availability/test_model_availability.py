import json
import types
from datetime import datetime, timezone

import model_availability


CONFIG = {
    "provider": {
        "vshn-us-ai": {"options": {"baseURL": "https://vshn.example.com/v1"}},
    }
}


def fake_run(args, *a, **kw):
    if args == ["opencode", "models"]:
        return types.SimpleNamespace(stdout="opencode/a-free\n")
    if args == ["opencode", "debug", "config"]:
        return types.SimpleNamespace(stdout=json.dumps(CONFIG))
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
                return types.SimpleNamespace(stdout=json.dumps(config))
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


class TestMergeResults:
    def test_merges_and_overwrites(self):
        cache = {"opencode/a-free": {"ok": True, "checked": "old"}}
        results = {"opencode/a-free": False, "vshn-us-ai/glm-5.2": True}
        assert model_availability.merge_results(cache, results, "2026-09-06T12:00:00Z") == {
            "opencode/a-free": {"ok": False, "checked": "2026-09-06T12:00:00Z"},
            "vshn-us-ai/glm-5.2": {"ok": True, "checked": "2026-09-06T12:00:00Z"},
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

    def test_swallows_failure(self, monkeypatch):
        monkeypatch.setenv("ISSUE_REPOSITORY", "bacluc-agent/agent-vshn-todo")

        def fail(*args):
            raise RuntimeError("gh failed")

        monkeypatch.setattr(model_availability, "run_gh", fail)
        model_availability.write_cache("3", {"a": 1})


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
        monkeypatch.setattr(
            model_availability.subprocess,
            "run",
            lambda *args, **kwargs: types.SimpleNamespace(stdout=json.dumps(config)),
        )
        assert model_availability.load_provider_base_urls() == {
            "vshn-us-ai": "https://vshn.example.com/v1",
        }

    def test_returns_empty_on_failure(self, monkeypatch):
        def fail(*args, **kwargs):
            raise RuntimeError("opencode failed")

        monkeypatch.setattr(model_availability.subprocess, "run", fail)
        assert model_availability.load_provider_base_urls() == {}


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
                return types.SimpleNamespace(stdout=json.dumps(CONFIG))
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
        reads = iter(
            [
                {},
                {"model-a": {"ok": True, "checked": "2026-09-12T00:00:00Z"}},
            ]
        )
        monkeypatch.setattr(model_availability, "read_cache", lambda issue: next(reads))
        monkeypatch.setattr(model_availability, "discover_models", lambda: ([], {}))
        monkeypatch.setattr(model_availability, "probe_candidates", lambda c, w: {})
        written = {}
        monkeypatch.setattr(
            model_availability, "write_cache", lambda issue, cache: written.update(cache)
        )
        monkeypatch.setattr(model_availability, "write_outputs", lambda *a: None)
        assert model_availability.main() == 0
        assert "model-a" in written