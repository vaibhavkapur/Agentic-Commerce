import { test } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setTimeout } from "node:timers/promises";

test(
  "API intake → generate → verify → exports, with access and evidence boundaries",
  { timeout: 25_000 },
  async () => {
    const dir = await mkdtemp(join(tmpdir(), "ralio-test-"));
    const port = 24000 + Math.floor(Math.random() * 15000);
    const server = spawn(
      process.execPath,
      ["--import", "tsx", "server/index.ts"],
      {
        cwd: process.cwd(),
        env: {
          ...process.env,
          NODE_ENV: "test",
          PORT: String(port),
          HOST: "127.0.0.1",
          DATA_DIR: dir,
          SUPABASE_URL: "",
          SUPABASE_ANON_KEY: "",
          SUPABASE_SERVICE_ROLE_KEY: "",
          OPENAI_API_KEY: "",
          STRIPE_SECRET_KEY: "",
          RUNNER_ENABLED: "false",
        },
        stdio: "ignore",
      },
    );
    const base = `http://127.0.0.1:${port}/api`;
    const post = (path: string, body: unknown = {}) =>
      fetch(base + path, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-ralio-client": "workspace",
        },
        body: JSON.stringify(body),
      });
    try {
      let ready = false;
      for (let i = 0; i < 80; i++) {
        try {
          const r = await fetch(base + "/config");
          if (r.ok) {
            ready = true;
            break;
          }
        } catch {}
        await setTimeout(100);
      }
      assert(ready, "API started");
      const config = await (await fetch(base + "/config")).json();
      assert.equal(config.auth, "local");
      assert.equal(config.provider, false);
      assert.equal(config.agent, false);
      assert.equal(
        (
          await fetch(base + "/projects", {
            headers: { Origin: "https://malicious.example" },
          })
        ).status,
        403,
      );
      assert.equal(
        (
          await fetch(base + "/projects/sample", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: "{}",
          })
        ).status,
        403,
      );
      assert.equal((await fetch(base + "/projects/not-mine")).status, 404);
      const create = await post("/projects/sample", {
        name: "Acceptance checkout",
        task: "webhooks",
      });
      assert.equal(create.status, 201);
      const project = await create.json();
      const id = project.id;
      const generated = await (await post(`/projects/${id}/generate`)).json();
      assert.equal(generated.patch.baseDigest, project.sourceDigest);
      assert.equal(generated.patch.generator, "template");
      assert.equal(generated.runs.length, 0);
      const runResponse = await post(`/projects/${id}/verify`);
      assert.equal(runResponse.status, 202);
      let current;
      for (let i = 0; i < 40; i++) {
        current = await (await fetch(base + `/projects/${id}`)).json();
        if (current.runs[0].status !== "running") break;
        await setTimeout(50);
      }
      const run = current.runs[0];
      assert.equal(run.status, "complete");
      assert.equal(run.local, "blocked");
      assert.equal(run.sandbox, "blocked");
      assert.equal(
        run.results.find((r: { id: string }) => r.id === "syntax").status,
        "passed",
      );
      assert(
        run.results
          .filter((r: { evidence: string }) => r.evidence === "Stripe sandbox")
          .every((r: { status: string }) => r.status === "blocked"),
      );
      const patch = await (await fetch(base + `/projects/${id}/patch`)).text();
      assert(patch.includes(project.sourceDigest));
      assert(patch.includes("--- a/src/app.ts"));
      const report = await (
        await fetch(base + `/projects/${id}/report`)
      ).json();
      assert.equal(report.sourceDigest, project.sourceDigest);
      assert.equal(report.runs[0].patchDigest, report.patch.digest);
      assert(!JSON.stringify(report).includes("sk_test_"));
      assert.equal((await post(`/projects/${id}/cancel`)).status, 409);
      const regen = await (await post(`/projects/${id}/generate`)).json();
      assert.notEqual(regen.patch.id, generated.patch.id);
      const newReport = await (
        await fetch(base + `/projects/${id}/report`)
      ).json();
      assert.equal(
        newReport.runs.length,
        0,
        "Old verification must not be attached to a new patch",
      );
    } finally {
      server.kill("SIGTERM");
      await new Promise<void>((resolve) =>
        server.once("close", () => resolve()),
      );
      await rm(dir, { recursive: true, force: true });
    }
  },
);
