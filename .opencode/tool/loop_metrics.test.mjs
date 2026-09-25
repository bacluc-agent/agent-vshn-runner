import loopMetrics, { computeMetrics, emitMetrics } from "./loop_metrics.ts";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

const mkCtx = () => {
  const worktree = mkdtempSync(join(tmpdir(), "loop-metrics-"));
  return { worktree, directory: worktree };
};

test("computeMetrics calculates convergence rate and token cost", () => {
  const m = computeMetrics(10, 2, "success", 0.05);
  assert.equal(m.steps, 10);
  assert.equal(m.tokenCostPerStep, 0.05);
  assert.equal(m.convergenceRate, 5); // 10 / 2
  assert.equal(m.failureMode, "success");
  assert.ok(m.terminatedAt);
});

test("emitMetrics writes summary and JSON artifact", () => {
  const ctx = mkCtx();
  const summaryPath = join(ctx.worktree, "summary.md");
  const artifactPath = join(ctx.worktree, "metrics.json");
  const m = computeMetrics(3, 1, "timeout");
  const res = emitMetrics(m, summaryPath, artifactPath);
  assert.ok(res.summary.includes("timeout"));
  assert.ok(res.artifact.includes("metrics.json"));
  assert.ok(readFileSync(summaryPath, "utf8").includes("timeout"));
  const json = JSON.parse(readFileSync(artifactPath, "utf8"));
  assert.equal(json.steps, 3);
  assert.equal(json.failureMode, "timeout");
  rmSync(ctx.worktree, { recursive: true, force: true });
});

test("tool execute returns metrics string", async () => {
  const ctx = mkCtx();
  const res = await loopMetrics.execute(
    {
      steps: 5,
      progressDelta: 1,
      failureMode: "max-steps",
      tokenEstimate: 0.01,
      summaryPath: join(ctx.worktree, "summary.md"),
      artifactPath: join(ctx.worktree, "metrics.json"),
    },
    ctx,
  );
  assert.ok(typeof res === "string");
  assert.ok(res.includes("max-steps"));
  assert.ok(res.includes("metrics.json"));
  assert.ok(
    readFileSync(join(ctx.worktree, "summary.md"), "utf8").includes(
      "max-steps",
    ),
  );
  assert.equal(
    JSON.parse(readFileSync(join(ctx.worktree, "metrics.json"), "utf8")).steps,
    5,
  );
  rmSync(ctx.worktree, { recursive: true, force: true });
});
