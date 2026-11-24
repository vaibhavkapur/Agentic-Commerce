import { createClient } from "@supabase/supabase-js";
import type { Config } from "./types";
let token: string | null = null;
export let authClient: ReturnType<typeof createClient> | null = null;
export async function configureAuth(config: Config) {
  if (config.auth !== "supabase") return;
  authClient = createClient(config.supabaseUrl!, config.supabaseAnonKey!);
  token =
    (await authClient.auth.getSession()).data.session?.access_token ?? null;
  authClient.auth.onAuthStateChange((_event, session) => {
    token = session?.access_token ?? null;
  });
}
export async function request(path: string, options: RequestInit = {}) {
  const headers = new Headers(options.headers);
  headers.set("x-ralio-client", "workspace");
  if (token) headers.set("authorization", `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData))
    headers.set("content-type", "application/json");
  const response = await fetch(`/api${path}`, { ...options, headers });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error ?? "Something went wrong. Please try again.");
  }
  return response;
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  return (await request(path, options)).json();
}
export async function download(path: string, name: string) {
  const blob = await (await request(path)).blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
