# Settings Skills Usability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make configuration easier to use, starting with a practical Skills admin experience.

**Architecture:** Extend existing admin routes with minimal CRUD endpoints for skills and a safe draft generator endpoint. Redesign the current React settings view with horizontal tabs and a focused Skills workspace containing Library, Editor, and IA Generator sections.

**Tech Stack:** FastAPI, psycopg, Pydantic, React, TypeScript, Vite, CSS.

## Global Constraints

- Preserve existing database schema; use existing `skills` columns only.
- Do not execute arbitrary generated code.
- Keep CRUD admin-only, but allow normal logged-in users to list and run safe skills.
- Keep changes small and compatible with existing tests.

---

### Task 1: Backend Skills CRUD

**Files:**
- Modify: `backend/app/admin/routes.py`
- Modify: `backend/tests/test_admin_payloads.py`

**Interfaces:**
- Produces: `PATCH /api/admin/skills/{skill_id}` returning `{ skill }`
- Produces: `DELETE /api/admin/skills/{skill_id}` returning `{ id, deleted: true }`

- [x] Add tests for update/delete audit behavior.
- [x] Implement update and delete endpoints using `execute_returning` and `connect` patterns already used in the file.
- [x] Run `pytest tests/test_admin_payloads.py -q`.

### Task 2: Safe Skill Draft Generator

**Files:**
- Modify: `backend/app/admin/routes.py`
- Modify: `backend/tests/test_admin_payloads.py`

**Interfaces:**
- Produces: `POST /api/admin/skills/generate` with `{ prompt: string }`
- Returns: `{ draft: { name, description, instructions, checklist } }`

- [x] Add Pydantic payload and deterministic generator test.
- [x] Implement generator as a safe structured draft, not executable code.
- [x] Run `pytest tests/test_admin_payloads.py -q`.

### Task 3: Settings Tabs and Skills UI

**Files:**
- Modify: `frontend-modern/src/App.tsx`
- Modify: `frontend-modern/src/styles.css`

**Interfaces:**
- Consumes: skill CRUD/generator endpoints from Tasks 1 and 2.
- Produces: horizontal settings tabs and Skills sub-tabs.

- [x] Replace settings side nav with top tabs.
- [x] Add Skills Library cards with edit, enable/disable, delete, assigned-agent chips.
- [x] Add Skills Editor form supporting create and update.
- [x] Add Skills Generator form that creates a safe draft and can populate the editor.
- [x] Run `npm run build`.

### Task 4: Verification

**Files:**
- Modify only if verification exposes defects.

- [x] Run backend tests: `pytest -q`.
- [x] Run frontend build: `npm run build`.
- [x] Restart frontend dev server.
