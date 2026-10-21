import { BrowserRouter, Link, NavLink, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import { ApprovalsPage } from "./pages/ApprovalsPage";
import { CasePage } from "./pages/CasePage";
import { InboxPage } from "./pages/InboxPage";
import { LoginPage } from "./pages/LoginPage";
import { VendorsPage } from "./pages/VendorsPage";

function Shell() {
  const { user, organizations, org, selectOrg, logout, loading } = useAuth();
  if (loading) return <p className="muted empty">Loading…</p>;
  if (!user) return <LoginPage />;
  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">
          AP Exception Agent
        </Link>
        <nav>
          <NavLink to="/" end>
            Inbox
          </NavLink>
          <NavLink to="/approvals">Approvals</NavLink>
          <NavLink to="/vendors">Vendors &amp; members</NavLink>
        </nav>
        <div className="spacer" />
        {organizations.length > 1 ? (
          <select value={org?.id ?? ""} onChange={(e) => selectOrg(e.target.value)}>
            {organizations.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </select>
        ) : (
          <span className="muted">{org?.name}</span>
        )}
        <span className="user">
          {user.display_name} <span className="badge status">{org?.role.replaceAll("_", " ")}</span>
        </span>
        <button type="button" className="secondary small" onClick={logout}>
          Sign out
        </button>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<InboxPage />} />
          <Route path="/cases/:caseId" element={<CasePage />} />
          <Route path="/approvals" element={<ApprovalsPage />} />
          <Route path="/vendors" element={<VendorsPage />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Shell />
      </AuthProvider>
    </BrowserRouter>
  );
}
