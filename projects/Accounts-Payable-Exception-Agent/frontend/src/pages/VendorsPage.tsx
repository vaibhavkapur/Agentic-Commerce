import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { Empty, ErrorNote, Panel, ProvenanceBadge, StatusBadge, formatDate } from "../components/ui";
import type { Member, Vendor } from "../types";

export function VendorsPage() {
  const { org } = useAuth();
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [vendorForm, setVendorForm] = useState({ vendor_code: "", name: "", tax_id: "" });
  const [memberForm, setMemberForm] = useState({ email: "", display_name: "", role: "ap_specialist" });
  const isAdmin = org?.role === "admin";

  const load = useCallback(async () => {
    if (!org) return;
    try {
      const [v, m] = await Promise.all([api.vendors(org.id), api.members(org.id)]);
      setVendors(v);
      setMembers(m);
      setError(null);
    } catch (err) {
      setError(err);
    }
  }, [org]);

  useEffect(() => {
    void load();
  }, [load]);

  async function createVendor(event: FormEvent) {
    event.preventDefault();
    if (!org) return;
    try {
      await api.createVendor(org.id, { ...vendorForm, tax_id: vendorForm.tax_id || null });
      setVendorForm({ vendor_code: "", name: "", tax_id: "" });
      await load();
    } catch (err) {
      setError(err);
    }
  }

  async function addMember(event: FormEvent) {
    event.preventDefault();
    if (!org) return;
    try {
      await api.addMember(org.id, { ...memberForm, display_name: memberForm.display_name || undefined });
      setMemberForm({ email: "", display_name: "", role: "ap_specialist" });
      await load();
    } catch (err) {
      setError(err);
    }
  }

  if (!org) return <Empty>Select an organization.</Empty>;
  return (
    <div className="grid two wide-left">
      <Panel
        title="Approved vendor register"
        actions={
          isAdmin && (
            <form onSubmit={createVendor} className="inline-form">
              <input placeholder="Vendor code" value={vendorForm.vendor_code} onChange={(e) => setVendorForm({ ...vendorForm, vendor_code: e.target.value })} required />
              <input placeholder="Legal name" value={vendorForm.name} onChange={(e) => setVendorForm({ ...vendorForm, name: e.target.value })} required />
              <input placeholder="Tax ID" value={vendorForm.tax_id} onChange={(e) => setVendorForm({ ...vendorForm, tax_id: e.target.value })} />
              <button type="submit">Add vendor</button>
            </form>
          )
        }
      >
        <ErrorNote error={error} />
        <p className="muted small">
          <ProvenanceBadge kind="register" compact /> Beneficiary details here are the only ones the system will ever pay. Bank details printed on invoices never update this register.
        </p>
        {vendors.length === 0 ? <Empty>No vendors.</Empty> : vendors.map((v) => <VendorCard key={v.id} vendor={v} org={org.id} isAdmin={isAdmin} onChanged={() => void load()} />)}
      </Panel>
      <Panel
        title="Members"
        actions={
          isAdmin && (
            <form onSubmit={addMember} className="inline-form">
              <input placeholder="email" value={memberForm.email} onChange={(e) => setMemberForm({ ...memberForm, email: e.target.value })} required />
              <select value={memberForm.role} onChange={(e) => setMemberForm({ ...memberForm, role: e.target.value })}>
                <option value="ap_specialist">AP specialist</option>
                <option value="budget_owner">Budget owner</option>
                <option value="approver">Approver</option>
                <option value="admin">Administrator</option>
              </select>
              <button type="submit">Add</button>
            </form>
          )
        }
      >
        <ul className="list">
          {members.map((m) => (
            <li key={m.id}>
              <strong>{m.user.display_name}</strong> <span className="muted small">{m.user.email}</span> <StatusBadge status={m.role} />
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}

function VendorCard({ vendor, org, isAdmin, onChanged }: { vendor: Vendor; org: string; isAdmin: boolean; onChanged: () => void }) {
  const [form, setForm] = useState({ account_name: vendor.name, sort_code: "", account_number: "", iban: "", note: "" });
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function addVersion(event: FormEvent) {
    event.preventDefault();
    try {
      await api.addBeneficiary(org, vendor.id, { ...form, verified: false });
      setOpen(false);
      onChanged();
    } catch (err) {
      setError(err);
    }
  }

  async function verify(id: string) {
    const note = window.prompt("Describe the verification performed (e.g. call-back to a registered contact):");
    if (!note) return;
    try {
      await api.verifyBeneficiary(org, vendor.id, id, note);
      onChanged();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <article className="vendor">
      <header>
        <strong>{vendor.name}</strong> <code>{vendor.vendor_code}</code> <span className="muted small">version {vendor.version}</span>
        {isAdmin && (
          <button type="button" className="secondary small" onClick={() => setOpen(!open)}>
            New beneficiary version
          </button>
        )}
      </header>
      <ErrorNote error={error} />
      {open && (
        <form onSubmit={addVersion} className="stack small-gap">
          <input placeholder="Account name" value={form.account_name} onChange={(e) => setForm({ ...form, account_name: e.target.value })} required />
          <div className="inline-form">
            <input placeholder="Sort code" value={form.sort_code} onChange={(e) => setForm({ ...form, sort_code: e.target.value })} />
            <input placeholder="Account number" value={form.account_number} onChange={(e) => setForm({ ...form, account_number: e.target.value })} />
            <input placeholder="IBAN" value={form.iban} onChange={(e) => setForm({ ...form, iban: e.target.value })} />
          </div>
          <input placeholder="Source of the change (recorded)" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
          <div>
            <button type="submit">Record (unverified)</button>
          </div>
        </form>
      )}
      <table className="table compact">
        <thead>
          <tr>
            <th>v</th>
            <th>Account</th>
            <th>Status</th>
            <th>Verified</th>
            {isAdmin && <th />}
          </tr>
        </thead>
        <tbody>
          {vendor.beneficiaries.map((b) => (
            <tr key={b.id} className={b.is_current ? "current" : ""}>
              <td>
                {b.version}
                {b.is_current && <span className="badge">current</span>}
              </td>
              <td>
                {b.account_name}
                <div className="muted small">
                  {b.sort_code ?? ""} {b.account_number ?? ""} {b.iban ?? ""}
                </div>
              </td>
              <td>
                <StatusBadge status={b.verification_status} />
              </td>
              <td className="muted small">
                {b.verified_at ? formatDate(b.verified_at) : "—"}
                {b.verification_note && <div>{b.verification_note}</div>}
              </td>
              {isAdmin && (
                <td>
                  {b.verification_status !== "verified" && (
                    <button type="button" className="secondary small" onClick={() => void verify(b.id)}>
                      Mark verified
                    </button>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </article>
  );
}
