import { useState, type FormEvent } from "react";
import { useAuth } from "../auth";
import { ErrorNote } from "../components/ui";

const DEMO_USERS = [
  ["ap@acme.test", "Priya Patel", "AP specialist"],
  ["budget@acme.test", "Ben Okafor", "Budget owner"],
  ["approver@acme.test", "Fiona Approver", "Finance approver"],
  ["admin@acme.test", "Alex Admin", "Administrator"],
];

export function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("ap@acme.test");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login">
      <h1>Accounts Payable Exception Agent</h1>
      <p className="muted">Development sign-in. In a hosted deployment this screen is replaced by Supabase Auth.</p>
      <form onSubmit={submit} className="login-form">
        <label>
          Email
          <input value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
        </label>
        <button type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <ErrorNote error={error} />
      </form>
      <div className="demo-users">
        <p className="muted">Seeded users</p>
        {DEMO_USERS.map(([address, name, role]) => (
          <button key={address} type="button" className="link" onClick={() => setEmail(address)}>
            {name} — {role} ({address})
          </button>
        ))}
      </div>
    </main>
  );
}
