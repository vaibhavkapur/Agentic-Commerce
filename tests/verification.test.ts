import { test } from "node:test";
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { providerChecks, providerReady, verify } from "../server/verification";
import { generatePatch, sourceDigest, inspect } from "../server/core";
import { sampleFiles } from "../server/sample";
import type { Project, Run } from "../src/types";

test("missing or live keys never issue provider calls", async () => {
  const previous = process.env.STRIPE_SECRET_KEY;
  try {
    for (const key of ["", "sk_live_placeholder"]) {
      process.env.STRIPE_SECRET_KEY = key;
      assert.equal(providerReady(), false);
      const results = await providerChecks(
        randomUUID(),
        new AbortController().signal,
      );
      assert.equal(results.length, 4);
      assert(results.every((r) => r.status === "blocked"));
      assert(results.every((r) => r.detail.includes("No provider call")));
    }
  } finally {
    if (previous === undefined) delete process.env.STRIPE_SECRET_KEY;
    else process.env.STRIPE_SECRET_KEY = previous;
  }
});
function fixture(): { project: Project; run: Run } {
  const patch = generatePatch(sampleFiles, "webhooks");
  const project: Project = {
    id: randomUUID(),
    orgId: "local",
    name: "test",
    description: "",
    task: "webhooks",
    createdAt: "",
    updatedAt: "",
    sourceDigest: sourceDigest(sampleFiles),
    files: sampleFiles,
    inspection: inspect(sampleFiles),
    patch,
    runs: [],
    sample: true,
  };
  const run: Run = {
    id: randomUUID(),
    patchId: patch.id,
    patchDigest: patch.digest,
    baseDigest: patch.baseDigest,
    status: "running",
    startedAt: new Date().toISOString(),
    events: [],
    results: [],
    local: "pending",
    sandbox: "pending",
  };
  return { project, run };
}
test("cancelled verification cannot produce passing run dimensions", async () => {
  const { project, run } = fixture();
  const controller = new AbortController();
  controller.abort();
  let saves = 0;
  await verify(project, run, controller.signal, async () => {
    saves++;
  });
  assert.equal(run.status, "cancelled");
  assert.equal(run.local, "cancelled");
  assert.equal(run.sandbox, "cancelled");
  assert(run.finishedAt);
  assert(saves > 0);
});
test("changed source produces failed/blocked evidence instead of pending success", async () => {
  const { project, run } = fixture();
  project.files = { ...sampleFiles, "new.ts": "// modified" };
  await verify(project, run, new AbortController().signal, async () => {});
  assert.equal(run.status, "complete");
  assert.equal(run.local, "failed");
  assert.equal(run.sandbox, "blocked");
});
