import {
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type FormEvent,
} from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Bell,
  BookOpen,
  Box,
  Braces,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Circle,
  CircleHelp,
  Clock3,
  Code2,
  Copy,
  FileCode2,
  FileDiff,
  FileText,
  Folder,
  FolderGit2,
  GitBranch,
  GitPullRequest,
  LayoutDashboard,
  Loader2,
  LockKeyhole,
  Menu,
  MoreHorizontal,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  Terminal,
  UploadCloud,
  Workflow,
  X,
  XCircle,
  Zap,
} from "lucide-react";
import { diffLines } from "diff";
import { api, configureAuth, authClient, download } from "./api";
import type {
  Project,
  Config,
  TaskKind,
  Run,
  Reference,
  Scenario,
} from "./types";

type Page =
  | "Overview"
  | "Projects"
  | "Run history"
  | "Documentation"
  | "Settings";
const taskNames: Record<TaskKind, string> = {
  webhooks: "Verify webhooks",
  payments: "Create a payment",
  results: "Handle payment results",
};
const short = (value: string) => value.slice(0, 10);
function relative(date: string) {
  const minutes = Math.max(
    0,
    Math.floor((Date.now() - Date.parse(date)) / 60000),
  );
  return minutes < 1
    ? "Just now"
    : minutes < 60
      ? `${minutes}m ago`
      : minutes < 1440
        ? `${Math.floor(minutes / 60)}h ago`
        : new Date(date).toLocaleDateString(undefined, {
            month: "short",
            day: "numeric",
          });
}
function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return (
    <span className={`badge ${tone}`}>
      <span className="badge-dot" />
      {children}
    </span>
  );
}
function Logo({ small = false }: { small?: boolean }) {
  return (
    <div className={`logo ${small ? "small" : ""}`}>
      <svg viewBox="0 0 32 32" fill="none" aria-hidden="true">
        <path
          d="M8 25V7h10c10 0 10 12 0 12h-4m5 0 8 6"
          stroke="currentColor"
          strokeWidth="4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      {!small && (
        <span>
          ralio<span className="logo-dot">.</span>
        </span>
      )}
    </div>
  );
}
function Empty({
  icon,
  title,
  text,
  action,
}: {
  icon: ReactNode;
  title: string;
  text: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">{icon}</div>
      <h3>{title}</h3>
      <p>{text}</p>
      {action}
    </div>
  );
}
function Modal({
  title,
  subtitle,
  close,
  children,
}: {
  title: string;
  subtitle?: string;
  close: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
      if (e.key === "Tab") {
        const nodes = ref.current?.querySelectorAll<HTMLElement>(
          "button, input, select, a[href], textarea",
        );
        if (!nodes?.length) return;
        const first = nodes[0],
          last = nodes[nodes.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    ref.current?.focus();
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("keydown", key);
      previous?.focus();
    };
  }, [close]);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        ref={ref}
      >
        <button
          className="icon-button modal-close"
          onClick={close}
          aria-label="Close dialog"
        >
          <X size={20} />
        </button>
        <div className="modal-symbol">
          <FolderGit2 size={24} />
        </div>
        <h2>{title}</h2>
        {subtitle && <p className="muted">{subtitle}</p>}
        {children}
      </div>
    </div>
  );
}
export default function App() {
  const [page, setPage] = useState<Page>("Overview");
  const [projects, setProjects] = useState<Project[]>([]);
  const [config, setConfig] = useState<Config | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const [modal, setModal] = useState<"project" | "connections" | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [menu, setMenu] = useState(false);
  const [notifications, setNotifications] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  const [narrow, setNarrow] = useState(
    () => window.matchMedia("(max-width: 720px)").matches,
  );
  const searchRef = useRef<HTMLInputElement>(null);
  const refresh = async () => {
    const data = await api<Project[]>("/projects");
    setProjects(data.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)));
    setSignedIn(true);
  };
  useEffect(() => {
    void (async () => {
      try {
        const c = await api<Config>("/config");
        setConfig(c);
        await configureAuth(c);
        await refresh();
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);
  useEffect(() => {
    if (!notice) return;
    const timeout = setTimeout(() => setNotice(""), 3500);
    return () => clearTimeout(timeout);
  }, [notice]);
  useEffect(() => {
    const query = window.matchMedia("(max-width: 720px)");
    const change = () => setNarrow(query.matches);
    query.addEventListener("change", change);
    return () => query.removeEventListener("change", change);
  }, []);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setActive(null);
        setPage("Projects");
        setTimeout(() => searchRef.current?.focus(), 20);
      }
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, []);
  const navigate = (p: Page) => {
    setPage(p);
    setActive(null);
    setMenu(false);
    setSearch("");
  };
  const openProject = (p: Project) => {
    setActive(p.id);
    setPage("Projects");
  };
  const updateProject = (p: Project) =>
    setProjects((old) => old.map((item) => (item.id === p.id ? p : item)));
  const current = projects.find((p) => p.id === active);
  const allRuns = projects
    .flatMap((p) => p.runs.map((run) => ({ project: p, run })))
    .sort((a, b) => b.run.startedAt.localeCompare(a.run.startedAt));
  const recent = projects.slice(0, 3);
  const filtered = projects.filter(
    (p) =>
      p.name.toLowerCase().includes(search.toLowerCase()) &&
      (filter === "all" || (filter === "patches" ? !!p.patch : !p.patch)),
  );
  const copy = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setNotice("Copied to clipboard");
    } catch {
      setError("Clipboard is unavailable in this browser.");
    }
  };
  return (
    <div className="app-shell">
      {menu && (
        <div className="mobile-overlay" onClick={() => setMenu(false)} />
      )}
      <aside
        className={`sidebar ${menu ? "open" : ""}`}
        inert={narrow && !menu}
      >
        <div className="brand">
          <Logo />
          <span className="brand-caption">INTEGRATION COPILOT</span>
        </div>
        <button
          className="workspace-switch"
          onClick={() => navigate("Settings")}
        >
          <span className="workspace-avatar">R</span>
          <span>
            My workspace
            <small>
              {config?.auth === "supabase"
                ? "Team workspace"
                : "Local workspace"}
            </small>
          </span>
          <ChevronDown size={15} />
        </button>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {(
            [
              [LayoutDashboard, "Overview"],
              [FolderGit2, "Projects"],
              [Activity, "Run history"],
            ] as const
          ).map(([Icon, label]) => (
            <button
              key={label}
              onClick={() => navigate(label)}
              className={page === label ? "nav-item active" : "nav-item"}
            >
              <Icon size={18} />
              <span>{label}</span>
              {label === "Projects" && (
                <span className="nav-count">{projects.length}</span>
              )}
              {label === "Overview" && page === label && (
                <span className="nav-active-dot" />
              )}
            </button>
          ))}
        </nav>
        <div className="nav-label second">RESOURCES</div>
        <nav aria-label="Resources">
          {(
            [
              [BookOpen, "Documentation"],
              [Settings2, "Settings"],
            ] as const
          ).map(([Icon, label]) => (
            <button
              key={label}
              onClick={() => navigate(label)}
              className={page === label ? "nav-item active" : "nav-item"}
            >
              <Icon size={18} />
              <span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sandbox-note">
            <div>
              <span className="status-dot" />
              <strong>A safe place to build</strong>
            </div>
            <p>
              Every integration starts
              <br />
              in a sandbox.
            </p>
            <button onClick={() => setModal("connections")}>
              View environment <ArrowUpRight size={14} />
            </button>
            <ShieldCheck className="note-watermark" size={68} />
          </div>
          <button
            className="help-link"
            onClick={() => navigate("Documentation")}
          >
            <CircleHelp size={17} /> Help & getting started{" "}
            <ArrowUpRight size={14} />
          </button>
          <button className="profile" onClick={() => navigate("Settings")}>
            <span className="profile-avatar">VK</span>
            <span>
              My workspace
              <small>
                {config?.auth === "supabase"
                  ? "Authenticated session"
                  : "Local developer"}
              </small>
            </span>
            <MoreHorizontal size={18} />
          </button>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            <button
              className="icon-button mobile-menu"
              aria-label="Open navigation"
              onClick={() => setMenu(true)}
            >
              <Menu size={20} />
            </button>
            <span className="breadcrumb-home">Workspace</span>
            <ChevronRight size={14} />
            <span>{page}</span>
            {current && (
              <>
                <ChevronRight size={14} />
                <span className="breadcrumb-project">{current.name}</span>
              </>
            )}
          </div>
          <div className="topbar-right">
            <button
              className="search-shortcut"
              onClick={() => {
                navigate("Projects");
                setTimeout(() => searchRef.current?.focus(), 20);
              }}
            >
              <Search size={16} />
              <span>Quick search</span>
              <kbd>⌘ K</kbd>
            </button>
            <span className="top-divider" />
            <span className="environment">
              <span className="status-dot" />
              Sandbox only
            </span>
            <div className="notification-wrap">
              <button
                className="icon-button"
                aria-label="View recent activity"
                onClick={() => setNotifications(!notifications)}
              >
                <Bell size={18} />
                {allRuns.length > 0 && <span className="notification-dot" />}
              </button>
              {notifications && (
                <div className="notification-panel">
                  <strong>Recent activity</strong>
                  {allRuns.length ? (
                    allRuns.slice(0, 3).map(({ project, run }) => (
                      <button
                        key={run.id}
                        onClick={() => {
                          openProject(project);
                          setNotifications(false);
                        }}
                      >
                        {project.name}
                        <small>
                          Verification {run.status} · {relative(run.startedAt)}
                        </small>
                      </button>
                    ))
                  ) : (
                    <p>
                      No verification runs yet. Open a project to run your first
                      checks.
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
        </header>
        {error && (
          <div className="error-banner" role="alert">
            <XCircle size={17} />
            <span>{error}</span>
            <button
              className="icon-button"
              aria-label="Dismiss error"
              onClick={() => setError("")}
            >
              <X size={16} />
            </button>
          </div>
        )}
        {loading ? (
          <main className="loading-page">
            <Loader2 className="spin" />
            <p>Opening your workspace…</p>
          </main>
        ) : !signedIn && config?.auth !== "supabase" ? (
          <main className="content">
            <Empty
              icon={<Workflow />}
              title="Your workspace is reconnecting"
              text="The local API is unavailable. Once it’s running, reload to return to your projects."
              action={
                <button
                  className="button primary"
                  onClick={() => window.location.reload()}
                >
                  Reload workspace <ArrowRight size={16} />
                </button>
              }
            />
          </main>
        ) : config?.auth === "supabase" && !signedIn ? (
          <Login
            onLogin={async () => {
              setError("");
              await refresh();
            }}
            onError={setError}
          />
        ) : current ? (
          <ProjectWorkspace
            project={current}
            config={config!}
            update={updateProject}
            back={() => setActive(null)}
            onError={setError}
            toast={setNotice}
            copy={copy}
          />
        ) : (
          <main className="content">
            {page === "Overview" && (
              <>
                <div className="page-heading">
                  <div>
                    <div className="eyebrow">
                      <span className="tiny-star">✳</span> YOUR BUILD, WITH A
                      LITTLE BACKUP
                    </div>
                    <h1>Let’s get you payment-ready.</h1>
                    <p>
                      From source code to a reviewed integration. One clear step
                      at a time.
                    </p>
                  </div>
                  <button
                    className="button primary"
                    onClick={() => setModal("project")}
                  >
                    <Plus size={17} /> New project
                  </button>
                </div>
                <section className="welcome-banner">
                  <div className="welcome-copy">
                    <span className="banner-label">
                      <Sparkles size={14} /> BUILT FOR YOUR NEXT INTEGRATION
                    </span>
                    <h2>
                      Less guesswork.
                      <br />
                      More <span>shipping confidence.</span>
                    </h2>
                    <p>
                      Bring your code. Get a focused patch, clear explanations,
                      <br className="desktop-break" /> and verification you can
                      actually trace.
                    </p>
                    <button
                      className="banner-link"
                      onClick={() =>
                        recent[0] ? openProject(recent[0]) : setModal("project")
                      }
                    >
                      {recent[0]
                        ? "Explore the sample project"
                        : "Start your first project"}{" "}
                      <ArrowRight size={16} />
                    </button>
                  </div>
                  <div
                    className="flow-illustration"
                    aria-label="Source to patch to verification"
                  >
                    <div className="orbit orbit-one" />
                    <div className="orbit orbit-two" />
                    <div className="flow-pill source-pill">
                      <span>
                        <Code2 size={20} />
                      </span>
                      <div>
                        Your source<small>Node.js + TypeScript</small>
                      </div>
                      <CheckCircle2 size={14} />
                    </div>
                    <div className="flow-line line-one" />
                    <div className="flow-pill copilot-pill">
                      <span className="copilot-star">✳</span>
                      <div>
                        A focused patch<small>A little help from Ralio</small>
                      </div>
                      <Sparkles size={15} />
                    </div>
                    <div className="flow-line line-two" />
                    <div className="flow-pill verify-pill">
                      <span>
                        <ShieldCheck size={20} />
                      </span>
                      <div>
                        Evidence, included
                        <small>Every check accounted for</small>
                      </div>
                    </div>
                    <span className="float-star star-one">✧</span>
                    <span className="float-star star-two">+</span>
                    <div className="illustration-caption">
                      <LockKeyhole size={11} /> Your code. Your control.
                    </div>
                  </div>
                </section>
                <div className="stats-grid">
                  {[
                    {
                      label: "Projects",
                      value: projects.length,
                      detail: "Your integration workspaces",
                      icon: FolderGit2,
                      tint: "sage",
                    },
                    {
                      label: "Patches ready",
                      value: projects.filter((p) => p.patch).length,
                      detail: "Generated and ready for review",
                      icon: FileDiff,
                      tint: "blue",
                    },
                    {
                      label: "Verification runs",
                      value: allRuns.length,
                      detail: allRuns.length
                        ? `${allRuns.filter((x) => x.run.status === "complete").length} completed runs`
                        : "Ready when you are",
                      icon: ShieldCheck,
                      tint: "sand",
                    },
                    {
                      label: "Open decisions",
                      value: projects.reduce(
                        (n, p) => n + (p.patch?.questions.length ?? 0),
                        0,
                      ),
                      detail: "A few things to make yours",
                      icon: GitBranch,
                      tint: "lavender",
                    },
                  ].map(({ label, value, detail, icon: Icon, tint }) => (
                    <div className="stat-card" key={label}>
                      <div className="stat-top">
                        <span>{label}</span>
                        <span className={`stat-icon ${tint}`}>
                          <Icon size={17} />
                        </span>
                      </div>
                      <strong>{String(value).padStart(2, "0")}</strong>
                      <small>{detail}</small>
                    </div>
                  ))}
                </div>
                <section className="projects-section">
                  <div className="section-heading">
                    <div>
                      <h2>
                        Pick up where you left off{" "}
                        <span className="count-chip">{projects.length}</span>
                      </h2>
                      <p>Your projects, from first look to final review.</p>
                    </div>
                    <button
                      className="text-button"
                      onClick={() => navigate("Projects")}
                    >
                      View all projects <ArrowRight size={15} />
                    </button>
                  </div>
                  {recent.length ? (
                    <div className="project-list">
                      {recent.map((p) => (
                        <ProjectRow
                          key={p.id}
                          project={p}
                          open={() => openProject(p)}
                        />
                      ))}
                    </div>
                  ) : (
                    <Empty
                      icon={<FolderGit2 />}
                      title="Your next integration starts here"
                      text="Upload an Express project or explore the sample checkout."
                      action={
                        <button
                          className="button primary"
                          onClick={() => setModal("project")}
                        >
                          Create a project <ArrowRight size={16} />
                        </button>
                      }
                    />
                  )}
                </section>
                <div className="bottom-grid">
                  <section className="panel activity-panel">
                    <div className="panel-title">
                      <h3>Workspace activity</h3>
                      <Activity size={17} />
                    </div>
                    <div className="activity-list">
                      {allRuns.slice(0, 2).map(({ project, run }) => (
                        <div className="activity-item" key={run.id}>
                          <span className="activity-icon">
                            <ShieldCheck size={15} />
                          </span>
                          <div>
                            <p>Verification {run.status}</p>
                            <small>
                              {project.name}{" "}
                              <span>· {relative(run.startedAt)}</span>
                            </small>
                          </div>
                        </div>
                      ))}
                      {recent.slice(0, allRuns.length ? 1 : 2).map((p) => (
                        <div className="activity-item" key={p.id}>
                          <span className="activity-icon">
                            <FolderGit2 size={15} />
                          </span>
                          <div>
                            <p>
                              {p.sample
                                ? "Sample project is ready to explore"
                                : "Source snapshot added"}
                            </p>
                            <small>
                              {p.name} <span>· {relative(p.createdAt)}</span>
                            </small>
                          </div>
                        </div>
                      ))}
                    </div>
                    <div className="activity-foot">
                      <span className="status-dot" /> All changes stay
                      reviewable. You’re in control.
                    </div>
                  </section>
                  <section className="guide-card">
                    <div className="guide-icon">
                      <BookOpen size={21} />
                    </div>
                    <span className="eyebrow">A GOOD PLACE TO START</span>
                    <h3>
                      Good integrations
                      <br />
                      start with the right context.
                    </h3>
                    <p>
                      Explore the supported stack, payment flows,
                      <br className="desktop-break" /> and what each
                      verification level means.
                    </p>
                    <button
                      className="text-button"
                      onClick={() => navigate("Documentation")}
                    >
                      Read the integration guide <ArrowUpRight size={16} />
                    </button>
                    <span className="guide-decoration">↗</span>
                  </section>
                </div>
                <footer className="page-footer">
                  <span>
                    <ShieldCheck size={13} /> Sandbox-first. Review always.
                  </span>
                  <span>Made for developers, by your side.</span>
                </footer>
              </>
            )}
            {page === "Projects" && (
              <>
                <div className="page-heading">
                  <div>
                    <div className="eyebrow">YOUR INTEGRATION WORKSPACES</div>
                    <h1>Projects</h1>
                    <p>
                      Small, focused changes. Every source snapshot accounted
                      for.
                    </p>
                  </div>
                  <button
                    className="button primary"
                    onClick={() => setModal("project")}
                  >
                    <Plus size={17} /> New project
                  </button>
                </div>
                <div className="filter-bar">
                  <div className="segmented">
                    {[
                      ["all", "All projects"],
                      ["patches", "Ready for review"],
                      ["new", "Awaiting patch"],
                    ].map(([id, label]) => (
                      <button
                        className={filter === id ? "selected" : ""}
                        onClick={() => setFilter(id)}
                        key={id}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  <label className="search-field">
                    <Search size={16} />
                    <input
                      ref={searchRef}
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder="Search projects…"
                      aria-label="Search projects"
                    />
                  </label>
                </div>
                {filtered.length ? (
                  <div className="project-list">
                    {filtered.map((p) => (
                      <ProjectRow
                        key={p.id}
                        project={p}
                        open={() => openProject(p)}
                      />
                    ))}
                  </div>
                ) : (
                  <Empty
                    icon={<Search />}
                    title={search ? "No matching projects" : "Nothing here yet"}
                    text={
                      search
                        ? "Try another project name or clear the filters."
                        : "Create a project to begin your next integration."
                    }
                    action={
                      <button
                        className="button secondary"
                        onClick={() => {
                          setFilter("all");
                          setSearch("");
                        }}
                      >
                        Clear filters
                      </button>
                    }
                  />
                )}
              </>
            )}
            {page === "Run history" && (
              <>
                <div className="page-heading">
                  <div className="heading-text">
                    <div className="eyebrow">
                      AN EVIDENCE TRAIL, NOT A GUESS
                    </div>
                    <h1>Run history</h1>
                    <p>Every check, with its exact source and patch version.</p>
                  </div>
                </div>
                {allRuns.length ? (
                  <div className="panel run-list">
                    {allRuns.map(({ project, run }) => (
                      <button
                        className="run-row"
                        key={run.id}
                        onClick={() => openProject(project)}
                      >
                        <span className="file-symbol">
                          <Terminal size={20} />
                        </span>
                        <div>
                          <strong>{project.name}</strong>
                          <small>
                            {short(run.id)} ·{" "}
                            {new Date(run.startedAt).toLocaleString()}
                          </small>
                        </div>
                        <Badge
                          tone={run.status === "running" ? "blue" : "neutral"}
                        >
                          {run.status}
                        </Badge>
                        <span className="muted">
                          {
                            run.results.filter((r) => r.status === "passed")
                              .length
                          }
                          /{run.results.length} checks passed
                        </span>
                        <ArrowUpRight size={18} />
                      </button>
                    ))}
                  </div>
                ) : (
                  <Empty
                    icon={<Activity />}
                    title="Your evidence trail starts here"
                    text="Open a project, review its patch, and run verification to see real results."
                    action={
                      <button
                        className="button primary"
                        onClick={() => navigate("Projects")}
                      >
                        Explore projects <ArrowRight size={16} />
                      </button>
                    }
                  />
                )}
              </>
            )}
            {page === "Documentation" && <Documentation />}
            {page === "Settings" && (
              <>
                <div className="page-heading">
                  <div>
                    <div className="eyebrow">
                      A WORKSPACE THAT WORKS FOR YOU
                    </div>
                    <h1>Workspace settings</h1>
                    <p>
                      Connections and boundaries for your integration workflow.
                    </p>
                  </div>
                </div>
                <div className="settings-grid">
                  <section className="panel settings-panel">
                    <h3>Connected services</h3>
                    <p className="muted">
                      Credentials stay on your server, outside source snapshots
                      and patches.
                    </p>
                    {[
                      {
                        name: "Stripe sandbox",
                        desc: "Run real provider scenarios against a test account.",
                        ready: config?.provider,
                        icon: "S",
                      },
                      {
                        name: "OpenAI",
                        desc: "Generate source-aware patches with the Agents SDK.",
                        ready: config?.agent,
                        icon: "✳",
                      },
                      {
                        name: "Isolated runner",
                        desc: "Execute application checks in a bounded Docker container.",
                        ready: config?.runner,
                        icon: "▧",
                      },
                      {
                        name: "Supabase",
                        desc: "Organization-scoped authentication and persistent project data.",
                        ready: config?.auth === "supabase",
                        icon: "ϟ",
                      },
                    ].map((c) => (
                      <div className="connection-row" key={c.name}>
                        <span className="connection-symbol">{c.icon}</span>
                        <div>
                          <strong>{c.name}</strong>
                          <small>{c.desc}</small>
                        </div>
                        <Badge tone={c.ready ? "green" : "neutral"}>
                          {c.ready ? "Configured" : "Not configured"}
                        </Badge>
                      </div>
                    ))}
                    <button
                      className="button secondary"
                      onClick={() => setModal("connections")}
                    >
                      Connection setup <ArrowUpRight size={15} />
                    </button>
                  </section>
                  <section className="panel settings-panel">
                    <ShieldCheck className="green-icon" size={27} />
                    <h3>Built with clear boundaries</h3>
                    <ul className="check-list">
                      <li>
                        <Check size={16} /> Stripe sandbox credentials only
                      </li>
                      <li>
                        <Check size={16} /> Immutable, hashed source snapshots
                      </li>
                      <li>
                        <Check size={16} /> Reviewable patches, never
                        auto-merged
                      </li>
                      <li>
                        <Check size={16} /> No host execution of uploaded code
                      </li>
                      <li>
                        <Check size={16} /> Explicit blocked and skipped checks
                      </li>
                    </ul>
                    <p className="callout">
                      This local release is for small, supported Express
                      projects. Validate the isolation service before external
                      deployment.
                    </p>
                    {config?.auth === "supabase" && (
                      <button
                        className="button secondary"
                        onClick={async () => {
                          await authClient?.auth.signOut();
                          setSignedIn(false);
                          setProjects([]);
                        }}
                      >
                        Sign out
                      </button>
                    )}
                  </section>
                </div>
              </>
            )}
          </main>
        )}
      </div>
      {modal === "project" && (
        <NewProject
          close={() => setModal(null)}
          onCreated={(p) => {
            setProjects((old) => [p, ...old]);
            openProject(p);
            setModal(null);
            setNotice("Source snapshot accepted");
          }}
        />
      )}
      {modal === "connections" && (
        <Modal
          title="Connect your environment"
          subtitle="Configure services on the server, then restart the app. Keys never go in the browser."
          close={() => setModal(null)}
        >
          <div className="setup-step">
            <span>1</span>
            <div>
              <strong>Start with your server environment</strong>
              <p>
                Copy .env.example to .env in the project directory. Set
                OPENAI_API_KEY for model-assisted generation and
                STRIPE_SECRET_KEY to a sandbox key beginning with sk_test_.
              </p>
            </div>
          </div>
          <div className="setup-step">
            <span>2</span>
            <div>
              <strong>Enable isolated verification</strong>
              <p>
                Start Docker, run the command below, then set
                RUNNER_ENABLED=true.
              </p>
              <div className="copy-code">
                <code>npm run runner:build</code>
                <button
                  className="icon-button"
                  aria-label="Copy runner command"
                  onClick={() => void copy("npm run runner:build")}
                >
                  <Copy size={15} />
                </button>
              </div>
            </div>
          </div>
          <div className="setup-step">
            <span>3</span>
            <div>
              <strong>Connect your team when ready</strong>
              <p>
                Apply supabase/migration.sql and set the Supabase URL, anonymous
                key, and server service role key. Provision organization
                memberships before signing in.
              </p>
            </div>
          </div>
          <button
            className="button primary full"
            onClick={() => setModal(null)}
          >
            Got it <Check size={16} />
          </button>
        </Modal>
      )}
      {notice && (
        <div className="toast" role="status">
          <CheckCircle2 size={17} />
          {notice}
        </div>
      )}
    </div>
  );
}

function ProjectRow({
  project: p,
  open,
}: {
  project: Project;
  open: () => void;
}) {
  const latest = p.runs.find((r) => r.patchId === p.patch?.id);
  return (
    <button className="project-row" onClick={open}>
      <span className="project-symbol">
        <Braces size={25} />
      </span>
      <div className="project-info">
        <div className="project-name">
          {p.name}
          {p.sample && <span className="sample-label">SAMPLE</span>}
        </div>
        <div className="project-meta">
          <span className="stripe-word">stripe</span>
          <span className="meta-dot">·</span>Node.js / Express
          <span className="meta-dot">·</span>
          <GitBranch size={12} />
          <span>{short(p.sourceDigest)}</span>
        </div>
      </div>
      <div className="project-task">
        <span>{taskNames[p.task]}</span>
        <small>
          {p.patch
            ? `${p.patch.changes.length} changed file${p.patch.changes.length === 1 ? "" : "s"}`
            : "Source ready for inspection"}
        </small>
      </div>
      <div className="project-status">
        <Badge tone={p.patch ? "green" : "neutral"}>
          {p.patch ? "Ready for review" : "Source accepted"}
        </Badge>
        <small>
          {latest
            ? `Verification ${latest.status}`
            : `Updated ${relative(p.updatedAt)}`}
        </small>
      </div>
      <ArrowUpRight size={19} className="project-arrow" />
    </button>
  );
}

function NewProject({
  close,
  onCreated,
}: {
  close: () => void;
  onCreated: (p: Project) => void;
}) {
  const [name, setName] = useState("");
  const [task, setTask] = useState<TaskKind>("webhooks");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [drag, setDrag] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!file) {
      setError("Choose a ZIP archive first.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.set("name", name);
      form.set("task", task);
      form.set("archive", file);
      onCreated(
        await api<Project>("/projects", { method: "POST", body: form }),
      );
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };
  const sample = async () => {
    setBusy(true);
    setError("");
    try {
      onCreated(
        await api<Project>("/projects/sample", {
          method: "POST",
          body: JSON.stringify({
            name: name.trim() || "Northstar checkout",
            task,
          }),
        }),
      );
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };
  const choose = (f: File | undefined) => {
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".zip")) {
      setError("Choose a .zip source snapshot.");
      return;
    }
    if (f.size > 2_000_000) {
      setError("The archive must be smaller than 2 MB.");
      return;
    }
    setFile(f);
    setError("");
    if (!name) setName(f.name.replace(/\.zip$/i, ""));
  };
  return (
    <Modal
      title="Start a new integration"
      subtitle="Bring a small Express project. We’ll help with the next step."
      close={close}
    >
      <form onSubmit={submit}>
        <label className="form-label">
          Project name
          <input
            required
            minLength={2}
            maxLength={60}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Acme checkout"
          />
        </label>
        <label className="form-label">
          What are you working on?
          <select
            value={task}
            onChange={(e) => setTask(e.target.value as TaskKind)}
          >
            {Object.entries(taskNames).map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <input
          ref={fileRef}
          type="file"
          accept=".zip"
          className="visually-hidden"
          aria-label="Source ZIP archive"
          onChange={(e) => choose(e.target.files?.[0])}
        />
        <button
          type="button"
          className={`drop-zone ${drag ? "dragging" : ""}`}
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            choose(e.dataTransfer.files[0]);
          }}
        >
          <UploadCloud size={29} />
          <strong>{file ? file.name : "Drop your source snapshot here"}</strong>
          <span>
            {file
              ? `${(file.size / 1024).toFixed(1)} KB · Click to replace`
              : "or click to browse your files"}
          </span>
          <small>ZIP · Up to 2 MB · No node_modules or secrets</small>
        </button>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <div className="intake-note">
          <LockKeyhole size={14} /> Your original source stays intact. Nothing
          runs on upload.
        </div>
        <button className="button primary full" disabled={busy}>
          {busy ? <Loader2 className="spin" size={16} /> : <Plus size={16} />}{" "}
          Create project
        </button>
        <div className="or-divider">
          <span>JUST EXPLORING?</span>
        </div>
        <button
          type="button"
          className="button secondary full"
          disabled={busy}
          onClick={() => void sample()}
        >
          <Box size={17} /> Try the sample checkout <ArrowRight size={16} />
        </button>
      </form>
    </Modal>
  );
}

function ProjectWorkspace({
  project: p,
  config,
  update,
  back,
  onError,
  toast,
  copy,
}: {
  project: Project;
  config: Config;
  update: (p: Project) => void;
  back: () => void;
  onError: (s: string) => void;
  toast: (s: string) => void;
  copy: (s: string) => Promise<void>;
}) {
  const [tab, setTab] = useState("Overview");
  const [busy, setBusy] = useState("");
  const [mode, setMode] = useState("template");
  const [selected, setSelected] = useState("");
  const [split, setSplit] = useState(false);
  const [sourcePath, setSourcePath] = useState(Object.keys(p.files)[0]);
  const [selectedRun, setSelectedRun] = useState("");
  const run =
    p.runs.find((r) => r.id === selectedRun) ??
    p.runs.find((r) => r.patchId === p.patch?.id);
  const running = p.runs.some((r) => r.status === "running");
  useEffect(() => {
    if (!running) return;
    const interval = setInterval(() => {
      void api<Project>(`/projects/${p.id}`)
        .then(update)
        .catch((e) => onError(e.message));
    }, 1000);
    return () => clearInterval(interval);
  }, [running, p.id]);
  const act = async (action: string) => {
    setBusy(action);
    try {
      if (action === "generate") {
        const value = await api<Project>(`/projects/${p.id}/generate`, {
          method: "POST",
          body: JSON.stringify({ mode }),
        });
        update(value);
        setSelected("");
        setSelectedRun("");
        setTab("Changes");
        toast("Patch is ready for review");
      } else if (action === "verify") {
        await api(`/projects/${p.id}/verify`, { method: "POST" });
        update(await api<Project>(`/projects/${p.id}`));
        setSelectedRun("");
        setTab("Verification");
      } else {
        await api(`/projects/${p.id}/cancel`, { method: "POST" });
        toast("Cancellation requested");
      }
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy("");
    }
  };
  const exportFile = async (kind: string) => {
    try {
      await download(
        `/projects/${p.id}/${kind}`,
        kind === "patch"
          ? `ralio-${short(p.sourceDigest)}.patch`
          : `ralio-${short(p.sourceDigest)}-report.json`,
      );
      toast(`${kind === "patch" ? "Patch" : "Report"} downloaded`);
    } catch (e) {
      onError((e as Error).message);
    }
  };
  const change =
    p.patch?.changes.find((c) => c.path === selected) ?? p.patch?.changes[0];
  return (
    <main className="content workspace-content">
      <button className="back-link" onClick={back}>
        <ArrowLeft size={15} /> All projects
      </button>
      <div className="page-heading project-heading">
        <div>
          <div className="eyebrow">
            <span className="stripe-word">stripe</span>
            <span className="meta-dot">/</span>
            {taskNames[p.task]}
          </div>
          <h1>
            {p.name}
            {p.sample && <span className="sample-label">SAMPLE PROJECT</span>}
          </h1>
          <p>
            <GitBranch size={13} />
            <span>Source {short(p.sourceDigest)}</span>
            <span>·</span>
            {p.inspection.fileCount} files<span>·</span>
            {p.inspection.stack.join(" / ")}
          </p>
        </div>
        <div className="heading-actions">
          {p.patch && (
            <button
              className="button secondary"
              onClick={() => void exportFile("patch")}
            >
              <ArrowDownToLine size={16} /> Export patch
            </button>
          )}
          <button
            className="button primary"
            disabled={!!busy || running || !p.patch}
            onClick={() => void act("verify")}
          >
            {running || busy === "verify" ? (
              <Loader2 className="spin" size={16} />
            ) : (
              <ShieldCheck size={16} />
            )}{" "}
            {running ? "Verifying…" : "Run verification"}
          </button>
        </div>
      </div>
      <div className="project-steps">
        {[
          {
            title: "Source accepted",
            sub: "Original snapshot preserved",
            done: true,
            icon: FolderGit2,
          },
          {
            title: "Patch generated",
            sub: p.patch ? "Ready for your review" : "Your next step",
            done: !!p.patch,
            icon: FileDiff,
          },
          {
            title: "Locally checked",
            sub: run
              ? `${run.local} · ${run.results.filter((r) => r.evidence !== "Stripe sandbox" && r.status === "passed").length} checks passed`
              : "Awaiting verification",
            done: run?.local === "passed",
            icon: Terminal,
          },
          {
            title: "Provider scenarios",
            sub: run
              ? `${run.sandbox} · adapter checks`
              : "Stripe sandbox required",
            done: run?.sandbox === "passed",
            icon: ShieldCheck,
          },
        ].map(({ title, sub, done, icon: Icon }, i) => (
          <div className={`project-step ${done ? "done" : ""}`} key={title}>
            <span className="step-icon">
              {done ? <Check size={17} /> : <Icon size={17} />}
            </span>
            <div>
              <strong>{title}</strong>
              <small>{sub}</small>
            </div>
            {i < 3 && <ChevronRight className="step-arrow" size={16} />}
          </div>
        ))}
      </div>
      <div className="tabs" role="tablist" aria-label="Project views">
        {["Overview", "Changes", "Verification", "Source"].map((label) => (
          <button
            key={label}
            role="tab"
            aria-selected={tab === label}
            className={tab === label ? "active" : ""}
            onClick={() => setTab(label)}
          >
            {label}
            {label === "Changes" && p.patch && (
              <span>{p.patch.changes.length}</span>
            )}
            {label === "Verification" && run && (
              <span>{run.results.length}</span>
            )}
          </button>
        ))}
        <span className="tabs-aside">
          <LockKeyhole size={12} /> Source snapshot is read-only
        </span>
      </div>
      {tab === "Overview" && (
        <div className="workspace-grid">
          <div>
            <section className="panel review-panel">
              <div className="panel-title">
                <h3>
                  <Sparkles size={18} /> Your integration plan
                </h3>
                <Badge tone="green">
                  {p.patch ? "Generated" : "Ready to start"}
                </Badge>
              </div>
              <p className="muted">
                {p.patch
                  ? "A focused change, tied to this source snapshot. Review it before applying."
                  : "Inspect the accepted source and generate a reviewable patch."}
              </p>
              <ol className="plan-list">
                {(
                  p.patch?.plan ?? [
                    "Inspect the project’s routes and payment behavior.",
                    "Generate a focused patch for your chosen integration task.",
                    "Review changes and run independent verification.",
                  ]
                ).map((step, i) => (
                  <li key={step}>
                    <span>{String(i + 1).padStart(2, "0")}</span>
                    {step}
                  </li>
                ))}
              </ol>
              <div className="generation-bar">
                <select
                  aria-label="Patch generator"
                  value={mode}
                  onChange={(e) => setMode(e.target.value)}
                >
                  <option value="template">Supported template</option>
                  <option value="agent" disabled={!config.agent}>
                    OpenAI agent{!config.agent ? " · key required" : ""}
                  </option>
                </select>
                <button
                  className="button primary"
                  disabled={!!busy || running}
                  onClick={() => void act("generate")}
                >
                  {busy === "generate" ? (
                    <Loader2 size={16} className="spin" />
                  ) : (
                    <Sparkles size={16} />
                  )}{" "}
                  {p.patch ? "Regenerate patch" : "Generate patch"}
                </button>
              </div>
              {busy === "generate" && (
                <button
                  className="text-button"
                  onClick={() => void act("cancel")}
                >
                  Cancel generation
                </button>
              )}
              <p className="fine-print">
                {p.patch?.generator === "agent"
                  ? `Generated with ${p.patch.model}.`
                  : "Template generation uses deterministic source analysis; no model call."}
              </p>
            </section>
            <section className="panel findings-panel">
              <h3>What we found</h3>
              {p.inspection.findings.map((f, i) => (
                <div className="finding" key={i}>
                  <span className={`finding-dot ${f.severity}`} />
                  <div>
                    <strong>{f.title}</strong>
                    <p>{f.detail}</p>
                    <button
                      className="file-link"
                      onClick={() => {
                        setSourcePath(f.path);
                        setTab("Source");
                      }}
                    >
                      <FileCode2 size={13} />
                      {f.path} <ArrowUpRight size={12} />
                    </button>
                  </div>
                </div>
              ))}
            </section>
          </div>
          <div>
            <section className="panel decisions-panel">
              <div className="panel-title">
                <h3>Open decisions</h3>
                <span className="count-chip">
                  {p.patch?.questions.length ?? 0}
                </span>
              </div>
              <p className="muted">A little context only you can provide.</p>
              {p.patch?.questions.map((q, i) => (
                <div className="decision" key={q}>
                  <Circle size={14} />
                  <p>{q}</p>
                </div>
              ))}
              {!p.patch && (
                <p className="muted">
                  Application-specific decisions will appear with your patch.
                </p>
              )}
              <div className="decision-note">
                <CircleHelp size={14} /> Decisions remain open until addressed
                in your application.
              </div>
            </section>
            <section className="panel source-record">
              <h3>Snapshot record</h3>
              <dl>
                <dt>Uploaded</dt>
                <dd>
                  {new Date(p.createdAt).toLocaleDateString(undefined, {
                    day: "numeric",
                    month: "short",
                    year: "numeric",
                  })}
                </dd>
                <dt>SHA-256</dt>
                <dd>
                  <code>{short(p.sourceDigest)}…</code>
                  <button
                    className="icon-button"
                    aria-label="Copy source digest"
                    onClick={() => void copy(p.sourceDigest)}
                  >
                    <Copy size={13} />
                  </button>
                </dd>
                <dt>Patch version</dt>
                <dd>{p.patch ? short(p.patch.digest) : "Not generated"}</dd>
                <dt>Provider</dt>
                <dd>
                  <span className="stripe-word">stripe</span> Sandbox
                </dd>
              </dl>
            </section>
            {p.patch && (
              <section className="panel source-record reference-record">
                <h3>Documentation sources</h3>
                {p.patch.references.map((ref) => (
                  <a
                    key={ref.url}
                    href={ref.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <span>
                      {ref.title} <ArrowUpRight size={12} />
                    </span>
                    <small>
                      {ref.retrievedAt
                        ? `Retrieved ${new Date(ref.retrievedAt).toLocaleDateString()}`
                        : "Reference only · retrieval not verified"}
                    </small>
                  </a>
                ))}
              </section>
            )}
          </div>
        </div>
      )}
      {tab === "Changes" &&
        (p.patch && change ? (
          <>
            <div className="review-summary">
              <div>
                <FileDiff size={19} />
                <strong>
                  {p.patch.changes.length} changed file
                  {p.patch.changes.length !== 1 ? "s" : ""}
                </strong>
                <span className="muted">
                  Generated · execution evidence is separate
                </span>
              </div>
              <div className="segmented small">
                <button
                  className={!split ? "selected" : ""}
                  onClick={() => setSplit(false)}
                >
                  Unified
                </button>
                <button
                  className={split ? "selected" : ""}
                  onClick={() => setSplit(true)}
                >
                  Split
                </button>
              </div>
            </div>
            <div className="code-workspace">
              <aside className="file-sidebar">
                <div className="file-sidebar-label">CHANGED FILES</div>
                {p.patch.changes.map((c) => (
                  <button
                    key={c.path}
                    className={c.path === change.path ? "selected" : ""}
                    onClick={() => setSelected(c.path)}
                  >
                    <FileCode2 size={15} />
                    <span>{c.path}</span>
                    <span className="file-mark">{c.before ? "M" : "A"}</span>
                  </button>
                ))}
                <div className="file-sidebar-note">
                  <ShieldCheck size={17} />
                  <p>Your original source is preserved.</p>
                </div>
              </aside>
              <div className="diff-panel">
                <div className="diff-title">
                  <FileCode2 size={15} />
                  <strong>{change.path}</strong>
                  <span>TypeScript</span>
                </div>
                <p className="diff-reason">
                  <Sparkles size={14} />
                  {change.reason}
                </p>
                {split ? (
                  <div className="split-code">
                    <CodeBlock
                      content={change.before || "// New file"}
                      label="Original"
                    />
                    <CodeBlock content={change.after} label="Proposed" />
                  </div>
                ) : (
                  <div className="diff-code" aria-label="Unified diff">
                    {diffLines(change.before, change.after).map((part, index) =>
                      part.value
                        .replace(/\n$/, "")
                        .split("\n")
                        .map((line, i) => (
                          <div
                            className={`diff-line ${part.added ? "added" : part.removed ? "removed" : ""}`}
                            key={`${index}-${i}`}
                          >
                            <span className="diff-prefix">
                              {part.added ? "+" : part.removed ? "−" : " "}
                            </span>
                            <code>{line || " "}</code>
                          </div>
                        )),
                    )}
                  </div>
                )}
              </div>
            </div>
            <div className="review-footer">
              <LockKeyhole size={13} /> Patch bound to source{" "}
              <code>{short(p.patch.baseDigest)}</code>
              <button
                className="text-button"
                onClick={() => setTab("Verification")}
              >
                See verification evidence <ArrowRight size={15} />
              </button>
            </div>
          </>
        ) : (
          <Empty
            icon={<FileDiff />}
            title="A clearer diff starts with a plan"
            text="Generate your integration patch to review each changed file here."
            action={
              <button
                className="button primary"
                onClick={() => setTab("Overview")}
              >
                Back to the plan <ArrowRight size={16} />
              </button>
            }
          />
        ))}
      {tab === "Verification" &&
        (run ? (
          <>
            <div className="verification-heading">
              <div>
                <h2>Evidence, one check at a time.</h2>
                <p className="muted">
                  A passing syntax check never stands in for application or
                  provider verification.
                </p>
              </div>
              <div className="heading-actions">
                {p.runs.length > 1 && (
                  <select
                    aria-label="Verification run"
                    value={run.id}
                    onChange={(e) => setSelectedRun(e.target.value)}
                  >
                    {p.runs.map((r) => (
                      <option value={r.id} key={r.id}>
                        {new Date(r.startedAt).toLocaleTimeString()} ·{" "}
                        {r.status} · {short(r.patchDigest)}
                      </option>
                    ))}
                  </select>
                )}
                {running ? (
                  <button
                    className="button secondary"
                    onClick={() => void act("cancel")}
                  >
                    Cancel run
                  </button>
                ) : (
                  <button
                    className="button secondary"
                    onClick={() => void exportFile("report")}
                  >
                    <ArrowDownToLine size={16} /> Export report
                  </button>
                )}
              </div>
            </div>
            {run.patchId !== p.patch?.id && (
              <p className="callout">
                This run belongs to an earlier patch. Generate fresh evidence
                for the current changes.
              </p>
            )}
            <div className="evidence-grid">
              {[
                {
                  label: "Static analysis",
                  value:
                    run.results.find((r) => r.id === "syntax")?.status ??
                    "pending",
                  detail: "TypeScript syntax only",
                },
                {
                  label: "Isolated application",
                  value: run.local,
                  detail: "Independent local fixtures",
                },
                {
                  label: "Stripe sandbox",
                  value: run.sandbox,
                  detail: "Controlled provider adapter",
                },
              ].map((item) => (
                <div className="panel evidence-card" key={item.label}>
                  <span>{item.label}</span>
                  <strong
                    className={item.value === "passed" ? "text-green" : ""}
                  >
                    {item.value === "pending"
                      ? "Pending"
                      : item.value[0].toUpperCase() + item.value.slice(1)}
                  </strong>
                  <small>{item.detail}</small>
                </div>
              ))}
            </div>
            <div className="workspace-grid verification-grid">
              <section className="panel results-panel">
                <div className="panel-title">
                  <h3>Scenario results</h3>
                  <span className="muted">
                    {run.results.filter((r) => r.status === "passed").length}{" "}
                    passed / {run.results.length} total
                  </span>
                </div>
                {run.results.map((result) => (
                  <ScenarioRow result={result} key={result.id} />
                ))}
                {!run.results.length && (
                  <p className="muted">Checks are starting…</p>
                )}
              </section>
              <section className="panel timeline-panel">
                <h3>Run timeline</h3>
                <div className="run-identity">
                  <code>{short(run.id)}</code>
                  <Badge tone={run.status === "running" ? "blue" : "neutral"}>
                    {run.status}
                  </Badge>
                </div>
                {run.events.map((event, i) => (
                  <div className="timeline-event" key={i}>
                    <span className="timeline-dot" />
                    <div>
                      <small>{new Date(event.time).toLocaleTimeString()}</small>
                      <strong>{event.title}</strong>
                      <p>{event.detail}</p>
                    </div>
                  </div>
                ))}
                {run.status === "running" && (
                  <div className="running-label">
                    <Loader2 className="spin" size={15} /> Running checks…
                  </div>
                )}
              </section>
            </div>
            <p className="verification-disclaimer">
              <CircleHelp size={15} /> Provider adapter results verify the
              configured sandbox connection. They do not establish that the
              candidate application is production-ready.
            </p>
          </>
        ) : (
          <Empty
            icon={<ShieldCheck />}
            title="Evidence starts with a real run"
            text="Run verification to check syntax, isolated application behavior, and Stripe scenarios. Missing prerequisites will be shown clearly."
            action={
              <button
                className="button primary"
                disabled={!p.patch || !!busy}
                onClick={() => void act("verify")}
              >
                <ShieldCheck size={16} /> Run verification
              </button>
            }
          />
        ))}
      {tab === "Source" && (
        <>
          <div className="review-summary">
            <div>
              <Folder size={18} />
              <strong>{p.inspection.fileCount} original files</strong>
              <span className="muted">Immutable snapshot</span>
            </div>
            <button
              className="text-button"
              onClick={() => void copy(p.sourceDigest)}
            >
              <Copy size={14} /> Copy digest
            </button>
          </div>
          <div className="code-workspace">
            <aside className="file-sidebar">
              <div className="file-sidebar-label">SOURCE EXPLORER</div>
              {Object.keys(p.files)
                .sort()
                .map((path) => (
                  <button
                    className={sourcePath === path ? "selected" : ""}
                    key={path}
                    onClick={() => setSourcePath(path)}
                  >
                    <FileText size={14} />
                    <span>{path}</span>
                  </button>
                ))}
            </aside>
            <div className="diff-panel">
              <CodeBlock
                label={sourcePath}
                content={p.files[sourcePath] ?? ""}
              />
            </div>
          </div>
        </>
      )}
    </main>
  );
}
function CodeBlock({ content, label }: { content: string; label: string }) {
  return (
    <div className="code-block">
      <div className="code-label">{label}</div>
      <pre>
        {content.split("\n").map((line, i) => (
          <div key={i}>
            <span className="line-number">{i + 1}</span>
            <code>{line || " "}</code>
          </div>
        ))}
      </pre>
    </div>
  );
}
function ScenarioRow({ result: r }: { result: Scenario }) {
  const [open, setOpen] = useState(r.status === "blocked");
  return (
    <div className="scenario">
      <button onClick={() => setOpen(!open)} aria-expanded={open}>
        {r.status === "passed" ? (
          <CheckCircle2 className="green-icon" size={19} />
        ) : r.status === "failed" ? (
          <XCircle className="red-icon" size={19} />
        ) : (
          <CircleHelp className="amber-icon" size={19} />
        )}
        <div>
          <strong>{r.name}</strong>
          <small>{r.evidence}</small>
        </div>
        <Badge
          tone={
            r.status === "passed"
              ? "green"
              : r.status === "failed"
                ? "red"
                : "amber"
          }
        >
          {r.status}
        </Badge>
        <ChevronDown size={15} className={open ? "rotate" : ""} />
      </button>
      {open && <p className="scenario-detail">{r.detail}</p>}
    </div>
  );
}
function Documentation() {
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">A LITTLE CONTEXT GOES A LONG WAY</div>
          <h1>Your integration field guide.</h1>
          <p>Know what’s supported, what was checked, and what comes next.</p>
        </div>
      </div>
      <div className="docs-hero">
        <BookOpen size={31} />
        <div>
          <h2>Source → Plan → Patch → Evidence</h2>
          <p>
            Upload a small Node.js, TypeScript, and Express project. Choose a
            payment task, review a proposed change, then run checks. Your
            original source stays intact throughout.
          </p>
        </div>
      </div>
      <div className="docs-grid">
        {[
          {
            icon: UploadCloud,
            title: "01 / Bring your source",
            text: "Upload a ZIP with package.json at the root, or within one repository folder. Include at most 100 text files, 256 KB per file, and 2 MB in total. Exclude dependencies, credentials, and symlinks.",
          },
          {
            icon: GitPullRequest,
            title: "02 / Review every change",
            text: "Template mode repairs supported Express raw-body middleware ordering and generates payment modules. The optional OpenAI agent can inspect other supported layouts. Review unresolved decisions before applying the exported patch.",
          },
          {
            icon: ShieldCheck,
            title: "03 / Read the evidence",
            text: "Generated means a patch exists. Static analysis checks syntax. Isolated fixture results check application behavior. Stripe sandbox results describe actual provider calls by the controlled adapter. Blocked means a prerequisite is missing.",
          },
          {
            icon: ArrowDownToLine,
            title: "04 / Take it from here",
            text: "Export the unified patch and JSON report. Each identifies the source digest and patch digest. Apply the patch to the exact original source with git apply, then resolve application-specific decisions and run your own acceptance suite.",
          },
        ].map(({ icon: Icon, title, text }) => (
          <article className="panel docs-card" key={title}>
            <Icon size={22} />
            <h3>{title}</h3>
            <p>{text}</p>
          </article>
        ))}
      </div>
      <section className="panel official-docs">
        <h3>
          Go straight to the source <ArrowUpRight size={17} />
        </h3>
        <p className="muted">
          Official documentation for the supported integration flows.
        </p>
        {[
          {
            title: "Stripe webhook signatures",
            url: "https://docs.stripe.com/webhooks/signature",
            text: "Original request bytes, endpoint secrets, and signature verification.",
          },
          {
            title: "Stripe idempotent requests",
            url: "https://docs.stripe.com/api/idempotent_requests",
            text: "Safe retries and stable keys for payment operations.",
          },
          {
            title: "Payment Intents lifecycle",
            url: "https://docs.stripe.com/payments/paymentintents/lifecycle",
            text: "Payment states, additional customer action, and asynchronous completion.",
          },
        ].map((doc) => (
          <a key={doc.url} href={doc.url} target="_blank" rel="noreferrer">
            <span className="doc-icon">
              <FileText size={18} />
            </span>
            <div>
              <strong>{doc.title}</strong>
              <small>{doc.text}</small>
            </div>
            <ArrowUpRight size={18} />
          </a>
        ))}
      </section>
    </>
  );
}
function Login({
  onLogin,
  onError,
}: {
  onLogin: () => Promise<void>;
  onError: (s: string) => void;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <main className="login-page">
      <div className="panel login-card">
        <Logo />
        <h1>Welcome back.</h1>
        <p className="muted">Sign in to your integration workspace.</p>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            try {
              const result = await authClient!.auth.signInWithPassword({
                email,
                password,
              });
              if (result.error) throw result.error;
              await onLogin();
            } catch (e) {
              onError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <label className="form-label">
            Email
            <input
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label className="form-label">
            Password
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <button className="button primary full" disabled={busy}>
            {busy ? (
              <Loader2 className="spin" size={16} />
            ) : (
              <LockKeyhole size={16} />
            )}{" "}
            Sign in
          </button>
        </form>
      </div>
    </main>
  );
}
