import "dotenv/config";
import express from "express";
import multer from "multer";
import { randomUUID } from "node:crypto";
import { resolve } from "node:path";
import { z } from "zod";
import {
  initStore,
  listProjects,
  getProject,
  saveProject,
  supabase,
  authorizedOrg,
} from "./store";
import { readArchive } from "./archive";
import {
  inspect,
  sourceDigest,
  validateFiles,
  generatePatch,
  references,
  lookupDocs,
  secretPattern,
} from "./core";
import { generateWithAgent } from "./agent";
import { sampleFiles } from "./sample";
import { verify, providerReady } from "./verification";
import type { Project, Run, TaskKind } from "../src/types";

const app = express();
const port = Number(process.env.PORT || 4318);
const host = process.env.HOST || "127.0.0.1";
if (!["127.0.0.1", "localhost", "::1"].includes(host) && !supabase)
  throw new Error(
    "Supabase authentication is required before listening beyond loopback.",
  );
app.disable("x-powered-by");
app.use(express.json({ limit: "64kb" }));
const active = new Map<string, AbortController>();
const limits = new Map<string, { start: number; count: number }>();
app.use("/api", async (req, res, next) => {
  res.setHeader("Cache-Control", "no-store");
  res.setHeader("X-Content-Type-Options", "nosniff");
  const origin = req.get("origin");
  if (
    origin &&
    ![
      `http://localhost:${port}`,
      `http://127.0.0.1:${port}`,
      "http://127.0.0.1:5173",
      "http://localhost:5173",
      process.env.APP_ORIGIN,
    ]
      .filter(Boolean)
      .includes(origin)
  )
    return res.status(403).json({ error: "Origin not allowed." });
  if (!supabase && !["localhost", "127.0.0.1", "[::1]"].includes(req.hostname))
    return res.status(403).json({ error: "Local workspace only." });
  if (req.method !== "GET" && req.get("x-ralio-client") !== "workspace")
    return res
      .status(403)
      .json({ error: "Workspace request header required." });
  if (req.path === "/config") return next();
  if (!supabase) {
    res.locals.orgId = "local";
    return next();
  }
  const token = req.get("authorization")?.replace(/^Bearer /, "");
  if (!token)
    return res.status(401).json({ error: "Sign in to access your workspace." });
  const {
    data: { user },
    error,
  } = await supabase.auth.getUser(token);
  if (error || !user)
    return res
      .status(401)
      .json({ error: "Your session expired. Sign in again." });
  const { data: memberships } = await supabase
    .from("memberships")
    .select("org_id")
    .eq("user_id", user.id);
  try {
    res.locals.orgId = authorizedOrg(
      req.get("x-organization-id"),
      (memberships ?? []).map((m) => m.org_id),
    );
  } catch {
    return res
      .status(403)
      .json({
        error:
          "No organization membership. Ask your workspace administrator to provision access.",
      });
  }
  next();
});
app.get("/api/config", (_req, res) =>
  res.json({
    auth: supabase ? "supabase" : "local",
    supabaseUrl: supabase ? process.env.SUPABASE_URL : undefined,
    supabaseAnonKey: supabase ? process.env.SUPABASE_ANON_KEY : undefined,
    agent: !!process.env.OPENAI_API_KEY,
    provider: providerReady(),
    runner: process.env.RUNNER_ENABLED === "true",
    model: process.env.OPENAI_MODEL || "gpt-4.1",
  }),
);
app.get("/api/projects", async (_req, res) =>
  res.json(await listProjects(res.locals.orgId)),
);
const createSchema = z.object({
  name: z.string().trim().min(2).max(60),
  task: z.enum(["webhooks", "payments", "results"]),
  description: z.string().max(240).optional(),
});
async function createProject(
  orgId: string,
  name: string,
  task: TaskKind,
  files: Project["files"],
  sample: boolean,
  description = "",
) {
  if ((await listProjects(orgId)).length >= 25)
    throw new Error("This workspace supports up to 25 projects.");
  const now = new Date().toISOString();
  const project: Project = {
    id: randomUUID(),
    orgId,
    name,
    description,
    task,
    createdAt: now,
    updatedAt: now,
    sourceDigest: sourceDigest(files),
    files,
    inspection: inspect(files),
    patch: null,
    runs: [],
    sample,
  };
  await saveProject(project);
  return project;
}
app.post("/api/projects/sample", async (req, res) => {
  const data = createSchema.parse({
    name: "Northstar checkout",
    task: "webhooks",
    ...req.body,
  });
  res
    .status(201)
    .json(
      await createProject(
        res.locals.orgId,
        data.name,
        data.task,
        validateFiles(sampleFiles),
        true,
        "A sample Express checkout with a webhook signature issue.",
      ),
    );
});
const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 2_000_000, files: 1, fields: 3, fieldSize: 500 },
});
app.post("/api/projects", upload.single("archive"), async (req, res) => {
  const data = createSchema.parse(req.body);
  if (!req.file) throw new Error("Choose a ZIP source snapshot.");
  const files = await readArchive(req.file.buffer);
  res
    .status(201)
    .json(
      await createProject(
        res.locals.orgId,
        data.name,
        data.task,
        files,
        false,
        data.description,
      ),
    );
});
app.param("id", async (req, res, next, id) => {
  const project = await getProject(id, res.locals.orgId);
  if (!project) return res.status(404).json({ error: "Project not found." });
  res.locals.project = project;
  next();
});
app.get("/api/projects/:id", (_req, res) => res.json(res.locals.project));
app.post("/api/projects/:id/generate", async (req, res) => {
  const project = res.locals.project as Project;
  if (active.has(project.id))
    return res
      .status(409)
      .json({ error: "A task is already active for this project." });
  const key = project.orgId;
  const limit = limits.get(key);
  const now = Date.now();
  if (limit && now - limit.start < 3_600_000 && limit.count >= 20)
    return res
      .status(429)
      .json({ error: "Generation limit reached. Try again in an hour." });
  limits.set(key, {
    start: limit && now - limit.start < 3_600_000 ? limit.start : now,
    count: limit && now - limit.start < 3_600_000 ? limit.count + 1 : 1,
  });
  const controller = new AbortController();
  active.set(project.id, controller);
  const timeout = setTimeout(() => controller.abort(), 90_000);
  try {
    const mode = z
      .enum(["template", "agent"])
      .parse(req.body.mode ?? "template");
    const patch =
      mode === "agent"
        ? await generateWithAgent(project, controller.signal)
        : generatePatch(project.files, project.task);
    if (mode === "template" && process.env.NODE_ENV !== "test") {
      patch.references = await Promise.all(
        references.map(async (ref, index) => {
          try {
            return await lookupDocs(index, controller.signal);
          } catch {
            return ref;
          }
        }),
      );
    }
    if (controller.signal.aborted)
      return res.status(409).json({ error: "Generation was cancelled." });
    if (project.sample && !patch.questions.some((q) => q.includes("in-memory")))
      patch.questions.push(
        "The sample uses an in-memory event store. Replace it with a transactional database operation before production.",
      );
    project.patch = patch;
    project.updatedAt = new Date().toISOString();
    await saveProject(project);
    res.json(project);
  } finally {
    clearTimeout(timeout);
    active.delete(project.id);
  }
});
app.post("/api/projects/:id/verify", async (_req, res) => {
  const project = res.locals.project as Project;
  if (!project.patch)
    throw new Error("Generate a patch before running verification.");
  if (active.has(project.id))
    return res
      .status(409)
      .json({ error: "A task is already active for this project." });
  if (project.runs.length >= 50)
    throw new Error("This project reached its 50-run limit.");
  const run: Run = {
    id: randomUUID(),
    patchId: project.patch.id,
    baseDigest: project.sourceDigest,
    patchDigest: project.patch.digest,
    startedAt: new Date().toISOString(),
    status: "running",
    local: "pending",
    sandbox: "pending",
    events: [],
    results: [],
  };
  const controller = new AbortController();
  active.set(project.id, controller);
  project.runs.unshift(run);
  await saveProject(project);
  res.status(202).json(run);
  void verify(project, run, controller.signal, () => saveProject(project))
    .catch(() => {})
    .finally(() => active.delete(project.id));
});
app.post("/api/projects/:id/cancel", (_req, res) => {
  const project = res.locals.project as Project;
  const controller = active.get(project.id);
  if (!controller)
    return res.status(409).json({ error: "No active run to cancel." });
  controller.abort();
  res.json({ cancelled: true });
});
app.get("/api/projects/:id/patch", (_req, res) => {
  const project = res.locals.project as Project;
  if (!project.patch) throw new Error("No patch to download.");
  res
    .attachment(`ralio-${project.patch.baseDigest.slice(0, 8)}.patch`)
    .type("text/plain")
    .send(
      `# Source SHA-256: ${project.patch.baseDigest}\n# Patch SHA-256: ${project.patch.digest}\n${project.patch.diff}`,
    );
});
app.get("/api/projects/:id/report", (_req, res) => {
  const p = res.locals.project as Project;
  if (!p.patch) throw new Error("Generate a patch before exporting a report.");
  res
    .attachment(`ralio-report-${p.sourceDigest.slice(0, 8)}.json`)
    .json({
      project: p.name,
      sourceDigest: p.sourceDigest,
      patch: {
        ...p.patch,
        changes: p.patch.changes.map((c) => ({
          path: c.path,
          reason: c.reason,
        })),
        diff: undefined,
      },
      sourceDependencies: p.inspection.dependencies,
      verificationDependencies: {
        express: "5.1.0",
        stripe: "18.5.0",
        typescript: "5.9.2",
        stripeApiVersion: "2025-08-27.basil",
        runner: "ralio-runner:1",
        promptVersion: "1",
      },
      runs: p.runs.filter((r) => r.patchId === p.patch!.id),
      limitations: [
        "Static syntax checks are not type checks or application execution.",
        "The evaluator uses fixed dependencies, not the uploaded dependency graph.",
        "Stripe adapter scenarios do not establish end-to-end candidate correctness.",
        "Sandbox evidence does not establish production readiness.",
      ],
    });
});
app.get("/api/docs", (_req, res) => res.json(references));
app.post("/api/docs/:topic", async (req, res) => {
  const topic = z
    .enum(["signatures", "idempotency", "lifecycle"])
    .parse(req.params.topic);
  const doc = await lookupDocs(
    ["signatures", "idempotency", "lifecycle"].indexOf(topic),
  );
  res.json(doc);
});
app.use("/api", (_req, res) =>
  res.status(404).json({ error: "API route not found." }),
);
app.use(express.static(resolve("dist")));
app.get("/{*path}", (_req, res) => res.sendFile(resolve("dist/index.html")));
app.use(
  (
    error: Error,
    _req: express.Request,
    res: express.Response,
    _next: express.NextFunction,
  ) => {
    const message =
      error instanceof z.ZodError
        ? error.issues.map((i) => i.message).join("; ")
        : error.message;
    res
      .status(400)
      .json({
        error:
          message && !secretPattern.test(message)
            ? message.slice(0, 350)
            : "Request could not be completed. Check server configuration.",
      });
  },
);
await initStore();
if (!supabase && !(await listProjects("local")).length) {
  const sample = await createProject(
    "local",
    "Northstar checkout",
    "webhooks",
    sampleFiles,
    true,
    "A sample Express checkout with a webhook signature issue.",
  );
  sample.patch = generatePatch(sample.files, sample.task);
  sample.patch.questions.push(
    "The sample in-memory event store must be replaced with a transactional database operation.",
  );
  await saveProject(sample);
}
const server = app.listen(port, host, () =>
  console.log(`Ralio API: http://${host}:${port}`),
);
for (const sig of ["SIGINT", "SIGTERM"] as const)
  process.on(sig, () => {
    for (const controller of active.values()) controller.abort();
    server.close(() => process.exit(0));
  });
