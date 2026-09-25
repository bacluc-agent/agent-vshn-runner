#!/usr/bin/env python3
"""Loop-termination metrics emitter — stdlib only, no new dependencies."""
import json
import os
import sys
from datetime import datetime, timezone


def compute_metrics(
    steps: int,
    progress_delta: float,
    failure_mode: str = "unknown",
    token_estimate: float | None = None,
) -> dict:
    # ponytail: token cost estimated from model-discovery output or plumbed from context;
    # upgrade when real token usage API available.
    token_cost_per_step = token_estimate if token_estimate is not None else max(0.001, steps * 0.0005)
    # convergence_rate = steps / progress_delta when progress_delta > 0, else steps (unbounded;
    # deviation from the issue's 0-1 `1 - step_count/max_steps` formula, documented in the PR description).
    convergence_rate = steps / progress_delta if progress_delta > 0 else steps
    return {
        "step_count": steps,
        "token_cost_per_step": token_cost_per_step,
        "convergence_rate": convergence_rate,
        "failure_mode": failure_mode,
        "terminated_at": datetime.now(timezone.utc).isoformat(),
    }


def load_artifact(path: str = "loop-metrics.json") -> dict | None:
    """Load the artifact written by the opencode tool (camelCase) as snake_case metrics."""
    try:
        with open(path) as f:
            raw = json.load(f)
        return {
            "step_count": raw["steps"],
            "token_cost_per_step": raw["tokenCostPerStep"],
            "convergence_rate": raw["convergenceRate"],
            "failure_mode": raw["failureMode"],
            "terminated_at": raw["terminatedAt"],
        }
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return None


def emit_metrics(
    metrics: dict,
    summary_path: str | None = None,
    artifact_path: str | None = None,
) -> dict:
    summary_file = summary_path or os.environ.get("GITHUB_STEP_SUMMARY", "/tmp/loop-summary.md")
    artifact_file = artifact_path or "loop-metrics.json"

    table = (
        "| Metric | Value |\n"
        "|---|---|\n"
        f"| Steps | {metrics['step_count']} |\n"
        f"| Token cost / step | {metrics['token_cost_per_step']:.4f} |\n"
        f"| Convergence rate | {metrics['convergence_rate']:.4f} |\n"
        f"| Failure mode | {metrics['failure_mode']} |\n"
        f"| Terminated at | {metrics['terminated_at']} |\n"
    )

    with open(summary_file, "a") as f:
        f.write("\n" + table + "\n")

    with open(artifact_file, "w") as f:
        f.write(json.dumps(metrics, indent=2) + "\n")

    return {"summary": table, "artifact": artifact_file}


def main() -> int:
    # Prefer the artifact written by the opencode tool during the run; fall back to env defaults.
    metrics = load_artifact()
    if metrics is None:
        steps = int(os.environ.get("LOOP_STEPS", "0"))
        progress_delta = float(os.environ.get("LOOP_PROGRESS_DELTA", "1"))
        failure_mode = os.environ.get("LOOP_FAILURE_MODE", "unknown")
        token_estimate = os.environ.get("LOOP_TOKEN_ESTIMATE")
        token_estimate_f = float(token_estimate) if token_estimate else None

        metrics = compute_metrics(steps, progress_delta, failure_mode, token_estimate_f)

    result = emit_metrics(metrics)
    print(f"Metrics emitted: {json.dumps(metrics)}")
    print(f"Summary: {result['summary']}")
    print(f"Artifact: {result['artifact']}")
    # Write step output for GitHub Actions
    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"metrics={json.dumps(metrics)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
