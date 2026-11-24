-- Run as the database administrator. Provision memberships explicitly; no open signup-to-org grants.
create table if not exists public.organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null check (length(name) between 1 and 120),
  created_at timestamptz not null default now()
);
create table if not exists public.memberships (
  org_id uuid not null references public.organizations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null default 'developer' check (role in ('owner', 'developer')),
  primary key (org_id, user_id)
);
create table if not exists public.copilot_projects (
  id uuid primary key,
  org_id uuid not null references public.organizations(id) on delete cascade,
  document jsonb not null,
  updated_at timestamptz not null default now(),
  constraint document_org_matches check (document->>'orgId' = org_id::text),
  constraint document_id_matches check (document->>'id' = id::text)
);
alter table public.organizations enable row level security;
alter table public.memberships enable row level security;
alter table public.copilot_projects enable row level security;
create policy "Read own memberships" on public.memberships for select to authenticated using (user_id = auth.uid());
create policy "Read member organizations" on public.organizations for select to authenticated using (
  exists (select 1 from public.memberships m where m.org_id = organizations.id and m.user_id = auth.uid())
);
create policy "Read organization projects" on public.copilot_projects for select to authenticated using (
  exists (select 1 from public.memberships m where m.org_id = copilot_projects.org_id and m.user_id = auth.uid())
);
-- No client write policies. The API validates identity and membership before scoped server writes.
revoke all on public.organizations, public.memberships, public.copilot_projects from anon;
grant select on public.organizations, public.memberships, public.copilot_projects to authenticated;
create index if not exists memberships_user_idx on public.memberships(user_id);
create index if not exists copilot_projects_org_idx on public.copilot_projects(org_id);
