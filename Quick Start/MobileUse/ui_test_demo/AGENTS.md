# Agent Guide

This file is for coding agents and maintainers working on MUA Automation
Platform. Read it before changing code.

## Project Summary

MUA Automation Platform is a local-first mobile UI automation console.

- Backend: FastAPI, SQLAlchemy, SQLite, Pydantic, uvicorn.
- Frontend: React 19, TypeScript, Vite, React Router, TanStack Query.
- Test stack: pytest, Vitest, Playwright.
- Real-device path: Mobile Use Runner with Pod discovery and TOS-backed
  execution assets.

## High-Signal Commands

```bash
uv sync
npm ci
make dev
make test
npm run build
make e2e
```

Focused commands:

```bash
APP_SECRET_KEY=test-secret-key-at-least-32-bytes uv run pytest tests/backend
npm test
npm run test:e2e
uv run uvicorn mua_platform.main:app --reload
npm run dev
```

`make dev` builds the frontend and serves `dist/` from FastAPI. For UI hot
reload, run uvicorn and Vite separately.

## Repository Map

```text
src/mua_platform/main.py        FastAPI app factory, routers, worker lifecycle
src/mua_platform/config.py      environment settings and secret-key resolution
src/mua_platform/db.py          SQLite engine, schema creation, lightweight migrations
src/mua_platform/auth/          admin setup, multi-user login, roles, sessions, CSRF
src/mua_platform/settings/      encrypted runner settings and audit events
src/mua_platform/tasks/         task models, state machine, scheduler, worker
src/mua_platform/runners/       Mobile Use Runner, remote gateway
src/mua_platform/pods/          Pod discovery, allocation, leases, task sync
src/mua_platform/test_plans/    test-plan CRUD, execution, report assembly
src/mua_platform/traces/        persisted task trace spans
web/                            React app, pages, components, API types/client
tests/backend/                  pytest coverage
tests/frontend/                 Vitest + Testing Library coverage
tests/e2e/                      Playwright flows and controlled servers
```

## Safety Rules

- Never commit `.env`, `data/`, `dist/`, `app.db`, screenshots, temporary live-run
  scripts, Playwright traces, or real execution artifacts.
- Never print, persist, fixture, or expose real Access Key ID, Secret Access Key,
  Ark API Key, callback authorization headers, MCP authorization headers, or raw
  remote responses that may contain prompts or credentials.
- Secrets are write-only in the UI. Empty secret inputs mean "keep existing
  value"; do not replace stored secrets with empty strings unless the API
  explicitly implements that behavior.
- `APP_SECRET_KEY` must remain stable for existing data. Changing it makes
  encrypted settings undecryptable.
- Production must not use weak or test secret keys.
- Treat real Mobile Use checks as manual-only. Do not put real credentials
  or live cloud calls in CI.

## Core Domain Rules

- SQLite is the task source of truth. Preserve idempotency and atomic task claim
  behavior.
- Task status and operation controls are separate. Do not make status badges the
  only way to trigger actions.
- Remote task results and screenshots must be filtered by `remote_run_id`.
  Filtering only by `ThreadID` can mix old assets into a newer task.
- Remote `Status=3` and `Status=6` are both terminal for the current integration
  and must drive local result convergence.
- `result_ready` with verdict `pass` or `fail` can be saved as a reusable script.
- Evidence gaps, malformed structured output, missing must assertions, or
  untrusted natural-language success claims must not become a passing verdict.
- Queued tasks can cancel locally. Running tasks remain running until runner
  cancellation converges or the service finalizes interruption.
- Pod allocation uses local leases for single-instance mutual exclusion. Do not
  describe or implement it as a distributed lock.
- Existing deployment boundary is single tenant, single instance, SQLite.

## Runner Notes

Mobile Use Runner:

- Requires Access Key ID, Secret Access Key, Product ID, TOS Bucket, and TOS
  Region for real execution.
- Discovers Pods with `ListPod` and validates availability with `DetailPod`.
- Uses `RunAgentTaskOneStep -> ListAgentRunCurrentStep -> GetAgentResult`.
- Start and cancel POST calls must not be replayed blindly.
- GET polling can retry bounded transient failures.
- Persist safe structured trace fields only.

## Configuration Rules

- Environment variables are parsed by `src/mua_platform/config.py`.
- `.env.example` is documentation, not a place for real credentials.
- Frontend settings saved in the UI can override `MOBILE_USE_*` defaults.
- Execution snapshots are captured when tasks or test-plan executions are
  created. Later settings changes must not mutate historical runs.
- Agent runtime options belong in execution config forms, not as unrelated
  top-level fields.
- Timeout copy should use "任务超时 Timeout（秒）" or "默认任务超时 Timeout（秒）"
  in Chinese UI text. Avoid "接口超时" for task execution timeout.

## Backend Change Rules

- Prefer changing domain services before adding logic to routers.
- Keep routers thin: validate, call service/repository, return schema.
- When adding SQLAlchemy models, ensure they are imported before
  `Base.metadata.create_all(engine)` in `main.py` or covered by schema migration
  helpers.
- When adding persistent fields, update schemas, repositories, migrations or
  compatibility helpers, tests, and API types.
- Use structured API errors from `api/errors.py`; do not leak raw exceptions or
  sensitive upstream response bodies.
- Keep FastAPI development runs on `--reload` when changing model fields.

## Frontend Change Rules

- API contracts live in `web/api/types.ts` and `web/api/client.ts`.
- Route structure lives in `web/app.tsx`.
- Keep UI patterns consistent across pages: compact layout, clear action
  buttons, fixed modal header/footer with scrollable content where applicable.
- Prefer placeholder examples over auto-injecting example values into inputs.
- Use explicit buttons for state changes; do not hide critical actions in status
  badges.
- Keep lists height-bounded with internal scroll when they can grow.
- After saving case configuration, keep `case-detail` cache in sync.

## Testing Expectations

Run the smallest relevant check first, then broaden based on risk.

- Backend domain or API change: targeted `uv run pytest tests/backend/...`.
- Frontend component or page change: targeted Vitest test.
- API type or cross-page behavior change: `npm test`.
- Task execution, settings, Pod, or report workflow change: relevant Playwright
  spec, then `make e2e` when feasible.
- Before claiming a broad change is complete, run at least `make test` and
  `npm run build`. Use `make e2e` for end-to-end behavior changes.

## Documentation Rules

- Keep `README.md` user-facing and open-source friendly.
- Keep this file focused on agent-maintainer instructions.
- If adding public deployment guidance, document secret handling and the current
  single-instance SQLite boundary clearly.

## Dirty Worktree Rule

This repository may contain user changes. Do not revert files you did not
modify. If a required file has unrelated edits, read it carefully and make the
smallest compatible change.
