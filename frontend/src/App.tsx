import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./app/AuthProvider";
import { ProtectedRoute, RequireRole } from "./app/guards";
import { lazy, Suspense } from "react";
import { AppLayout } from "./components/layout/AppLayout";
import { LoadingSkeleton } from "./components/states";
import { AssistantPage } from "./pages/AssistantPage";
import { DashboardPage } from "./pages/DashboardPage";
import { MyLibraryPage } from "./pages/MyLibraryPage";
import { DiscoverPage } from "./pages/DiscoverPage";
import { LoginPage } from "./pages/LoginPage";
import { ResourceDetailPage } from "./pages/ResourceDetailPage";

// Charts (Recharts) are only needed by librarians, so load that page on demand.
const AnalyticsPage = lazy(() => import("./pages/AnalyticsPage").then((m) => ({ default: m.AnalyticsPage })));

function ProtectedShell() {
  const { user, logout, sessionKey } = useAuth();
  return (
    <ProtectedRoute>
      {/* Keyed by session so no page state survives a change of identity. */}
      <AppLayout key={sessionKey} user={user} onSignOut={logout} />
    </ProtectedRoute>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedShell />}>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/discover" element={<DiscoverPage />} />
        <Route path="/discover/:resourceId" element={<ResourceDetailPage />} />
        <Route path="/assistant" element={<AssistantPage />} />
        <Route path="/my-library" element={<MyLibraryPage />} />
        <Route
          path="/analytics"
          element={
            <RequireRole roles={["librarian"]}>
              <Suspense fallback={<LoadingSkeleton lines={6} className="pt-4" />}>
                <AnalyticsPage />
              </Suspense>
            </RequireRole>
          }
        />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
    </Routes>
  );
}
