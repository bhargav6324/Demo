import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ApiError } from "../api";
import { ErrorState } from "../components/states";
import { renderSignedIn } from "./utils";

describe("app shell", () => {
  it("renders navigation and the mock-mode indicator", async () => {
    await renderSignedIn("Student");
    const nav = screen.getByRole("complementary", { name: "Primary" });
    for (const label of ["Dashboard", "Discover", "AI Assistant", "My Library"]) {
      expect(nav).toHaveTextContent(label);
    }
    expect(screen.getByText("Mock data")).toBeInTheDocument();
  });

  it("navigates between routes", async () => {
    const { user } = await renderSignedIn("Student");
    await user.click(screen.getByRole("link", { name: /AI Assistant/ }));
    expect(screen.getByRole("heading", { level: 1, name: "AI Assistant" })).toBeInTheDocument();
  });

  it("redirects unknown paths to the dashboard", async () => {
    await renderSignedIn("Student", "/nope");
    expect(await screen.findByRole("heading", { level: 1, name: /Welcome back/ })).toBeInTheDocument();
  });
});

describe("ErrorState", () => {
  it("shows message, trace id and a retry button for transient errors only", async () => {
    let retried = 0;
    const { rerender } = render(<ErrorState error={new ApiError("network_error", "Cannot reach the service.")} onRetry={() => retried++} />);
    expect(screen.getByText("Connection problem")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(retried).toBe(1);

    rerender(<ErrorState error={new ApiError("forbidden", "Librarians only.", 403, "tr-123")} onRetry={() => retried++} />);
    expect(screen.getByText("Access denied")).toBeInTheDocument();
    expect(screen.getByText("tr-123")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /try again/i })).not.toBeInTheDocument();
  });
});
