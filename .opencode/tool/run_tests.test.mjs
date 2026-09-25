import runTests from "./run_tests.ts";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

const mkCtx = () => {
  const worktree = mkdtempSync(join(tmpdir(), "run-tests-"));
  return { worktree, directory: worktree };
};

test("successful command reports exit code 0", async (t) => {
  const ctx = mkCtx();
  t.after(() => rmSync(ctx.worktree, { recursive: true, force: true }));

  const res = await runTests.execute({ command: "true" }, ctx);

  assert.ok(typeof res === "string");
  assert.match(res, /exit_code: 0/);
});

test("failing command reports a nonzero exit code", async (t) => {
  const ctx = mkCtx();
  t.after(() => rmSync(ctx.worktree, { recursive: true, force: true }));

  const res = await runTests.execute({ command: "false" }, ctx);

  assert.ok(typeof res === "string");
  assert.match(res, /exit_code: [1-9]/);
});

test("long output is truncated to the tail with the total line count visible", async (t) => {
  const ctx = mkCtx();
  t.after(() => rmSync(ctx.worktree, { recursive: true, force: true }));

  const res = await runTests.execute({ command: "seq 1 300" }, ctx);

  assert.ok(typeof res === "string");
  assert.match(res, /exit_code: 0/);
  assert.match(res, /output lines: 300 \(showing last 200\)/);
  assert.match(res, /^101$/m);
  assert.doesNotMatch(res, /^100$/m);
});
