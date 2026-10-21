import { mkdir, readFile, writeFile, rename } from "node:fs/promises";
import { resolve } from "node:path";
import { createClient } from "@supabase/supabase-js";
import type { Project } from "../src/types";

const configured = !!(
  process.env.SUPABASE_URL &&
  process.env.SUPABASE_ANON_KEY &&
  process.env.SUPABASE_SERVICE_ROLE_KEY
);
if (
  !configured &&
  [
    process.env.SUPABASE_URL,
    process.env.SUPABASE_ANON_KEY,
    process.env.SUPABASE_SERVICE_ROLE_KEY,
  ].some(Boolean)
)
  throw new Error(
    "Supabase is partially configured. Supply all three settings; authentication will not fall back to local mode.",
  );
export const supabase = configured
  ? createClient(
      process.env.SUPABASE_URL!,
      process.env.SUPABASE_SERVICE_ROLE_KEY!,
      { auth: { persistSession: false, autoRefreshToken: false } },
    )
  : null;
const root = resolve(process.env.DATA_DIR || ".data");
let projects: Project[] = [];
let writeQueue = Promise.resolve();
export async function initStore() {
  if (supabase) return;
  await mkdir(root, { recursive: true, mode: 0o700 });
  try {
    projects = JSON.parse(
      await readFile(resolve(root, "projects.json"), "utf8"),
    );
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code !== "ENOENT") throw e;
  }
  for (const project of projects)
    for (const run of project.runs)
      if (run.status === "running") {
        run.status = "cancelled";
        run.local = "cancelled";
        run.sandbox = "cancelled";
        run.finishedAt = new Date().toISOString();
        run.events.push({
          time: run.finishedAt,
          title: "Run interrupted",
          detail: "The server restarted. Start a new verification run.",
        });
      }
}
export async function listProjects(orgId: string): Promise<Project[]> {
  if (supabase) {
    const { data, error } = await supabase
      .from("copilot_projects")
      .select("document")
      .eq("org_id", orgId);
    if (error)
      throw new Error(
        "Unable to load project data. Check the Supabase migration.",
      );
    return (data ?? []).map((r) => r.document as Project);
  }
  return projects.filter((p) => p.orgId === orgId);
}
export async function getProject(id: string, orgId: string) {
  return (await listProjects(orgId)).find((p) => p.id === id);
}
export async function saveProject(project: Project) {
  if (supabase) {
    const { error } = await supabase
      .from("copilot_projects")
      .upsert({ id: project.id, org_id: project.orgId, document: project });
    if (error) throw new Error("Unable to save project.");
    return;
  }
  const index = projects.findIndex(
    (p) => p.id === project.id && p.orgId === project.orgId,
  );
  if (index >= 0) projects[index] = project;
  else projects.push(project);
  const json = JSON.stringify(projects, null, 2);
  writeQueue = writeQueue
    .catch(() => {})
    .then(async () => {
      const tmp = resolve(root, "projects.json.tmp");
      await writeFile(tmp, json, { mode: 0o600 });
      await rename(tmp, resolve(root, "projects.json"));
    });
  await writeQueue;
}
export function authorizedOrg(
  requested: string | undefined,
  memberships: string[],
) {
  const org = requested || memberships[0];
  if (!org || !memberships.includes(org))
    throw new Error("Organization access denied.");
  return org;
}
