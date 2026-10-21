// Independent harness is baked into the read-only image, never added to candidate files.
import { mkdir, writeFile, symlink } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { spawn } from "node:child_process";
import { createHmac } from "node:crypto";

let input = "";
for await (const chunk of process.stdin) {
  input += chunk;
  if (input.length > 3_000_000) process.exit(2);
}
const { files, entry, task } = JSON.parse(input);
const results = [];
const add = (id, name, status, detail) =>
  results.push({ id, name, status, detail, evidence: "isolated fixture" });
if (!entry || task !== "webhooks") {
  add(
    "contract",
    "Supported application contract",
    "blocked",
    "The fixed harness supports Express apps exporting app/default and a raw-body webhook route. Payment mounting requires merchant-specific tests.",
  );
  process.stdout.write(JSON.stringify(results));
  process.exit(0);
}
for (const [path, content] of Object.entries(files)) {
  if (
    /\\|\0/.test(path) ||
    path.startsWith("/") ||
    path.split("/").some((p) => p === ".." || p === "." || p === "")
  )
    process.exit(2);
  const target = resolve("/work", path);
  if (!target.startsWith("/work/")) process.exit(2);
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, content);
}
// Pin evaluation dependencies; never install a merchant's scripts or dependency graph.
await symlink("/opt/ralio/node_modules", "/work/node_modules");
const webhookPath = files[entry].match(
  /\.post\(\s*['"]([^'"]*webhook[^'"]*)['"]/,
)?.[1];
if (!webhookPath) {
  add(
    "contract",
    "Webhook route contract",
    "blocked",
    "No literal webhook route found in the application entry point.",
  );
  process.stdout.write(JSON.stringify(results));
  process.exit(0);
}
const child = spawn(
  process.execPath,
  ["--import", "tsx", "/opt/ralio/launch.mjs", resolve("/work", entry)],
  {
    cwd: "/opt/ralio",
    stdio: ["ignore", "ignore", "ignore"],
    env: {
      PATH: process.env.PATH,
      NODE_ENV: "test",
      STRIPE_SECRET_KEY: "sk_test_fixture",
      STRIPE_WEBHOOK_SECRET: "whsec_fixture",
    },
  },
);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const call = (path, options = {}) =>
  fetch(`http://127.0.0.1:8787${path}`, {
    ...options,
    signal: AbortSignal.timeout(1500),
    redirect: "error",
  });
try {
  let ready = false;
  for (let i = 0; i < 40; i++) {
    try {
      await call("/");
      ready = true;
      break;
    } catch {
      await sleep(100);
    }
  }
  if (!ready)
    throw new Error(
      "Application did not start with the fixed evaluator dependencies and export contract.",
    );
  const payload = JSON.stringify({
    id: "evt_fixture_one",
    object: "event",
    type: "payment_intent.succeeded",
    data: { object: { id: "pi_fixture_one", amount: 100, currency: "usd" } },
  });
  const timestamp = Math.floor(Date.now() / 1000);
  const signature = `t=${timestamp},v1=${createHmac("sha256", "whsec_fixture").update(`${timestamp}.${payload}`).digest("hex")}`;
  const send = (body, sig) =>
    call(webhookPath, {
      method: "POST",
      headers: { "content-type": "application/json", "stripe-signature": sig },
      body,
    });
  const valid = await send(payload, signature);
  add(
    "valid-signature",
    "Valid webhook signature",
    valid.ok ? "passed" : "failed",
    `Original request bytes returned HTTP ${valid.status}. Local HMAC fixture; no provider call.`,
  );
  const tampered = await send(payload.replace("100", "200"), signature);
  add(
    "tampered-payload",
    "Modified payload rejected",
    tampered.status === 400 ? "passed" : "failed",
    `Tampered payload returned HTTP ${tampered.status}.`,
  );
  const invalid = await send(payload, `t=${timestamp},v1=${"0".repeat(64)}`);
  add(
    "invalid-signature",
    "Invalid signature rejected",
    invalid.status === 400 ? "passed" : "failed",
    `Invalid signature returned HTTP ${invalid.status}.`,
  );
  await send(payload, signature);
  await send(payload, signature);
  const effects = await call("/test/fulfillments");
  if (effects.ok) {
    const data = await effects.json();
    add(
      "duplicate-delivery",
      "Repeated delivery has one business effect",
      data.count === 1 ? "passed" : "failed",
      `Fixture reported ${data.count} effects for repeated event ID. In-memory fixture only; durable concurrency is not verified.`,
    );
  } else
    add(
      "duplicate-delivery",
      "Repeated delivery has one business effect",
      "blocked",
      "No /test/fulfillments fixture endpoint. Provide merchant-specific acceptance tests for durable deduplication.",
    );
} catch (e) {
  add(
    "application",
    "Application execution",
    "failed",
    String(e.message).slice(0, 200),
  );
} finally {
  child.kill("SIGKILL");
}
process.stdout.write(JSON.stringify(results));
