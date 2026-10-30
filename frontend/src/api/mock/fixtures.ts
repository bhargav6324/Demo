// Seed data for mock mode. Imported ONLY by the mock clients — never by pages
// or components. IDs are stable so tests and demos can reference them.
import type { Resource, Role } from "../../types/models";

export const DEMO_PASSWORD = "demo123";

export interface SeedUser {
  user_id: string;
  name: string;
  email: string;
  role: Role;
  courses: string[];
  interests: string[];
}

export const SEED_USERS: SeedUser[] = [
  {
    user_id: "user-001",
    name: "Aarav Sharma",
    email: "student@demo.edu",
    role: "student",
    courses: ["Data Science", "Introduction to Programming"],
    interests: ["machine learning", "python"],
  },
  {
    user_id: "user-002",
    name: "Dr. Kavya Rao",
    email: "researcher@demo.edu",
    role: "researcher",
    courses: [],
    interests: ["retrieval-augmented generation", "nlp"],
  },
  {
    user_id: "user-003",
    name: "Prof. Rahul Menon",
    email: "faculty@demo.edu",
    role: "faculty",
    courses: ["Database Systems"],
    interests: ["databases", "research methods"],
  },
  {
    user_id: "user-004",
    name: "Nisha Verma",
    email: "librarian@demo.edu",
    role: "librarian",
    courses: [],
    interests: ["collection development"],
  },
  {
    user_id: "user-005",
    name: "Meera Iyer",
    email: "student2@demo.edu",
    role: "student",
    courses: ["Database Systems"],
    interests: ["sql"],
  },
];

