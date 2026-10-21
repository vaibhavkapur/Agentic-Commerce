import { createHash, randomUUID } from "node:crypto";
import ts from "typescript";
import { createTwoFilesPatch } from "diff";
import type {
  SourceFiles,
  Inspection,
  Patch,
  TaskKind,
  Change,
  Reference,
} from "../src/types";

export const digest = (value: string) =>
  createHash("sha256").update(value).digest("hex");
export const sourceDigest = (files: SourceFiles) =>
  digest(
    JSON.stringify(
      Object.keys(files)
        .sort()
        .map((k) => [k, files[k]]),
    ),
  );
export const secretPattern =
  /(?:[sr]k_(?:live|test)_[A-Za-z0-9]{12,}|whsec_[A-Za-z0-9]{12,}|sk-proj-[A-Za-z0-9_-]{12,}|sk-[A-Za-z0-9]{24,}|sb_secret_[A-Za-z0-9_-]{12,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)/;
export function safePath(path: string) {
  if (
    !path ||
    path.length > 180 ||
    /[\\\x00-\x1f:]/.test(path) ||
    path.startsWith("/") ||
    path.split("/").some((p) => p === ".." || p === "." || p === "")
  )
    throw new Error("Unsafe source path. Use ordinary relative file paths.");
  if (
    /(^|\/)(node_modules|\.git|\.env(?:\..*)?|\.ssh|\.aws|\.codex|\.agents)(\/|$)/.test(
      path,
    ) &&
    !path.endsWith(".env.example")
  )
    throw new Error(
      "Remove dependencies, hidden credentials, and environment files before uploading.",
    );
  return path;
}
export function validateFiles(files: SourceFiles): SourceFiles {
  const names = Object.keys(files);
  if (!names.length || names.length > 100)
    throw new Error("A snapshot must contain 1–100 files.");
  let size = 0;
  for (const name of names) {
    safePath(name);
    if (typeof files[name] !== "string")
      throw new Error("Only text source files are supported.");
    size += Buffer.byteLength(files[name]);
    if (Buffer.byteLength(files[name]) > 256_000 || size > 2_000_000)
      throw new Error(
        "Snapshot exceeds the 2 MB expanded / 256 KB per file limit.",
      );
    if (files[name].includes("\0"))
      throw new Error("Binary files are not supported.");
    if (secretPattern.test(files[name]))
      throw new Error(
        `Possible credential in ${name}. Remove secrets before uploading.`,
      );
  }
  let pkg;
  try {
    pkg = JSON.parse(files["package.json"]);
  } catch {
    throw new Error("Include a valid package.json at the source root.");
  }
  if (!pkg.dependencies?.express && !pkg.devDependencies?.express)
    throw new Error(
      "This release supports Node.js / TypeScript / Express projects.",
    );
  if (!names.some((p) => p.endsWith(".ts")))
    throw new Error(
      "Include the TypeScript source files for your Express app.",
    );
  return files;
}
function middlewareMove(path: string, content: string): Change | null {
  const file = ts.createSourceFile(path, content, ts.ScriptTarget.Latest, true);
  const statements = file.statements;
  const json = statements.find((s) =>
    /\b\w+\.use\(\s*express\.json\(/.test(s.getText(file)),
  );
  if (!json) return null;
  const receiver = json.getText(file).match(/^(\w+)\.use/)?.[1];
  const routes = statements.filter(
    (s) =>
      s.getStart(file) > json.getStart(file) &&
      new RegExp(`^${receiver}\\.post\\(`).test(s.getText(file)) &&
      /express\.raw\(/.test(s.getText(file)) &&
      /webhook/i.test(s.getText(file)),
  );
  if (!routes.length) return null;
  const last = routes[routes.length - 1];
  // Moving a parser past other routes could alter their behavior. Refuse ambiguous layouts.
  const intervening = statements.filter(
    (s) =>
      s.getStart(file) > json.getStart(file) && s.getStart(file) < last.end,
  );
  if (
    intervening.some(
      (s) =>
        !routes.includes(s) &&
        !ts.isFunctionDeclaration(s) &&
        !ts.isTypeAliasDeclaration(s) &&
        !ts.isInterfaceDeclaration(s),
    )
  )
    return null;
  const start = json.getFullStart();
  const block = content.slice(start, json.end);
  let after = content.slice(0, start) + content.slice(json.end);
  const offset = last.end - block.length;
  after = after.slice(0, offset) + block + after.slice(offset);
  return {
    path,
    before: content,
    after,
    reason:
      "Register the raw-body webhook route before JSON middleware so Stripe receives the original request bytes.",
  };
}
export function inspect(files: SourceFiles): Inspection {
  const pkg = JSON.parse(files["package.json"]);
  const dependencies = { ...pkg.devDependencies, ...pkg.dependencies };
  const entry =
    Object.keys(files).find(
      (p) =>
        p.endsWith(".ts") &&
        /(?:const|let)\s+[A-Za-z_$][\w$]*\s*=\s*express\(/.test(files[p]),
    ) ?? null;
  const findings: Inspection["findings"] = [];
  for (const [path, content] of Object.entries(files)) {
    if (!path.endsWith(".ts")) continue;
    if (middlewareMove(path, content))
      findings.push({
        path,
        severity: "warning",
        title: "Webhook body is parsed too early",
        detail:
          "express.json() runs before the raw webhook route. Signature verification needs the original bytes.",
      });
    if (/constructEvent/.test(content) && !/event\.id|eventId/.test(content))
      findings.push({
        path,
        severity: "warning",
        title: "Repeated delivery needs a decision",
        detail:
          "No event ID handling was found. Choose durable, transactional deduplication before production.",
      });
  }
  if (!findings.length)
    findings.push({
      path: entry ?? "package.json",
      severity: "info",
      title: "Source inspection complete",
      detail:
        "No known middleware ordering issue found. Review the generated integration and verify its behavior.",
    });
  return {
    stack: [
      "Node.js",
      "TypeScript",
      "Express",
      ...(dependencies.stripe ? ["Stripe"] : []),
    ],
    dependencies,
    entry,
    findings,
    fileCount: Object.keys(files).length,
  };
}
export const references: Reference[] = [
  {
    title: "Webhook signatures",
    url: "https://docs.stripe.com/events/manage-webhook-endpoints",
    retrievedAt: null,
    excerpt: "Verify signatures against the original request body.",
  },
  {
    title: "Idempotent requests",
    url: "https://docs.stripe.com/api/idempotent_requests",
    retrievedAt: null,
    excerpt: "Reuse a stable idempotency key when retrying the same operation.",
  },
  {
    title: "Payment Intents lifecycle",
    url: "https://docs.stripe.com/payments/paymentintents/lifecycle",
    retrievedAt: null,
    excerpt:
      "Handle asynchronous payment states and additional customer action.",
  },
];
const documentationCache = new Map<number, Reference>();
export async function lookupDocs(
  index: number,
  signal?: AbortSignal,
): Promise<Reference> {
  const ref = references[index];
  if (!ref) throw new Error("Unknown documentation reference.");
  const cached = documentationCache.get(index);
  if (
    cached?.retrievedAt &&
    Date.now() - Date.parse(cached.retrievedAt) < 3_600_000
  )
    return cached;
  const response = await fetch(ref.url, {
    headers: { Accept: "text/markdown" },
    signal: AbortSignal.any([
      signal ?? new AbortController().signal,
      AbortSignal.timeout(8000),
    ]),
    redirect: "error",
  });
  if (!response.ok) throw new Error("Documentation lookup unavailable.");
  // The URL is fixed; never follow a URL supplied by source files or a model.
  const reader = response.body?.getReader();
  let size = 0;
  const chunks: Uint8Array[] = [];
  while (reader) {
    const next = await reader.read();
    if (next.done) break;
    size += next.value.length;
    if (size > 1_000_000) {
      await reader.cancel();
      break;
    }
    chunks.push(next.value);
  }
  const content = Buffer.concat(chunks)
    .toString("utf8")
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<style[\s\S]*?<\/style>/gi, "")
    .replace(/<[^>]+>/g, " ")
    .replace(/[ \t]+/g, " ");
  const relevant = content
    .split("\n")
    .filter((line) =>
      /raw|signature|idempotenc|requires_action|payment_intent|request body/i.test(
        line,
      ),
    )
    .join("\n")
    .slice(0, 6000);
  const doc = {
    ...ref,
    excerpt: relevant || content.slice(0, 3000),
    retrievedAt: new Date().toISOString(),
  };
  documentationCache.set(index, doc);
  return doc;
}
export function makePatch(
  files: SourceFiles,
  changes: Change[],
  plan: string[],
  questions: string[],
  generator: Patch["generator"] = "template",
  docs = references,
): Patch {
  if (!changes.length)
    throw new Error(
      "No supported change could be generated for this snapshot.",
    );
  if (new Set(changes.map((c) => c.path)).size !== changes.length)
    throw new Error("Duplicate patch path.");
  for (const change of changes) {
    safePath(change.path);
    if (
      !change.path.endsWith(".ts") ||
      /(^|\/)(tests?|runner|supabase)(\/|\.)/.test(change.path)
    )
      throw new Error("Patches may only edit application TypeScript files.");
    if ((files[change.path] ?? "") !== change.before)
      throw new Error("Patch base does not match the original source.");
    if (change.after.length > 256_000 || secretPattern.test(change.after))
      throw new Error("Patch contains a secret or oversized file.");
  }
  const diff = changes
    .map((c) =>
      createTwoFilesPatch(
        c.before ? `a/${c.path}` : "/dev/null",
        `b/${c.path}`,
        c.before,
        c.after,
        "",
        "",
        { context: 3 },
      ),
    )
    .join("\n");
  return {
    id: randomUUID(),
    baseDigest: sourceDigest(files),
    digest: digest(diff),
    createdAt: new Date().toISOString(),
    changes,
    diff,
    plan,
    questions,
    references: docs,
    generator,
    model: generator === "agent" ? process.env.OPENAI_MODEL || "gpt-4.1" : null,
  };
}
export const paymentModule = `import { Router } from 'express';
import Stripe from 'stripe';
export const payments = Router();
const stripe = () => new Stripe(process.env.STRIPE_SECRET_KEY!);
// Set server-owned prices and require your application's authentication middleware.
const priceInMinorUnits = 2500;
payments.post('/payments', async (req, res) => {
  const key = req.get('Idempotency-Key');
  if (!key || !/^[a-zA-Z0-9_-]{16,120}$/.test(key)) return res.status(400).json({ error: 'A stable Idempotency-Key is required' });
  try {
    const intent = await stripe().paymentIntents.create({ amount: priceInMinorUnits, currency: 'usd', automatic_payment_methods: { enabled: true } }, { idempotencyKey: key });
    return res.json({ id: intent.id, clientSecret: intent.client_secret, status: intent.status });
  } catch { return res.status(502).json({ error: 'Payment could not be created. Retry with the same key.' }); }
});
// Use verified webhooks to fulfill orders. A client response is not proof of payment.
export function paymentState(status: Stripe.PaymentIntent.Status) {
  switch (status) {
    case 'succeeded': return 'paid';
    case 'requires_action': return 'action_required';
    case 'requires_payment_method': return 'payment_method_required';
    case 'canceled': return 'cancelled';
    default: return 'pending';
  }
}
`;
export function generatePatch(files: SourceFiles, task: TaskKind): Patch {
  const inspection = inspect(files);
  const changes: Change[] = [];
  const questions = [
    "Confirm the Stripe sandbox API version and supported dependency versions before deployment.",
  ];
  if (task === "webhooks") {
    for (const [path, content] of Object.entries(files))
      if (path.endsWith(".ts")) {
        const change = middlewareMove(path, content);
        if (change) changes.push(change);
      }
    if (!changes.length)
      throw new Error(
        "No safely repairable raw-body ordering issue found. Use model-assisted generation for other webhook changes.",
      );
    if (inspection.findings.some((f) => f.title.includes("Repeated")))
      questions.push(
        "Select a durable event store; the application must atomically record event IDs with their business effects.",
      );
    return makePatch(
      files,
      changes,
      [
        "Inspect the Express middleware and webhook route order.",
        "Move raw-body routes before the JSON parser without changing handlers.",
        "Run syntax checks, isolated signature fixtures, and provider checks separately.",
      ],
      questions,
    );
  }
  const modulePath = "src/ralio-payments.ts";
  if (files[modulePath])
    throw new Error(
      "An integration already exists at src/ralio-payments.ts. Use model-assisted generation to update it.",
    );
  changes.push({
    path: modulePath,
    before: "",
    after: paymentModule,
    reason:
      "Add payment creation with stable idempotency keys and explicit asynchronous result states.",
  });
  questions.push(
    "Mount the payments router after JSON parsing and your authentication middleware. Use your order ID to namespace idempotency keys.",
    "Replace the example $25 price with a trusted server-side catalog lookup; connect paymentState to your UI.",
    "Associate payment intents with authenticated order ownership and use verified webhooks for fulfillment.",
  );
  return makePatch(
    files,
    changes,
    [
      "Add a small Stripe payment module.",
      "Expose creation errors and additional customer action explicitly.",
      "Review application-specific mounting, pricing, and order ownership decisions.",
    ],
    questions,
  );
}
export function syntaxChecks(files: SourceFiles) {
  const errors: string[] = [];
  for (const [name, content] of Object.entries(files))
    if (/\.tsx?$/.test(name)) {
      const result = ts.transpileModule(content, {
        fileName: name,
        reportDiagnostics: true,
        compilerOptions: {
          target: ts.ScriptTarget.ES2022,
          module: ts.ModuleKind.ESNext,
          jsx: ts.JsxEmit.ReactJSX,
        },
      });
      for (const d of result.diagnostics ?? [])
        if (d.category === ts.DiagnosticCategory.Error)
          errors.push(
            `${name}: ${ts.flattenDiagnosticMessageText(d.messageText, " ")}`,
          );
    }
  return errors;
}
export function patchedFiles(files: SourceFiles, patch: Patch) {
  if (sourceDigest(files) !== patch.baseDigest)
    throw new Error("Source changed. Generate and verify a new patch.");
  const actualDiff = patch.changes
    .map((c) =>
      createTwoFilesPatch(
        c.before ? `a/${c.path}` : "/dev/null",
        `b/${c.path}`,
        c.before,
        c.after,
        "",
        "",
        { context: 3 },
      ),
    )
    .join("\n");
  if (patch.diff !== actualDiff || digest(actualDiff) !== patch.digest)
    throw new Error("Patch contents changed. Regenerate before verification.");
  return {
    ...files,
    ...Object.fromEntries(patch.changes.map((c) => [c.path, c.after])),
  };
}
