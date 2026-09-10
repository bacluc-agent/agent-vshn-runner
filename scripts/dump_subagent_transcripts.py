#!/usr/bin/env python3

import json
import os
import secrets
import subprocess
import sys


def run_opencode(*args) -> str:
    env = dict(os.environ)
    return subprocess.run(
        ["opencode", *args], check=True, capture_output=True, text=True, env=env
    ).stdout


def compact_json(value) -> str:
    return json.dumps(value, separators=(",", ":"))


def as_text(value) -> str:
    return value if isinstance(value, str) else compact_json(value)


def trunc(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "...[truncated]"


def render_transcript(session: dict, session_id: str, label: str = "Subagent transcript") -> list[str]:
    agent = (session.get("info") or {}).get("agent") or "subagent"
    lines = [f"--- {label}: {agent} ({session_id}) ---"]
    for message in session.get("messages") or []:
        for part in message.get("parts") or []:
            if part.get("type") == "text" and len(part.get("text") or "") > 0:
                lines.append(f"[{agent}] {part['text']}")
            elif part.get("type") == "tool" and (part.get("tool") or "") != "task":
                state = part.get("state") or {}
                line = f"[{agent}:tool] {part.get('tool') or 'unknown'} {trunc(compact_json(state.get('input') or {}), 200)}"
                output = state.get("output")
                if (
                    state.get("status") == "completed"
                    and output is not None
                    and len(as_text(output)) > 0
                ):
                    line += "\n  output: " + trunc(as_text(output), 500)
                lines.append(line)
    return lines


def child_session_ids(root_export: dict) -> list[str]:
    ids = set()

    def walk(node):
        if isinstance(node, dict):
            if node.get("tool") == "task":
                session_id = ((node.get("state") or {}).get("metadata") or {}).get(
                    "sessionId"
                )
                if session_id:
                    ids.add(session_id)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(root_export)
    return sorted(ids)


def coordinator_session_id(sessions, title: str) -> str | None:
    for session in sessions:
        if session.get("title") == title:
            return session.get("id")
    return None


def main() -> int:
    title = os.environ.get("COORDINATOR_SESSION_TITLE", "coordinator-run")
    try:
        sessions = json.loads(run_opencode("session", "list", "--format", "json"))
        root_id = coordinator_session_id(sessions, title)
    except Exception:
        root_id = None
    if not root_id:
        print("No coordinator session found; skipping subagent transcripts.")
        return 0

    try:
        root_export = json.loads(run_opencode("export", root_id))
        child_ids = child_session_ids(root_export)
    except Exception:
        root_export = None
        child_ids = []

    token = secrets.token_hex(32)
    print(f"::stop-commands::{token}")

    if root_export is not None:
        for line in render_transcript(root_export, root_id, label="Coordinator transcript"):
            print(line)
    else:
        print("--- Coordinator transcript: export failed ---")

    if not child_ids:
        print("(No subagents were spawned.)")
    else:
        for child_id in child_ids:
            try:
                child_export = json.loads(run_opencode("export", child_id))
                for line in render_transcript(child_export, child_id):
                    print(line)
            except Exception:
                continue

    print(f"::{token}::")
    return 0


if __name__ == "__main__":
    sys.exit(main())
