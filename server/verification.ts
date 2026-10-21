import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import Stripe from "stripe";
import { patchedFiles, syntaxChecks } from "./core";
import type { Project, Run, Scenario } from "../src/types";

export const providerReady = () =>
  /^sk_test_/.test(process.env.STRIPE_SECRET_KEY ?? "");
export async function isolatedChecks(
  project: Project,
  signal: AbortSignal,
): Promise<Scenario[]> {
  if (process.env.RUNNER_ENABLED !== "true")
    return [
      {
        id: "isolation",
        name: "Isolated application checks",
        status: "blocked",
        evidence: "isolated fixture",
        detail:
          "Enable the fixed Docker runner to execute candidate code. No uploaded code was executed on the host.",
      },
    ];
  const containerName = `ralio-${randomUUID()}`;
  const files = patchedFiles(project.files, project.patch!);
  return new Promise((resolve) => {
    let settled = false;
    let stdout = "";
    let stderr = "";
    const args = [
      "run",
      "--rm",
      "--pull=never",
      "--name",
      containerName,
      "--network=none",
      "--read-only",
      "--cpus=0.5",
      "--memory=192m",
      "--memory-swap=192m",
      "--pids-limit=48",
      "--cap-drop=ALL",
      "--security-opt=no-new-privileges",
      "--user=10001:10001",
      "--tmpfs",
      "/work:rw,nosuid,nodev,size=16m,uid=10001,gid=10001,mode=0700",
      "--tmpfs",
      "/tmp:rw,nosuid,nodev,noexec,size=4m,uid=10001,gid=10001",
      "-i",
      "ralio-runner:1",
    ];
    const child = spawn("docker", args, {
      stdio: ["pipe", "pipe", "pipe"],
      env: {
        PATH: process.env.PATH,
        HOME: process.env.HOME,
        DOCKER_HOST: process.env.DOCKER_HOST,
      },
    });
    const cleanup = () => {
      const stop = spawn("docker", ["rm", "-f", containerName], {
        stdio: "ignore",
      });
      stop.on("error", () => {});
    };
    const finish = (results: Scenario[]) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal.removeEventListener("abort", cancel);
      child.kill("SIGKILL");
      cleanup();
      resolve(results);
    };
    const cancel = () =>
      finish([
        {
          id: "isolation",
          name: "Isolated application checks",
          status: "cancelled",
          evidence: "isolated fixture",
          detail: "Execution cancelled and container cleanup requested.",
        },
      ]);
    const timer = setTimeout(
      () =>
        finish([
          {
            id: "isolation",
            name: "Isolated application checks",
            status: "failed",
            evidence: "isolated fixture",
            detail:
              "Execution exceeded the 30-second limit; container cleanup requested.",
          },
        ]),
      30_000,
    );
    signal.addEventListener("abort", cancel, { once: true });
    child.stdout.on("data", (d) => {
      stdout += d;
      if (stdout.length > 64_000)
        finish([
          {
            id: "isolation",
            name: "Output limit",
            status: "failed",
            evidence: "isolated fixture",
            detail: "Runner exceeded its output limit.",
          },
        ]);
    });
    child.stderr.on("data", (d) => {
      stderr = (stderr + d).slice(0, 2000);
    });
    child.on("error", () =>
      finish([
        {
          id: "isolation",
          name: "Isolated application checks",
          status: "blocked",
          evidence: "isolated fixture",
          detail:
            "Docker is unavailable. Install/start Docker and build the runner image.",
        },
      ]),
    );
    child.on("close", (code) => {
      if (code !== 0)
        return finish([
          {
            id: "isolation",
            name: "Isolated application checks",
            status: code === 125 ? "blocked" : "failed",
            evidence: "isolated fixture",
            detail:
              code === 125
                ? "Docker or the fixed runner image is unavailable. Run npm run runner:build."
                : "Candidate execution failed. Check the supported fixture contract.",
          },
        ]);
      try {
        const parsed = JSON.parse(stdout);
        if (
          !Array.isArray(parsed) ||
          !parsed.every(
            (r) =>
              ["passed", "failed", "blocked"].includes(r.status) &&
              typeof r.name === "string",
          )
        )
          throw new Error();
        finish(parsed);
      } catch {
        finish([
          {
            id: "isolation",
            name: "Runner protocol",
            status: "failed",
            evidence: "isolated fixture",
            detail: "The runner did not return valid structured results.",
          },
        ]);
      }
    });
    child.stdin.on("error", () => {});
    child.stdin.end(
      JSON.stringify({
        files,
        entry: project.inspection.entry,
        task: project.task,
      }),
    );
    if (signal.aborted) cancel();
  });
}
export async function providerChecks(
  runId: string,
  signal: AbortSignal,
): Promise<Scenario[]> {
  const cases = [
    "Sandbox payment creation",
    "Additional customer action",
    "Provider decline",
    "Payment retry idempotency",
  ];
  if (!providerReady())
    return cases.map((name, i) => ({
      id: `provider-${i}`,
      name,
      status: "blocked",
      evidence: "Stripe sandbox",
      detail: "No Stripe sandbox key is configured. No provider call was made.",
    }));
  const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, {
    timeout: 12_000,
    maxNetworkRetries: 0,
  });
  const results: Scenario[] = [];
  const pendingCleanup = new Set<string>();
  const add = (i: number, ok: boolean, detail: string, providerId?: string) =>
    results.push({
      id: `provider-${i}`,
      name: cases[i],
      status: ok ? "passed" : "failed",
      evidence: "Stripe sandbox",
      detail: `Controlled adapter check, not an end-to-end candidate test. ${detail}`,
      providerId,
    });
  try {
    if (signal.aborted) return [];
    const params = {
      amount: 100,
      currency: "usd",
      payment_method_types: ["card"],
      metadata: { copilot_run: runId },
    };
    const intent = await stripe.paymentIntents.create(params, {
      idempotencyKey: `${runId}-create`,
    });
    if (intent.livemode) throw new Error("Unexpected live payment");
    pendingCleanup.add(intent.id);
    add(
      0,
      intent.amount === 100 && intent.currency === "usd",
      `Created test PaymentIntent ${intent.id}.`,
      intent.id,
    );
    if (signal.aborted) return results;
    const repeated = await stripe.paymentIntents.create(params, {
      idempotencyKey: `${runId}-create`,
    });
    add(
      3,
      repeated.id === intent.id,
      "Repeating the same key returned the same PaymentIntent.",
      repeated.id,
    );
    await stripe.paymentIntents.cancel(intent.id);
    pendingCleanup.delete(intent.id);
    if (signal.aborted) return results;
    const action = await stripe.paymentIntents.create(
      {
        ...params,
        payment_method: "pm_card_threeDSecure2Required",
        confirm: true,
      },
      { idempotencyKey: `${runId}-action` },
    );
    if (action.status !== "succeeded" && action.status !== "canceled")
      pendingCleanup.add(action.id);
    add(
      1,
      action.status === "requires_action",
      `Provider returned ${action.status}.`,
      action.id,
    );
    if (pendingCleanup.has(action.id)) {
      await stripe.paymentIntents.cancel(action.id);
      pendingCleanup.delete(action.id);
    }
    if (signal.aborted) return results;
    try {
      await stripe.paymentIntents.create(
        { ...params, payment_method: "pm_card_chargeDeclined", confirm: true },
        { idempotencyKey: `${runId}-decline` },
      );
      add(2, false, "Expected a card decline.");
    } catch (e) {
      add(
        2,
        (e as { type?: string }).type === "StripeCardError",
        "Stripe returned a card error for the decline fixture.",
      );
    }
  } catch {
    for (let i = 0; i < cases.length; i++)
      if (!results.some((r) => r.id === `provider-${i}`))
        add(
          i,
          false,
          "Stripe sandbox request failed. Check server credentials and network access.",
        );
  } finally {
    for (const id of pendingCleanup) {
      try {
        await stripe.paymentIntents.cancel(id);
      } catch {
        results.push({
          id: `cleanup-${id}`,
          name: "Sandbox record cleanup",
          status: "failed",
          evidence: "Stripe sandbox",
          detail:
            "A test PaymentIntent could not be cancelled. Inspect it in the Stripe sandbox dashboard.",
          providerId: id,
        });
      }
    }
  }
  return results;
}
export async function verify(
  project: Project,
  run: Run,
  signal: AbortSignal,
  save: () => Promise<void>,
) {
  const event = async (title: string, detail: string) => {
    if (signal.aborted) return;
    run.events.push({ time: new Date().toISOString(), title, detail });
    await save();
  };
  try {
    await event(
      "Source identity checked",
      `Patch ${run.patchDigest.slice(0, 12)} is tied to source ${run.baseDigest.slice(0, 12)}.`,
    );
    const errors = syntaxChecks(patchedFiles(project.files, project.patch!));
    run.results.push({
      id: "syntax",
      name: "TypeScript syntax",
      status: errors.length ? "failed" : "passed",
      evidence: "static analysis",
      detail: errors.length
        ? errors.join("\n")
        : "All candidate TypeScript files transpile. This is a syntax check, not type checking or code execution.",
    });
    await event(
      "Static checks complete",
      errors.length
        ? "Syntax issues need review."
        : "TypeScript syntax passed.",
    );
    if (signal.aborted) return;
    const local = await isolatedChecks(project, signal);
    if (signal.aborted) return;
    run.results.push(...local);
    run.local =
      errors.length || local.some((r) => r.status === "failed")
        ? "failed"
        : local.some((r) => r.status === "blocked")
          ? "blocked"
          : "passed";
    await event(
      "Isolated checks finished",
      run.local === "blocked"
        ? "The isolated runner needs configuration."
        : "Independent fixture results recorded.",
    );
    if (signal.aborted) return;
    const provider = await providerChecks(run.id, signal);
    if (signal.aborted) return;
    run.results.push(...provider);
    run.sandbox = provider.some((r) => r.status === "failed")
      ? "failed"
      : provider.some((r) => r.status === "blocked")
        ? "blocked"
        : "passed";
    await event(
      "Provider checks finished",
      run.sandbox === "blocked"
        ? "Add a Stripe sandbox key to enable provider scenarios."
        : "Controlled adapter evidence recorded separately from application checks.",
    );
  } catch {
    run.local = "failed";
    run.sandbox = "blocked";
    run.events.push({
      time: new Date().toISOString(),
      title: "Verification failed",
      detail:
        "A verification prerequisite changed or a check could not complete.",
    });
  } finally {
    if (signal.aborted) {
      run.status = "cancelled";
      run.local = "cancelled";
      run.sandbox = "cancelled";
    } else run.status = "complete";
    run.finishedAt = new Date().toISOString();
    await save();
  }
}
