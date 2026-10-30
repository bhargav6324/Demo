// Authentication state. The token lives only in memory (via ApiProvider's ref):
// never in localStorage, URLs or logs. A browser refresh requires signing in again.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import type { Role, User } from "../types/models";
import { useApi, useApiSession } from "./ApiProvider";
import { useClearToasts, useToast } from "./ToastProvider";

interface AuthState {
  user: User | null;
  /** Changes on every sign-in so identity-scoped page state remounts from scratch. */
  sessionKey: number;
}

interface AuthContextValue extends AuthState {
  login(email: string, password: string): Promise<User>;
  logout(): void;
  hasRole(...roles: Role[]): boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const { auth } = useApi();
  const { setToken, setUnauthorizedHandler } = useApiSession();
  const toast = useToast();
  const navigate = useNavigate();
  const location = useLocation();
  const [state, setState] = useState<AuthState>({ user: null, sessionKey: 0 });

  const clearToasts = useClearToasts();

  const clear = useCallback(() => {
    setToken(null);
    clearToasts();
    setState((s) => ({ user: null, sessionKey: s.sessionKey + 1 }));
  }, [setToken, clearToasts]);

  const login = useCallback(
    async (email: string, password: string) => {
      // Drop any previous identity before authenticating the next one.
      clear();
      const result = await auth.login(email, password);
      setToken(result.access_token);
      setState((s) => ({ user: result.user, sessionKey: s.sessionKey + 1 }));
      return result.user;
    },
    [auth, clear, setToken],
  );

  const logout = useCallback(() => {
    clear();
    toast("info", "You have been signed out.");
    navigate("/login", { replace: true });
  }, [clear, navigate, toast]);

  // Any 401 from any client ends the session and returns to the login page.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      clear();
      toast("warning", "Your session has expired. Please sign in again.");
      navigate("/login", { replace: true, state: { from: location } });
    });
    return () => setUnauthorizedHandler(null);
  }, [clear, location, navigate, setUnauthorizedHandler, toast]);

  const hasRole = useCallback((...roles: Role[]) => !!state.user && roles.includes(state.user.role), [state.user]);

  const value = useMemo(() => ({ ...state, login, logout, hasRole }), [state, login, logout, hasRole]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

/** For screens rendered behind ProtectedRoute. */
export function useCurrentUser(): User {
  const { user } = useAuth();
  if (!user) throw new Error("useCurrentUser requires a signed-in user");
  return user;
}
