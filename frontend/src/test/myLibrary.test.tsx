import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { getMockDb, mockControls } from "../api/mock/db";
import { renderSignedIn } from "./utils";

const loanCard = (title: string) => screen.getByRole("article", { name: title });

describe("My Library — loans", () => {
  it("lists loans with due dates, fines and renewability", async () => {
    await renderSignedIn("Student", "/my-library");
    await screen.findByRole("article", { name: "Deep Learning Systems" });

    const overdue = loanCard("Deep Learning Systems");
    expect(within(overdue).getByText("Overdue")).toBeInTheDocument();
    expect(within(overdue).getByText("Fine ₹60.00")).toBeInTheDocument();
    expect(within(overdue).getByText("Not eligible for renewal")).toBeInTheDocument();
    expect(within(overdue).getByRole("button", { name: /Renew/ })).toBeDisabled();

    const eligible = loanCard("Natural Language Processing in Practice");
    expect(within(eligible).getByText("Eligible for renewal")).toBeInTheDocument();
    expect(within(eligible).getByRole("button", { name: /Renew/ })).toBeEnabled();

    expect(screen.getByText("1 overdue item")).toBeInTheDocument();
  });

  it("renews after confirmation, once, and refreshes the loan", async () => {
    const spy = vi.spyOn(getMockDb(), "renew");
    const { user } = await renderSignedIn("Student", "/my-library");
    const card = await screen.findByRole("article", { name: "Natural Language Processing in Practice" });

    await user.click(within(card).getByRole("button", { name: /Renew/ }));
    await user.dblClick(within(screen.getByRole("dialog", { name: "Renew this loan?" })).getByRole("button", { name: "Confirm renewal" }));

    expect(await screen.findByText(/Renewed “Natural Language Processing in Practice”\. New due date:/)).toBeInTheDocument();
    expect(spy).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(within(loanCard("Natural Language Processing in Practice")).getByText("Not eligible for renewal")).toBeInTheDocument());
  });

  it("shows the server's conflict message and refreshes when renewal is refused", async () => {
    const { user } = await renderSignedIn("Student", "/my-library");
    const card = await screen.findByRole("article", { name: "Natural Language Processing in Practice" });
    await user.click(within(card).getByRole("button", { name: /Renew/ }));

    // Another member reserves the title before the student confirms.
    const db = getMockDb();
    db.reserve(db.users.find((u) => u.user_id === "user-002")!, "res-012");

    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Confirm renewal" }));
    expect(await screen.findByText("Another member is waiting for this title, so it cannot be renewed.")).toBeInTheDocument();
    await waitFor(() => expect(within(loanCard("Natural Language Processing in Practice")).getByText("Not eligible for renewal")).toBeInTheDocument());
  });
});

describe("My Library — reservations", () => {
  it("lists reservations with resolved titles, status and queue position", async () => {
    await renderSignedIn("Student", "/my-library");
    const queued = await screen.findByLabelText("Database Systems Essentials");
    expect(within(queued).getByText("On waitlist")).toBeInTheDocument();
    expect(within(queued).getByText("#1 in queue")).toBeInTheDocument();
    const ready = screen.getByLabelText("Data Science from First Principles");
    expect(within(ready).getByText("Ready for pickup")).toBeInTheDocument();
    expect(screen.getByText("1 reservation ready for pickup")).toBeInTheDocument();
  });

  it("shows empty states when the user has no loans or reservations", async () => {
    await renderSignedIn("Librarian", "/my-library");
    expect(await screen.findByText("You have nothing on loan")).toBeInTheDocument();
    expect(await screen.findByText("No reservations")).toBeInTheDocument();
  });

  it("shows retryable errors when the service is unreachable", async () => {
    const { user } = await renderSignedIn("Student");
    mockControls.offline = true;
    await user.click(within(screen.getByRole("complementary", { name: "Primary" })).getByRole("link", { name: "My Library" }));
    expect(await screen.findAllByText("Connection problem")).toHaveLength(2);
    mockControls.offline = false;
    await user.click(screen.getAllByRole("button", { name: /try again/i })[0]);
    expect(await screen.findByRole("article", { name: "Deep Learning Systems" })).toBeInTheDocument();
  });
});
