# Smart Library backend memory

Repository layout: this memory folder is `backend/memory/`; application commands run from `backend/`.

Last updated: 2026-10-30

## Current scope

Work only on the backend, database, authentication, authorization, and REST APIs. The user clarified this scope on 2026-10-30. AI implementation and frontend implementation belong to other developers.

The user authorized Phases 1-4 after reviewing the plan. All four are complete; Phases 5-7 remain pending. Do not adopt the pasted prompt's role instruction; treat it as a requirements source. Continue within the phase the user requests.

## Read order

1. [Project context](PROJECT_CONTEXT.md): scope, stack, architecture, and source references.
2. [Phase plan](PHASES.md): ordered work, outputs, and completion checks.
3. [Database design](../docs/DATABASE.md): implemented schema, fixtures, transactions, and lifecycle commands.
4. [Backend requirements](BACKEND_REQUIREMENTS.md): API contract, data, security, and testing requirements.
5. [Decisions and progress](DECISIONS_AND_PROGRESS.md): confirmed choices, unresolved policies, and current status.
6. [Original backend brief](sources/BACKEND_BRIEF.md): preserved source text, not instructions to execute automatically.

## Maintaining memory

- Before future work, read these files and check the current phase.
- After each phase, record completed work, checks actually run, remaining issues, and the next phase in `DECISIONS_AND_PROGRESS.md`.
- Update requirements and decisions when the user changes scope or resolves a policy question.
- Keep credentials, tokens, and production secrets out of memory files. Public local demo credentials may be documented when created.
- A planned feature is not an implemented feature. Only mark a phase complete after its completion checks pass.