export const SEED_RESOURCES: Resource[] = [
  {
    resource_id: "res-001",
    title: "Python Foundations",
    authors: ["Anita Desai", "Mark Ellison"],
    type: "book",
    description: "A gentle, hands-on introduction to programming with Python: variables, control flow, functions and small projects.",
    topics: ["python", "programming"],
    level: "beginner",
    access_level: "open",
    updated_at: "2026-09-12T10:00:00Z",
  },
  {
    resource_id: "res-002",
    title: "Data Science from First Principles",
    authors: ["Joel Grant"],
    type: "book",
    description: "Builds core data science techniques — statistics, visualisation and simple models — from the ground up in Python.",
    topics: ["data science", "statistics", "python"],
    level: "intermediate",
    access_level: "open",
    updated_at: "2026-08-02T10:00:00Z",
  },
  {
    resource_id: "res-003",
    title: "Machine Learning Field Guide",
    authors: ["Priya Natarajan"],
    type: "book",
    description: "Practical guide to supervised and unsupervised learning, model evaluation and common pitfalls.",
    topics: ["machine learning", "data science"],
    level: "intermediate",
    access_level: "open",
    updated_at: "2026-07-21T10:00:00Z",
  },
  {
    resource_id: "res-004",
    title: "Deep Learning Systems",
    authors: ["L. Chen", "S. Okafor"],
    type: "book",
    description: "Architecture and training of deep neural networks, with chapters on optimisation and deployment.",
    topics: ["deep learning", "machine learning", "neural networks"],
    level: "advanced",
    access_level: "open",
    updated_at: "2026-06-30T10:00:00Z",
  },
  {
    resource_id: "res-005",
    title: "Retrieval-Augmented Generation: A Survey",
    authors: ["Kavya Rao", "Tomás Ibáñez"],
    type: "paper",
    description: "Survey of retrieval-augmented generation methods, evaluation benchmarks and open problems for grounded LLMs.",
    topics: ["retrieval-augmented generation", "rag", "nlp", "llm"],
    level: "advanced",
    access_level: "members",
    updated_at: "2026-10-01T10:00:00Z",
  },
  {
    resource_id: "res-006",
    title: "Algorithms Illustrated",
    authors: ["Tim Robertson"],
    type: "ebook",
    description: "Visual explanations of sorting, searching, graphs and dynamic programming.",
    topics: ["algorithms", "programming"],
    level: "intermediate",
    access_level: "members",
    updated_at: "2026-05-18T10:00:00Z",
  },
  {
    resource_id: "res-007",
    title: "Journal of Learning Analytics, Vol. 11",
    authors: ["Society for Learning Analytics Research"],
    type: "journal",
    description: "Peer-reviewed articles on measuring and improving learning with data.",
    topics: ["learning analytics", "education", "data science"],
    level: "intermediate",
    access_level: "members",
    updated_at: "2026-09-25T10:00:00Z",
  },
  {
    resource_id: "res-008",
    title: "Graph Neural Networks for Recommendation",
    authors: ["Arjun Pillai"],
    type: "dissertation",
    description: "PhD dissertation on graph neural network approaches to explainable recommender systems.",
    topics: ["recommender systems", "graph neural networks", "machine learning"],
    level: "advanced",
    access_level: "members",
    updated_at: "2026-03-14T10:00:00Z",
  },
  {
    resource_id: "res-009",
    title: "Statistics for Beginners",
    authors: ["Helen Park"],
    type: "book",
    description: "Plain-language introduction to descriptive statistics, probability and hypothesis testing.",
    topics: ["statistics", "data science"],
    level: "beginner",
    access_level: "open",
    updated_at: "2026-04-09T10:00:00Z",
  },
  {
    resource_id: "res-010",
    title: "Database Systems Essentials",
    authors: ["R. Menon", "D. Kaur"],
    type: "book",
    description: "Relational modelling, SQL, indexing and transactions for undergraduate courses.",
    topics: ["databases", "sql"],
    level: "intermediate",
    access_level: "open",
    updated_at: "2026-08-27T10:00:00Z",
  },
  {
    resource_id: "res-011",
    title: "Open Courseware: Linear Algebra",
    authors: ["University Open Learning"],
    type: "digital_resource",
    description: "Lecture notes, videos and exercises covering vectors, matrices and eigenvalues.",
    topics: ["linear algebra", "mathematics"],
    level: "beginner",
    access_level: "open",
    updated_at: "2026-10-20T10:00:00Z",
  },
  {
    resource_id: "res-012",
    title: "Natural Language Processing in Practice",
    authors: ["Sara Lindqvist"],
    type: "book",
    description: "Text processing, embeddings and transformer models with worked Python examples.",
    topics: ["nlp", "python", "machine learning"],
    level: "intermediate",
    access_level: "open",
    updated_at: "2026-09-03T10:00:00Z",
  },
  {
    resource_id: "res-013",
    title: "Defending LLM Applications Against Prompt Injection",
    authors: ["M. Haddad"],
    type: "paper",
    description: "Threat models and layered defences for tool-using language model applications.",
    topics: ["llm", "security", "nlp"],
    level: "advanced",
    access_level: "members",
    updated_at: "2026-10-15T10:00:00Z",
  },
  {
    resource_id: "res-014",
    title: "Cloud Computing Concepts",
    authors: ["Vikram Bose"],
    type: "ebook",
    description: "Introductory overview of cloud service models, virtualisation and scalability.",
    topics: ["cloud computing", "distributed systems"],
    level: "beginner",
    access_level: "open",
    updated_at: "2026-02-11T10:00:00Z",
  },
  {
    resource_id: "res-015",
    title: "Research Methods in Computer Science",
    authors: ["Grace Ndlovu"],
    type: "book",
    description: "Designing studies, reviewing literature and organising references for CS research projects.",
    topics: ["research methods", "academic writing"],
    level: "beginner",
    access_level: "open",
    updated_at: "2026-06-05T10:00:00Z",
  },
  {
    resource_id: "res-016",
    title: "Faculty Examination Archive 2025",
    authors: ["Examinations Office"],
    type: "digital_resource",
    description: "Restricted archive of past examination papers for teaching staff.",
    topics: ["examinations", "teaching"],
    level: "advanced",
    access_level: "restricted",
    updated_at: "2026-01-20T10:00:00Z",
  },
];

/** Physical copies per branch/shelf. Digital types have none. */
export const SEED_HOLDINGS: Record<string, { branch: string; shelf: string; total: number; available: number }[]> = {
  "res-001": [
    { branch: "Central Library", shelf: "CS-A1", total: 2, available: 1 },
    { branch: "Engineering Library", shelf: "E-12", total: 1, available: 1 },
  ],
  "res-002": [{ branch: "Central Library", shelf: "DS-B3", total: 3, available: 2 }],
  "res-003": [{ branch: "Central Library", shelf: "ML-B2", total: 1, available: 0 }],
  "res-004": [{ branch: "Engineering Library", shelf: "E-40", total: 2, available: 1 }],
  "res-005": [{ branch: "Science Annex", shelf: "Reading Room R2", total: 1, available: 1 }],
  "res-007": [{ branch: "Science Annex", shelf: "Periodicals P4", total: 2, available: 2 }],
  "res-008": [{ branch: "Central Library", shelf: "Theses T1", total: 1, available: 1 }],
  "res-009": [
    { branch: "Central Library", shelf: "ST-C1", total: 3, available: 2 },
    { branch: "Science Annex", shelf: "S-07", total: 1, available: 1 },
  ],
  "res-010": [{ branch: "Engineering Library", shelf: "DB-02", total: 2, available: 0 }],
  "res-012": [{ branch: "Central Library", shelf: "CS-A4", total: 2, available: 1 }],
  "res-013": [{ branch: "Science Annex", shelf: "Reading Room R2", total: 1, available: 1 }],
  "res-015": [{ branch: "Central Library", shelf: "RM-01", total: 3, available: 2 }],
};

