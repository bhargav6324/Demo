import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import App from "../App";
import { ApiProvider } from "../app/ApiProvider";
import { AuthProvider } from "../app/AuthProvider";
import { ROUTER_FUTURE } from "../app/nav";
import { ToastProvider } from "../app/ToastProvider";

/** Render the full app (mock clients) at a route. */
export function renderApp(path = "/dashboard", extra?: ReactNode) {
  const user = userEvent.setup();
  const utils = render(
    <MemoryRouter initialEntries={[path]} future={ROUTER_FUTURE}>
      <ToastProvider>
        <ApiProvider>
          <AuthProvider>
            <App />
            {extra}
          </AuthProvider>
        </ApiProvider>
      </ToastProvider>
    </MemoryRouter>,
  );
  return { user, ...utils };
}

export async function loginWithForm(user: ReturnType<typeof userEvent.setup>, email: string, password = "demo123") {
  await user.type(screen.getByLabelText("Email"), email);
  await user.type(screen.getByLabelText("Password"), password);
  await user.click(screen.getByRole("button", { name: "Sign in" }));
}

/** Render the app and sign in via a demo button; resolves once the shell is shown. */
export async function renderSignedIn(role: "Student" | "Researcher" | "Faculty" | "Librarian", path = "/dashboard") {
  const utils = renderApp(path);
  await utils.user.click(screen.getByRole("button", { name: `Sign in as demo ${role}` }));
  await screen.findByRole("complementary", { name: "Primary" });
  return utils;
}
