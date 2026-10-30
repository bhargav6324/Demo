import { ShieldAlert } from "lucide-react";
import type { ReactNode } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { EmptyState } from "../components/states";
import { Button } from "../components/ui";
import type { Role } from "../types/models";
import { useAuth } from "./AuthProvider";

/** Signed-out visitors are sent to /login and returned here afterwards. */
export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const location = useLocation();
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />;
  return <>{children}</>;
}

/**
 * Hides a screen from roles that cannot use it. This is UX only: the backend
 * still enforces authorization and returns 403 regardless of what the UI shows.
 */
export function RequireRole({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { hasRole } = useAuth();
  const navigate = useNavigate();
  if (!hasRole(...roles)) {
    return (
      <EmptyState
        icon={ShieldAlert}
        title="You don't have access to this page"
        description="This area is available to library staff only. If you think this is a mistake, contact the library."
        action={
          <Button variant="secondary" onClick={() => navigate("/dashboard")}>
            Back to dashboard
          </Button>
        }
      />
    );
  }
  return <>{children}</>;
}
