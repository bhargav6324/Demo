// Creates the five API clients once and exposes them to pages via useApi().
// The token lives in a ref owned here (memory only); the auth layer sets it.
import { createContext, useContext, useMemo, useRef, type ReactNode } from "react";
import { createApiClients, type ApiClients } from "../api";

interface ApiContextValue {
  clients: ApiClients;
  setToken(token: string | null): void;
  setUnauthorizedHandler(handler: (() => void) | null): void;
}

const ApiContext = createContext<ApiContextValue | null>(null);

export function ApiProvider({ children, clients: injected }: { children: ReactNode; clients?: ApiClients }) {
  const tokenRef = useRef<string | null>(null);
  const unauthorizedRef = useRef<(() => void) | null>(null);

  const value = useMemo<ApiContextValue>(() => {
    const clients =
      injected ??
      createApiClients({
        getToken: () => tokenRef.current,
        onUnauthorized: () => unauthorizedRef.current?.(),
      });
    return {
      clients,
      setToken: (token) => {
        tokenRef.current = token;
      },
      setUnauthorizedHandler: (handler) => {
        unauthorizedRef.current = handler;
      },
    };
  }, [injected]);

  return <ApiContext.Provider value={value}>{children}</ApiContext.Provider>;
}

function useApiContext() {
  const ctx = useContext(ApiContext);
  if (!ctx) throw new Error("useApi must be used inside ApiProvider");
  return ctx;
}

/** Pages and components use this — never fetch/axios directly. */
export function useApi(): ApiClients {
  return useApiContext().clients;
}

/** For the auth layer only. */
export function useApiSession() {
  const { setToken, setUnauthorizedHandler } = useApiContext();
  return { setToken, setUnauthorizedHandler };
}
