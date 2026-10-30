import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { getMockDb, mockControls } from "../api/mock/db";
import { renderSignedIn } from "./utils";

const stat = (label: string) => screen.getByTestId(`stat-${label}`);

describe("librarian analytics", () => {
  it("renders statistic cards and popular resources from AnalyticsClient", async () => {
    await renderSignedIn("Librarian", "/analytics");
    await screen.findByRole("region", { name: "Key metrics" });
    expect(stat("Total resources")).toHaveTextContent("16");
    expect(stat("Active loans")).toHaveTextContent("7");
    expect(stat("Overdue loans")).toHaveTextContent("2");
    expect(stat("Active reservations")).toHaveTextContent("5");
    expect(screen.getByText("29% of active loans")).toBeInTheDocument();
    expect(screen.getByRole("meter", { name: "Overdue share of active loans" })).toHaveAttribute("aria-valuenow", "29");

    const table = screen.getByRole("table", { name: /Popular resources/ });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(within(rows[0]).getByRole("link", { name: "Machine Learning Field Guide" })).toBeInTheDocument();
    expect(rows[0]).toHaveTextContent("52"); // 51 historical + 1 active loan
    expect(screen.getByRole("img", { name: /Bar chart of borrow counts/ })).toBeInTheDocument();
  });

  it("reflects live data on refresh — nothing is hardcoded", async () => {
    const { user } = await renderSignedIn("Librarian", "/analytics");
    await screen.findByRole("region", { name: "Key metrics" });
    const db = getMockDb();
    db.reserve(db.users.find((u) => u.user_id === "user-003")!, "res-001");
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(stat("Active reservations")).toHaveTextContent("6"));
  });

  it("is not available to students", async () => {
    await renderSignedIn("Student", "/analytics");
    expect(screen.getByText("You don't have access to this page")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Key metrics" })).not.toBeInTheDocument();
  });

  it("shows a retryable error when the service is unreachable", async () => {
    const { user } = await renderSignedIn("Librarian");
    mockControls.offline = true;
    await user.click(within(screen.getByRole("complementary", { name: "Primary" })).getByRole("link", { name: /Analytics/ }));
    expect(await screen.findByText("Connection problem")).toBeInTheDocument();
    mockControls.offline = false;
    await user.click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByRole("region", { name: "Key metrics" })).toBeInTheDocument();
  });
});
