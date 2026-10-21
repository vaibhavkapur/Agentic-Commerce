import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, getToken, setToken } from "./api";
import type { OrganizationMembership, User } from "./types";

interface AuthState {
  user: User | null;
  organizations: OrganizationMembership[];
  org: OrganizationMembership | null;
  loading: boolean;
  login: (email: string) => Promise<void>;
  logout: () => void;
  selectOrg: (id: string) => void;
}

const AuthContext = createContext<AuthState | null>(null);
const ORG_KEY = "ap.org";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [organizations, setOrganizations] = useState<OrganizationMembership[]>([]);
  const [orgId, setOrgId] = useState<string | null>(localStorage.getItem(ORG_KEY));
  const [loading, setLoading] = useState<boolean>(Boolean(getToken()));

  const load = useCallback(async () => {
    if (!getToken()) {
      setLoading(false);
      return;
    }
    try {
      const me = await api.me();
      setUser(me.user);
      setOrganizations(me.organizations);
      if (!me.organizations.some((o) => o.id === orgId)) {
        const first = me.organizations[0]?.id ?? null;
        setOrgId(first);
        if (first) localStorage.setItem(ORG_KEY, first);
      }
    } catch {
      setToken(null);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, [orgId]);

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      organizations,
      org: organizations.find((o) => o.id === orgId) ?? null,
      loading,
      login: async (email: string) => {
        const result = await api.devLogin(email);
        setToken(result.access_token);
        setLoading(true);
        await load();
      },
      logout: () => {
        setToken(null);
        setUser(null);
        setOrganizations([]);
      },
      selectOrg: (id: string) => {
        setOrgId(id);
        localStorage.setItem(ORG_KEY, id);
      },
    }),
    [user, organizations, orgId, loading, load],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
