// Display formatting only — never used to compute official fines or eligibility.
const DAY = 86_400_000;

export function formatDate(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

/** Whole calendar days from now until `iso` (negative when in the past). */
export function daysUntil(iso: string, now = Date.now()) {
  const startOfToday = new Date(now).setHours(0, 0, 0, 0);
  const target = new Date(iso).setHours(0, 0, 0, 0);
  return Math.round((target - startOfToday) / DAY);
}

export function relativeDue(iso: string, now = Date.now()) {
  const days = daysUntil(iso, now);
  if (days < 0) return `${Math.abs(days)} day${days === -1 ? "" : "s"} overdue`;
  if (days === 0) return "Due today";
  if (days === 1) return "Due tomorrow";
  return `Due in ${days} days`;
}

const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });

export function formatINR(amount: number) {
  return inr.format(amount);
}

export function plural(n: number, word: string, pluralWord = `${word}s`) {
  return `${n} ${n === 1 ? word : pluralWord}`;
}
