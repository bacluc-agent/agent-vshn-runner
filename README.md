# agent-vshn-runner

GitHub Actions runner for the agent-vshn-todo repository: scheduled issue runner and OpenCode workflows.

## Completion check

Run `./scripts/completion-check` before pushing. It runs all quality checks (Prettier formatting check and actionlint) in Docker and exits non-zero if any check fails. `.github/workflows/ci.yml` runs the same script on every push and pull request.

## Configuration

Repository variables:

- `ISSUE_REPOSITORY`: repository that holds the issues (defaults to this repository)
- `MODEL_AVAILABILITY_CACHE_ISSUE`: issue number of the model-discovery cache (auto-detected by title when unset)
- `VSHN_US_AI_BASE_URL`: base URL of the vshn-us-ai provider (unset until the API key is configured)

Repository secrets:

- `BACLUC_AGENT_GITHUB_TOKEN`: PAT with access to the issue repository
- `VSHN_US_AI_API_KEY`: API key for the vshn-us-ai provider