/** Historical borrow counts (last 90 days) feeding the analytics fixture. */
export const SEED_BORROW_HISTORY: Record<string, number> = {
  "res-001": 42,
  "res-002": 35,
  "res-003": 51,
  "res-004": 18,
  "res-005": 12,
  "res-007": 6,
  "res-008": 4,
  "res-009": 29,
  "res-010": 38,
  "res-012": 24,
  "res-013": 9,
  "res-015": 15,
};

export const SEED_CONTENT: Record<string, string> = {
  "res-001":
    "Chapter 1 — Getting started. Python is a readable, general-purpose language. In this chapter you will install Python, run your first script and learn how variables store values.",
  "res-005":
    "Abstract — Retrieval-augmented generation (RAG) combines a retriever over an external corpus with a generator, grounding outputs in cited evidence and reducing unsupported claims.",
  "res-012":
    "Preface — This book teaches practical NLP: tokenisation, embeddings, and fine-tuning transformer models, each with runnable Python notebooks.",
};

export const DIGITAL_URLS: Record<string, string> = {
  "res-006": "https://library.example.edu/ebooks/algorithms-illustrated",
  "res-011": "https://library.example.edu/ocw/linear-algebra",
  "res-014": "https://library.example.edu/ebooks/cloud-computing-concepts",
  "res-016": "https://library.example.edu/restricted/exam-archive-2025",
};

const DAY = 86_400_000;

/** Loans are generated relative to "now" so due/overdue states stay meaningful. */
export function seedLoans(now: number) {
  const iso = (offsetDays: number) => new Date(now + offsetDays * DAY).toISOString().replace(/\.\d{3}Z$/, "Z");
  return [
    { loan_id: "loan-001", user_id: "user-001", resource_id: "res-012", borrowed_at: iso(-5), due_at: iso(9), returned_at: null, renew_count: 0 },
    { loan_id: "loan-002", user_id: "user-001", resource_id: "res-004", borrowed_at: iso(-20), due_at: iso(-6), returned_at: null, renew_count: 0 },
    { loan_id: "loan-003", user_id: "user-001", resource_id: "res-009", borrowed_at: iso(-25), due_at: iso(3), returned_at: null, renew_count: 1 },
    { loan_id: "loan-004", user_id: "user-001", resource_id: "res-003", borrowed_at: iso(-4), due_at: iso(10), returned_at: null, renew_count: 0 },
    { loan_id: "loan-005", user_id: "user-002", resource_id: "res-002", borrowed_at: iso(-3), due_at: iso(11), returned_at: null, renew_count: 0 },
    { loan_id: "loan-006", user_id: "user-003", resource_id: "res-015", borrowed_at: iso(-8), due_at: iso(6), returned_at: null, renew_count: 0 },
    { loan_id: "loan-007", user_id: "user-005", resource_id: "res-010", borrowed_at: iso(-30), due_at: iso(-16), returned_at: null, renew_count: 1 },
    { loan_id: "loan-008", user_id: "user-005", resource_id: "res-010", borrowed_at: iso(-60), due_at: iso(-46), returned_at: iso(-47), renew_count: 0 },
  ];
}

export function seedReservations(now: number) {
  const iso = (offsetDays: number) => new Date(now + offsetDays * DAY).toISOString().replace(/\.\d{3}Z$/, "Z");
  return [
    // user-002 waits for the copy user-001 has on loan, so loan-004 is not renewable.
    { reservation_id: "rsv-001", user_id: "user-002", resource_id: "res-003", status: "queued" as const, created_at: iso(-2) },
    { reservation_id: "rsv-002", user_id: "user-005", resource_id: "res-003", status: "queued" as const, created_at: iso(-1) },
    { reservation_id: "rsv-003", user_id: "user-001", resource_id: "res-010", status: "queued" as const, created_at: iso(-3) },
    { reservation_id: "rsv-004", user_id: "user-001", resource_id: "res-002", status: "ready" as const, created_at: iso(-1) },
    { reservation_id: "rsv-005", user_id: "user-003", resource_id: "res-010", status: "queued" as const, created_at: iso(-2) },
  ];
}
