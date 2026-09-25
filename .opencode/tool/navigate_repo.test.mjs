import navigateRepo from "./navigate_repo.ts";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

const mkRepo = () => {
  const worktree = mkdtempSync(join(tmpdir(), "navigate-repo-"));
  return { worktree, directory: worktree };
};

const git = (args, cwd) => execFileSync("git", args, { cwd, stdio: "ignore" });

test("lists files staged in the index from the repo root by default", async (t) => {
  const ctx = mkRepo();
  t.after(() => rmSync(ctx.worktree, { recursive: true, force: true }));
  writeFileSync(join(ctx.worktree, "tracked.txt"), "hi\n");
  mkdirSync(join(ctx.worktree, "sub"));
  writeFileSync(join(ctx.worktree, "sub", "nested.txt"), "hi\n");
  git(["init", "-q"], ctx.worktree);
  git(["add", "tracked.txt", "sub/nested.txt"], ctx.worktree);

  const res = await navigateRepo.execute({}, ctx);

  assert.ok(typeof res === "string");
  assert.ok(res.includes("tracked.txt"));
  assert.ok(res.includes("sub/nested.txt"));
});

test("limits the listing and reports how many entries were hidden", async (t) => {
  const ctx = mkRepo();
  t.after(() => rmSync(ctx.worktree, { recursive: true, force: true }));
  for (const name of ["a.txt", "b.txt", "c.txt"]) {
    writeFileSync(join(ctx.worktree, name), "hi\n");
  }
  git(["init", "-q"], ctx.worktree);
  git(["add", "a.txt", "b.txt", "c.txt"], ctx.worktree);

  const res = await navigateRepo.execute({ path: ".", limit: 2 }, ctx);

  assert.ok(typeof res === "string");
  assert.ok(res.includes("a.txt"));
  assert.ok(res.includes("b.txt"));
  assert.ok(!res.includes("c.txt"));
  assert.match(res, /1 entr(y|ies) hidden/);
});

test("path escaping the worktree is rejected", async (t) => {
  const ctx = mkRepo();
  t.after(() => rmSync(ctx.worktree, { recursive: true, force: true }));

  const res = await navigateRepo.execute({ path: ".." }, ctx);

  assert.ok(typeof res === "string");
  assert.match(res, /outside the worktree/);
});
