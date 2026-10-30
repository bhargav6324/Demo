# Smart Library Management

This repository contains the Smart Library project modules.

| Module | Location | Status |
| --- | --- | --- |
| Backend | [backend/](backend/) | Phases 1-5 verified; Phase 6 analytics/audit implemented, tester verification pending |
| AI service | [ai_service/](ai_service/) | Chat, RAG, recommendations, tool orchestration; runs on port 8002 against mock or real backend |

Backend setup, API usage, demo credentials, and test commands are in [backend/README.md](backend/README.md). Run backend commands from that directory:

```bash
cd backend
```

Backend code, dependencies, tests, documentation, project memory, and the reference PDF are contained in `backend/`. Other contributors can add their modules in separate directories at the repository root. Backend integration is through its documented HTTP APIs.

AI service setup, chat API, tools and how to connect it to the backend are in [ai_service/README.md](ai_service/README.md). Run AI service commands from that directory:

```bash
cd ai_service
```
