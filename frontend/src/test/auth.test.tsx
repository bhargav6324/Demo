import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { getMockDb } from "../api/mock/db";
import { useApi } from "../app/ApiProvider";
import { loginWithForm, renderApp, renderSignedIn } from "./utils";

const sidebar = () => screen.getByRole("complementary", { name: "Primary" });

describe("login", () => {
  it("student signs in with the form and lands on the dashboard without librarian pages", async () => {
    const { user } = renderApp("/login");
    await loginWithForm(user, "student@demo.edu");
    expect(await screen.findByRole("heading", { level: 1, name: /Welcome back/ })).toBeInTheDocument();
    expect(within(sidebar()).getByText("Aarav Sharma")).toBeInTheDocument();
    expect(within(sidebar()).queryByRole("link", { name: /Analytics/ })).not.toBeInTheDocument();
  });

  it("librarian sees the Analytics page", async () => {
    const { user } = await renderSignedIn("Librarian");
    await user.click(within(sidebar()).getByRole("link", { name: /Analytics/ }));
    expect(await screen.findByRole("heading", { level: 1, name: "Analytics" })).toBeInTheDocument();
  });

  it.each(["Researcher", "Faculty"] as const)("%s gets member navigation only", async (role) => {
    await renderSignedIn(role);
    expect(within(sidebar()).getByText(role)).toBeInTheDocument();
    expect(within(sidebar()).queryByRole("link", { name: /Analytics/ })).not.toBeInTheDocument();
  });

  it("shows an error for invalid credentials and stays signed out", async () => {
    const { user } = renderApp("/login");
    await loginWithForm(user, "student@demo.edu", "wrong-password");
    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect email or password.");
    expect(screen.getByLabelText("Password")).toHaveValue("");
    expect(screen.queryByRole("complementary", { name: "Primary" })).not.toBeInTheDocument();
  });

  it("validates empty and malformed fields before calling the API", async () => {
    const { user } = renderApp("/login");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(screen.getByText("Enter your university email.")).toBeInTheDocument();
    expect(screen.getByText("Enter your password.")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Email"), "not-an-email");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(screen.getByText("Enter a valid email address.")).toBeInTheDocument();
  });
});

describe("protected routes", () => {
  it("redirects to login and returns to the requested page afterwards", async () => {
    const { user } = renderApp("/my-library");
    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    await loginWithForm(user, "student@demo.edu");
    expect(await screen.findByRole("heading", { level: 1, name: "My Library" })).toBeInTheDocument();
  });

  it("shows access denied when a student opens /analytics directly", async () => {
    await renderSignedIn("Student", "/analytics");
    expect(screen.getByText("You don't have access to this page")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1, name: "Analytics" })).not.toBeInTheDocument();
  });

  it("logout clears the session and protects routes again", async () => {
    const { user } = await renderSignedIn("Student");
    await user.click(screen.getByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByText("You have been signed out.")).toBeInTheDocument();
  });

  it("switching identity starts a clean session", async () => {
    const { user } = await renderSignedIn("Librarian");
    await user.click(screen.getByRole("button", { name: "Sign out" }));
    await user.click(await screen.findByRole("button", { name: "Sign in as demo Student" }));
    await screen.findByRole("complementary", { name: "Primary" });
    expect(within(sidebar()).getByText("Aarav Sharma")).toBeInTheDocument();
    expect(within(sidebar()).queryByText("Nisha Verma")).not.toBeInTheDocument();
    expect(screen.queryByText(/Nisha Verma/)).not.toBeInTheDocument(); // no leftover toast either
    expect(within(sidebar()).queryByRole("link", { name: /Analytics/ })).not.toBeInTheDocument();
  });
});

/** Test-only control that makes an authenticated call through the app's own clients. */
function AuthenticatedCallProbe() {
  const api = useApi();
  return (
    <button type="button" onClick={() => api.auth.me().catch(() => undefined)}>
      probe
    </button>
  );
}

describe("401 handling", () => {
  it("clears auth state and returns to login when the session expires", async () => {
    const { user } = renderApp("/login", <AuthenticatedCallProbe />);
    await user.click(screen.getByRole("button", { name: "Sign in as demo Student" }));
    await screen.findByRole("complementary", { name: "Primary" });

    getMockDb().sessions.clear(); // server-side expiry
    await user.click(screen.getByRole("button", { name: "probe" }));

    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByText("Your session has expired. Please sign in again.")).toBeInTheDocument();
    expect(screen.queryByRole("complementary", { name: "Primary" })).not.toBeInTheDocument();
  });
});
