export type TaskKind = "webhooks" | "payments" | "results";
export type Outcome = "passed" | "failed" | "blocked" | "cancelled";
export type SourceFiles = Record<string, string>;
export interface Reference {
  title: string;
  url: string;
  retrievedAt: string | null;
  excerpt: string;
}
export interface Finding {
  title: string;
  detail: string;
  path: string;
  severity: "warning" | "info";
}
export interface Inspection {
  stack: string[];
  entry: string | null;
  dependencies: Record<string, string>;
  findings: Finding[];
  fileCount: number;
}
export interface Change {
  path: string;
  before: string;
  after: string;
  reason: string;
}
export interface Patch {
  id: string;
  baseDigest: string;
  digest: string;
  createdAt: string;
  changes: Change[];
  diff: string;
  plan: string[];
  questions: string[];
  references: Reference[];
  generator: "template" | "agent";
  model: string | null;
}
export interface Scenario {
  id: string;
  name: string;
  status: Outcome;
  evidence: "static analysis" | "isolated fixture" | "Stripe sandbox";
  detail: string;
  providerId?: string;
}
export interface RunEvent {
  time: string;
  title: string;
  detail: string;
}
export interface Run {
  id: string;
  patchId: string;
  baseDigest: string;
  patchDigest: string;
  status: "running" | "complete" | "cancelled";
  startedAt: string;
  finishedAt?: string;
  events: RunEvent[];
  results: Scenario[];
  local: Outcome | "pending";
  sandbox: Outcome | "pending";
}
export interface Project {
  id: string;
  orgId: string;
  name: string;
  description: string;
  task: TaskKind;
  createdAt: string;
  updatedAt: string;
  sourceDigest: string;
  files: SourceFiles;
  inspection: Inspection;
  patch: Patch | null;
  runs: Run[];
  sample: boolean;
}
export interface Config {
  auth: "local" | "supabase";
  supabaseUrl?: string;
  supabaseAnonKey?: string;
  agent: boolean;
  provider: boolean;
  runner: boolean;
  model: string;
}
