import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { getMockDb, mockControls } from "../api/mock/db";
import { renderSignedIn } from "./utils";

const results = () => screen.getByRole("region", { name: "Search results" });
const cards = () => within(results()).queryAllByRole("article");

describe("catalog search", () => {
  it("searches and shows resource cards with live availability", async () => {
    const { user } = await renderSignedIn("Student", "/discover");
    await user.type(screen.getByLabelText("Search the catalog"), "python");
    await user.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByText(/results? for “python”/)).toBeInTheDocument();
    const first = cards()[0];
    expect(within(first).getByRole("link", { name: "Python Foundations" })).toBeInTheDocument();
    expect(within(first).getByText("Anita Desai, Mark Ellison")).toBeInTheDocument();
    expect(await within(first).findByText("2 available")).toBeInTheDocument();
  });

  it("filters by type and level", async () => {
    const { user } = await renderSignedIn("Student", "/discover");
    await screen.findByText(/^\d+ results?$/);
    const allCount = cards().length;

    await user.click(within(screen.getByRole("group", { name: "Filter by resource type" })).getByRole("button", { name: "Book" }));
    await user.click(within(screen.getByRole("group", { name: "Filter by level" })).getByRole("button", { name: "Beginner" }));

    await waitFor(() => expect(cards().length).toBeLessThan(allCount));
    expect(screen.getByRole("button", { name: "Book", pressed: true })).toBeInTheDocument();
    for (const card of cards()) {
      expect(within(card).getByText("Book")).toBeInTheDocument();
      expect(within(card).getByText("Beginner")).toBeInTheDocument();
    }
  });

  it("shows an empty state when nothing matches", async () => {
    const { user } = await renderSignedIn("Student", "/discover?q=quantum%20basket%20weaving");
    expect(await screen.findByText("No resources match your search")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Clear search and filters" }));
    await waitFor(() => expect(cards().length).toBeGreaterThan(0));
  });

  it("shows a retryable error on network failure", async () => {
    const { user } = await renderSignedIn("Student");
    mockControls.offline = true;
    await user.click(screen.getByRole("link", { name: "Discover" }));
    expect(await screen.findByText("Connection problem")).toBeInTheDocument();
    mockControls.offline = false;
    await user.click(screen.getByRole("button", { name: /try again/i }));
    await waitFor(() => expect(cards().length).toBeGreaterThan(0));
  });
});

describe("resource detail", () => {
  it("shows metadata, branch and shelf locations", async () => {
    await renderSignedIn("Student", "/discover/res-001");
    expect(await screen.findByRole("heading", { level: 1, name: "Python Foundations" })).toBeInTheDocument();
    const panel = screen.getByRole("complementary", { name: "Availability" });
    expect(await within(panel).findByText("Central Library")).toBeInTheDocument();
    expect(within(panel).getByText("Shelf CS-A1")).toBeInTheDocument();
    expect(within(panel).getByText("Engineering Library")).toBeInTheDocument();
    expect(screen.getByText(/Chapter 1 — Getting started/)).toBeInTheDocument(); // content preview
  });

  it("reports restricted resources as not found", async () => {
    await renderSignedIn("Student", "/discover/res-016");
    expect(await screen.findByText("Resource not found")).toBeInTheDocument();
  });

  it("shows online access for digital resources instead of a reserve button", async () => {
    await renderSignedIn("Student", "/discover/res-011");
    expect(await screen.findByText("Online access")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: /Open online/ })).toHaveAttribute("href", "https://library.example.edu/ocw/linear-algebra");
    expect(screen.queryByRole("button", { name: /Reserve|waitlist/i })).not.toBeInTheDocument();
  });
});

describe("reservation", () => {
  it("cancelling the dialog does not reserve", async () => {
    const spy = vi.spyOn(getMockDb(), "reserve");
    const { user } = await renderSignedIn("Student", "/discover/res-001");
    await user.click(await screen.findByRole("button", { name: "Reserve a copy" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });

  it("confirms, reserves once, and refreshes availability", async () => {
    const spy = vi.spyOn(getMockDb(), "reserve");
    const { user } = await renderSignedIn("Student", "/discover/res-001");
    const panel = screen.getByRole("complementary", { name: "Availability" });
    expect(await within(panel).findByText("2 available")).toBeInTheDocument();

    await user.click(within(panel).getByRole("button", { name: "Reserve a copy" }));
    const dialog = screen.getByRole("dialog", { name: "Reserve this title?" });
    const confirm = within(dialog).getByRole("button", { name: "Confirm reservation" });
    await user.dblClick(confirm); // duplicate clicks must not send twice

    expect(await screen.findByText(/Reserved “Python Foundations”/)).toBeInTheDocument();
    expect(spy).toHaveBeenCalledTimes(1);
    expect(await within(panel).findByText("1 available")).toBeInTheDocument();
  });

  it("shows the conflict message when the title is already reserved", async () => {
    const { user } = await renderSignedIn("Student", "/discover/res-002"); // user-001 already holds rsv-004
    await user.click(await screen.findByRole("button", { name: "Reserve a copy" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Confirm reservation" }));
    expect(await screen.findByText("You already have an active reservation for this title.")).toBeInTheDocument();
  });

  it("joins the waitlist when no copy is free", async () => {
    const { user } = await renderSignedIn("Researcher", "/discover/res-010");
    await user.click(await screen.findByRole("button", { name: "Join waitlist" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Join waitlist" }));
    expect(await screen.findByText(/Added to the waitlist for “Database Systems Essentials” — position 3/)).toBeInTheDocument();
  });
});

describe("dashboard", () => {
  it("shows borrowing overview, picks and routes searches to Discover", async () => {
    const { user } = await renderSignedIn("Student");
    expect(screen.getByRole("heading", { level: 1, name: "Welcome back, Aarav" })).toBeInTheDocument();
    const overview = screen.getByRole("region", { name: "Borrowing overview" });
    expect(await within(overview).findByText("On loan")).toBeInTheDocument();
    expect(within(overview).getByText("Overdue").previousElementSibling).toHaveTextContent("1");
    expect(screen.getByText("Picked for your interests")).toBeInTheDocument();
    expect((await within(screen.getByRole("region", { name: "Picked for your interests" })).findAllByRole("article")).length).toBeGreaterThan(0);

    await user.type(screen.getByLabelText("Search the catalog"), "statistics");
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText(/results? for “statistics”/)).toBeInTheDocument();
  });
});
