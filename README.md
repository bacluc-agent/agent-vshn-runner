# agent-vshn-runner

Think of the agent system as a small factory.

- **agent-vshn-todo** is the private suggestion inbox or backlog: every new idea, bug report, or improvement request lands there as an issue.
- **agent-vshn-runner** is the automated factory floor: it reads the inbox on a schedule, picks the oldest unclaimed request, runs an agent pipeline, and opens a pull request with the proposed implementation.

This repository is the public half of that pair: it contains the worker workflows that keep the factory running.

## The two repositories

| Repository                                                                          | Visibility | Purpose                    | Notes                                                        |
| ----------------------------------------------------------------------------------- | ---------- | -------------------------- | ------------------------------------------------------------ |
| [bacluc-agent/agent-vshn-todo](https://github.com/bacluc-agent/agent-vshn-todo)     | private    | Holds the issue backlog    | New ideas and bug reports are filed here                     |
| [bacluc-agent/agent-vshn-runner](https://github.com/bacluc-agent/agent-vshn-runner) | public     | Holds the worker workflows | Issues are disabled here; work is tracked in agent-vshn-todo |

## From idea to implementation

```
┌─────────────────────────────────┐
│ Issue opened in                 │
│ agent-vshn-todo                 │
└────────────┬────────────────────┘
             │ every hour
             ▼
┌─────────────────────────────────┐
│ hourly-issue.yml                │
│ picks oldest open, unclaimed    │
│ issue                           │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ issue-selector chooses one      │
│ issue to implement              │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ coordinator delegates the work  │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ agent pipeline                  │
│  • planner writes a plan        │
│  • refiner checks the plan      │
│  • build writes the code        │
│  • tester verifies the change   │
│  • reviewer reviews the result  │
└────────────┬────────────────────┘
             │
             ▼
┌─────────────────────────────────┐
│ Pull request opened in the      │
│ target repository               │
└────────────┬────────────────────┘
             │
    ┌────────┴────────┐
    │                 │
    ▼                 ▼
 human review   review-fixes.yml
 and feedback   applies review comments
    │                 │
    └────────┬────────┘
             │
             ▼
        PR merged
```

## Hourly issue runner

`.github/workflows/hourly-issue.yml` runs the first half of the cycle.

- **Schedule:** every hour at 24 minutes past the hour (`24 * * * *`), plus manual runs.
- **What it does:**
  1. Searches `agent-vshn-todo` for the oldest open issue that does **not** have the `agent-running` label.
  2. Uses the `issue-selector` agent to choose one issue from the candidate list.
  3. Adds the `agent-running` label so the same issue is not picked again.
  4. Dispatches `.github/workflows/opencode.yml` with the selected issue as a prompt.

The `agent-running` label is the factory's claim ticket: it prevents duplicate runs on the same issue.

## Review-fixes runner

`.github/workflows/review-fixes.yml` keeps existing pull requests moving.

- **Schedule:** every 4 hours at 32 minutes past the hour (`32 */4 * * *`), plus manual runs.
- **What it does:**
  1. Scans open pull requests in the issue repository for review comments from `@Bacluc` or `@bacluc-agent`.
  2. Generates a prompt for each PR that asks the agent to apply the review comments.
  3. Dispatches `.github/workflows/opencode.yml` in parallel for each PR.

## Agent pipeline

The work is done by OpenCode agents defined in the OpenCode configuration pulled from `provision-machines`. The agents play the following roles:

| Agent             | Role                                                          |
| ----------------- | ------------------------------------------------------------- |
| `issue-selector`  | Picks the most valuable issue to work on next                 |
| `model-discovery` | Chooses a reachable AI model for the current task             |
| `coordinator`     | Delegates work to the other agents and keeps the run on track |
| `planner`         | Produces a step-by-step implementation plan                   |
| `refiner`         | Reviews and tightens the plan before code is written          |
| `build`           | Writes the code and tests                                     |
| `tester`          | Runs tests and verifies the change works                      |
| `reviewer`        | Reviews the final pull request                                |

## Model availability

Before each run the `.github/actions/model-availability` action checks which AI models are currently reachable.

- Free models are listed first in the availability output and are preferred when no specific model is requested.
- Results are cached in a GitHub issue titled **"model-discovery cache"** inside `agent-vshn-todo`.
- A model that passed its last check is trusted for 24 hours.
- A model that failed is retried after 2 hours.
- If a coordinator run fails, the model used for that run is marked as failed in the cache.

## Completion check

Run the completion check before pushing:

```bash
./scripts/completion-check
```

The script runs Prettier and actionlint inside Docker. The same check runs automatically on every push and pull request via `.github/workflows/ci.yml`.

## Example walkthroughs

### Example A — fixing model authentication in agent-vshn-runner

- **Issue:** [bacluc-agent/agent-vshn-todo#5](https://github.com/bacluc-agent/agent-vshn-todo/issues/5) — "Make sure authenticating to VSHN_US_AI works"
- **Pull request:** [bacluc-agent/agent-vshn-runner#1](https://github.com/bacluc-agent/agent-vshn-runner/pull/1) — "Fix VSHN_US_AI authentication in model discovery" (merged)

**What happened:** The workflow that asks VSHN_US_AI "which models do you have?" was not sending the API key. The provider returned `401 Unauthorized`. The fix passes the API key as a Bearer token.

Code change in `.github/actions/model-availability/model_availability.py`:

```diff
-def fetch_model_ids(endpoint: str) -> list[str]:
-    """GET the v1/models endpoint with curl User-Agent + x-opencode-session; [] + warning on failure."""
+def fetch_model_ids(endpoint: str, api_key: str | None = None) -> list[str]:
+    """GET the v1/models endpoint with curl User-Agent, x-opencode-session, and optional Authorization; [] + warning on failure."""
     try:
         session_id = os.urandom(16).hex()
-        request = urllib.request.Request(
-            endpoint,
-            headers={"x-opencode-session": session_id, "User-Agent": "curl/8.5.0"},
-        )
+        headers = {"x-opencode-session": session_id, "User-Agent": "curl/8.5.0"}
+        if api_key:
+            headers["Authorization"] = f"Bearer {api_key}"
+        request = urllib.request.Request(endpoint, headers=headers)
```

A matching test was added to prove the key is sent, in `.github/actions/model-availability/test_model_availability.py`:

```diff
+        monkeypatch.setenv("VSHN_US_AI_API_KEY", "test-key")
 ...
+        assert captured["headers"].get("Authorization") == "Bearer test-key"
```

### Example B — letting free models push their work

- **Issue:** [bacluc-agent/agent-todo#80](https://github.com/bacluc-agent/agent-todo/issues/80) — "Enable the free models to use the BACLUC_AGENT_GITHUB_TOKEN"
- **Pull request:** [bacluc-agent/agent-todo#87](https://github.com/bacluc-agent/agent-todo/pull/87) — "fix(workflow): use BACLUC_AGENT_GITHUB_TOKEN for checkout to enable free model pushes" (merged)

**What happened:** The cheaper free models were checking out the repository with the default `GITHUB_TOKEN`, which does not have permission to push code. Switching the checkout step to use `BACLUC_AGENT_GITHUB_TOKEN` gave them the push permission they needed. This example is from the remote `bacluc-agent/agent-todo` repository, which uses the same runner setup.

Code change in `.github/workflows/opencode.yml`:

```diff
        - name: Checkout
          uses: actions/checkout@v4
          with:
            repository: bacluc-agent/agent-todo
            fetch-depth: 0
-           token: ${{ secrets.GITHUB_TOKEN }}
+           token: ${{ secrets.BACLUC_AGENT_GITHUB_TOKEN }}
```

## Glossary

| Term                         | Meaning                                                                                                                                |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| **Issue**                    | A ticket that describes a bug, idea, or task. Issues live in `agent-vshn-todo`.                                                        |
| **PR / Pull request**        | A proposed set of changes submitted for review before merging into the codebase.                                                       |
| **Workflow**                 | A GitHub Actions automation definition. This repository contains `hourly-issue.yml`, `review-fixes.yml`, `opencode.yml`, and `ci.yml`. |
| **Agent**                    | An AI role that performs a specific step, such as selecting an issue, planning, building, testing, or reviewing.                       |
| **OpenCode**                 | The command-line tool that runs the agents.                                                                                            |
| **Model**                    | An AI model the agents can call, for example a free model or a VSHN_US_AI model.                                                       |
| **Model-availability cache** | A GitHub issue in `agent-vshn-todo` that remembers which models were recently reachable.                                               |
| **Completion check**         | The local quality check script (`./scripts/completion-check`) that runs Prettier and actionlint.                                       |
| **Issue repository**         | The repository that holds the backlog, configured with the `ISSUE_REPOSITORY` variable. Defaults to the current repository.            |

## Configuration

Repository variables:

- `ISSUE_REPOSITORY`: repository that holds the issues (defaults to this repository)
- `MODEL_AVAILABILITY_CACHE_ISSUE`: issue number of the model-discovery cache (auto-detected by title when unset)
- `VSHN_US_AI_BASE_URL`: base URL of the vshn-us-ai provider (required to use VSHN_US_AI models)

Repository secrets:

- `BACLUC_AGENT_GITHUB_TOKEN`: PAT with access to the issue repository
- `VSHN_US_AI_API_KEY`: API key for the vshn-us-ai provider

The OpenCode CLI version is pinned in `.github/actions/setup-opencode/action.yml` and updated by Renovate.
