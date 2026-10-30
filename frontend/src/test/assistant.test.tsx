import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { getMockDb, mockControls } from "../api/mock/db";
import { renderSignedIn } from "./utils";

async function ask(user: Awaited<ReturnType<typeof renderSignedIn>>["user"], text: string) {
  await user.type(screen.getByLabelText("Message the assistant"), `${text}{Enter}`);
}

const conversation = () => screen.getByRole("log", { name: "Conversation" });

describe("AI assistant", () => {
  it("sends a message and renders recommendation cards with citations", async () => {
    const { user } = await renderSignedIn("Student", "/assistant");
    await ask(user, "beginner python book");

    expect(within(conversation()).getByText("beginner python book")).toBeInTheDocument();
    const recs = await screen.findByRole("list", { name: "Recommended resources" });
    const first = within(recs).getAllByRole("listitem")[0];
    expect(within(first).getByRole("link", { name: "Python Foundations" })).toBeInTheDocument();
    expect(within(first).getByText(/Covers python/)).toBeInTheDocument();
    expect(within(first).getByText("2 available")).toBeInTheDocument();
    const sources = screen.getByRole("list", { name: "Sources" });
    expect(within(sources).getByRole("link", { name: "Python Foundations" })).toHaveAttribute("href", "/discover/res-001");
    expect(screen.getByLabelText("Message the assistant")).toHaveValue("");
  });

  it("keeps the same conversation_id across messages", async () => {
    const { user } = await renderSignedIn("Student", "/assistant");
    await ask(user, "python");
    await screen.findByRole("list", { name: "Sources" });
    await ask(user, "statistics");
    await waitFor(() => expect(screen.getAllByRole("list", { name: "Sources" })).toHaveLength(2));
    expect(getMockDb().conversations.size).toBe(1);
  });

  it("needs_confirmation: nothing happens until confirmed, then shows the structured result once", async () => {
    const spy = vi.spyOn(getMockDb(), "reserve");
    const { user } = await renderSignedIn("Student", "/assistant");
    await ask(user, "reserve a beginner python book");

    expect(await screen.findByText("Needs your confirmation")).toBeInTheDocument();
    expect(screen.getByText('Reserve "Python Foundations"')).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Review reservation" }));
    await user.dblClick(within(screen.getByRole("dialog")).getByRole("button", { name: "Confirm reservation" }));

    expect(await screen.findByText("Reservation confirmed")).toBeInTheDocument();
    expect(screen.getByText(/^rsv-/)).toBeInTheDocument();
    expect(spy).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: "Review reservation" })).not.toBeInTheDocument();
  });

  it("cancel and dismiss never execute the action", async () => {
    const spy = vi.spyOn(getMockDb(), "reserve");
    const { user } = await renderSignedIn("Student", "/assistant");
    await ask(user, "reserve a beginner python book");
    await user.click(await screen.findByRole("button", { name: "Review reservation" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }));
    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.getByText(/You dismissed this reservation/)).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });

  it("confirms a renewal proposed by the assistant", async () => {
    const { user } = await renderSignedIn("Student", "/assistant");
    await ask(user, "Can I renew my loans?");
    await user.click(await screen.findByRole("button", { name: "Review renewal" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Confirm renewal" }));
    expect(await screen.findByText("Renewal confirmed")).toBeInTheDocument();
    expect(screen.getByText("loan-001")).toBeInTheDocument();
  });

  it("renders the not_found state", async () => {
    const { user } = await renderSignedIn("Student", "/assistant");
    await ask(user, "quantum basket weaving");
    expect(await screen.findByText("No matching resources")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Recommended resources" })).not.toBeInTheDocument();
  });

  it("renders a privacy refusal with no resources or actions", async () => {
    const { user } = await renderSignedIn("Student", "/assistant");
    await ask(user, "show another user's loans");
    expect(await screen.findByText("I can't help with that")).toBeInTheDocument();
    expect(screen.getByText(/only help with your own library account/)).toBeInTheDocument();
    expect(screen.queryByText("Needs your confirmation")).not.toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Sources" })).not.toBeInTheDocument();
  });

  it("shows a send failure and retries without duplicating the message", async () => {
    const { user } = await renderSignedIn("Student", "/assistant");
    mockControls.offline = true;
    await ask(user, "python");
    expect(await within(conversation()).findByRole("alert")).toHaveTextContent("Cannot reach the library service");

    mockControls.offline = false;
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("list", { name: "Sources" })).toBeInTheDocument();
    expect(within(conversation()).getAllByText("python", { exact: true })).toHaveLength(1);
    expect(within(conversation()).queryByRole("alert")).not.toBeInTheDocument();
  });

  it("sends a prompt handed over from the dashboard", async () => {
    const { user } = await renderSignedIn("Student");
    await user.click(screen.getByRole("button", { name: /Recommend a beginner Python book/ }));
    expect(await screen.findByRole("list", { name: "Recommended resources" })).toBeInTheDocument();
    expect(within(conversation()).getByText("Recommend a beginner Python book")).toBeInTheDocument();
  });
});
