import { test } from "node:test";
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { setTimeout } from "node:timers/promises";
import { isolatedChecks } from "../server/verification";
import {
  inspect,
  sourceDigest,
  generatePatch,
  makePatch,
} from "../server/core";
import { sampleFiles } from "../server/sample";
import type { Project, SourceFiles } from "../src/types";
process.env.RUNNER_ENABLED = "true";
const exec = promisify(execFile);
function project(files: SourceFiles = sampleFiles): Project {
  return {
    id: randomUUID(),
    orgId: "local",
    name: "Docker acceptance",
    description: "",
    task: "webhooks",
    createdAt: "",
    updatedAt: "",
    files,
    sourceDigest: sourceDigest(files),
    inspection: inspect(files),
    patch: generatePatch(files, "webhooks"),
    runs: [],
    sample: true,
  };
}
test(
  "unpatched sample fails and patched sample passes all four isolated HTTP fixtures",
  { timeout: 60_000 },
  async () => {
    const p = project();
    const original = structuredClone(p);
    original.patch = makePatch(
      sampleFiles,
      [
        {
          path: "src/app.ts",
          before: sampleFiles["src/app.ts"],
          after: sampleFiles["src/app.ts"],
          reason: "Unmodified benchmark",
        },
      ],
      [],
      [],
    );
    const broken = await isolatedChecks(original, new AbortController().signal);
    assert.equal(
      broken.find((r) => r.id === "valid-signature")?.status,
      "failed",
      JSON.stringify(broken),
    );
    const fixed = await isolatedChecks(p, new AbortController().signal);
    assert.equal(fixed.length, 4, JSON.stringify(fixed));
    assert(
      fixed.every((r) => r.status === "passed"),
      JSON.stringify(fixed),
    );
  },
);
test(
  "second repository layout and network/host isolation survive real container execution",
  { timeout: 35_000 },
  async () => {
    const files = { ...sampleFiles };
    const source = files["src/app.ts"];
    delete files["src/app.ts"];
    files["checkout/http/application.ts"] = source
      .replace(/\bapp\b/g, "merchant")
      .replace("/webhooks/stripe", "/api/payment/webhook");
    files["checkout/http/application.ts"] =
      "import fs from 'node:fs';\nimport net from 'node:net';\n" +
      files["checkout/http/application.ts"];
    files["checkout/http/application.ts"] = files[
      "checkout/http/application.ts"
    ].replace(
      "const merchant = express();",
      `const merchant = express();
if (process.getuid?.() === 0 || fs.existsSync('/var/run/docker.sock') || fs.existsSync('/Users') || process.env.OPENAI_API_KEY) throw new Error('Isolation failed');
let writableRoot = false;
try { fs.writeFileSync('/opt/ralio/tampered', 'x'); writableRoot = true; } catch {}
if (writableRoot) throw new Error('Root filesystem is writable');
const escaped = await new Promise<boolean>((resolve) => { const socket = net.connect({ host: '1.1.1.1', port: 443 }); socket.setTimeout(300); socket.once('connect', () => { socket.destroy(); resolve(true); }); socket.once('error', () => resolve(false)); socket.once('timeout', () => { socket.destroy(); resolve(false); }); });
if (escaped) throw new Error('Network escaped');`,
    );
    const results = await isolatedChecks(
      project(files),
      new AbortController().signal,
    );
    assert.equal(results.length, 4, JSON.stringify(results));
    assert(
      results.every((r) => r.status === "passed"),
      JSON.stringify(results),
    );
  },
);
test(
  "cancellation terminates an unresponsive candidate and removes its container",
  { timeout: 15_000 },
  async () => {
    const before = (
      await exec("docker", ["ps", "-aq", "--filter", "name=^ralio-"])
    ).stdout
      .trim()
      .split("\n")
      .filter(Boolean);
    const p = project();
    p.patch = makePatch(
      p.files,
      [
        {
          path: "src/app.ts",
          before: p.files["src/app.ts"],
          after:
            "import express from 'express';\nconst app=express();\napp.post('/webhook',express.raw({type:'application/json'}),()=>{});\nwhile(true) {}\nexport default app;\n",
          reason: "Unresponsive acceptance fixture",
        },
      ],
      [],
      [],
    );
    const controller = new AbortController();
    const pending = isolatedChecks(p, controller.signal);
    await setTimeout(1000);
    controller.abort();
    const results = await pending;
    assert.equal(results[0].status, "cancelled");
    let remaining: string[] = [];
    for (let i = 0; i < 30; i++) {
      remaining = (
        await exec("docker", ["ps", "-aq", "--filter", "name=^ralio-"])
      ).stdout
        .trim()
        .split("\n")
        .filter((id) => id && !before.includes(id));
      if (!remaining.length) break;
      await setTimeout(100);
    }
    assert.deepEqual(remaining, [], "cancelled container is removed");
  },
);
