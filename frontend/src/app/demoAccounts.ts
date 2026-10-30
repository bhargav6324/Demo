// Demo identities offered on the login page. These are shared, synthetic demo
// credentials (seeded by the mock backend and expected to be seeded by the real
// backend for the hackathon demo) — not real user passwords.
import type { Role } from "../types/models";

export interface DemoAccount {
  role: Role;
  email: string;
  password: string;
  description: string;
}

export const DEMO_ACCOUNTS: DemoAccount[] = [
  { role: "student", email: "student@demo.edu", password: "demo123", description: "Loans, holds and recommendations" },
  { role: "researcher", email: "researcher@demo.edu", password: "demo123", description: "Papers, dissertations and citations" },
  { role: "faculty", email: "faculty@demo.edu", password: "demo123", description: "Course reading and restricted archives" },
  { role: "librarian", email: "librarian@demo.edu", password: "demo123", description: "Analytics and collection demand" },
];
