# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

This repo is **Miyano HR — Miyano Việt Nam's in-house HR, timekeeping and payroll system.** It is private software for one deployment: not open source, not a product for resale. It runs on the Frappe Framework + ERPNext (v15), and encodes Miyano's Vietnamese HR / timekeeping / payroll rules.

- One app inside a bench: **run all `bench` commands from the bench root `/home/miyano/frappe-bench`**, not from `apps/hrms`. Depends on `frappe` + `erpnext` (`required_apps` in `hooks.py`; versions pinned in `pyproject.toml`).
- **`miyano` is Miyano's live site and holds real HR/payroll data** — treat it as production-like, never a scratch site.
- **Miyano self-maintains:** this repo no longer tracks any upstream. Changes need not preserve merge compatibility, but must stay `git revert`-able and ship with tests. The trade-off, accepted deliberately: any security fix published for the upstream HR app must be found and applied by Miyano itself. Integration branch is `version-15`; feature work happens on `feat/*`.

## Working on the `miyano` site safely (read before running anything)

Because `miyano` carries real data, some ordinary Frappe commands are unsafe:

- **NEVER run `bench --site miyano run-tests`.** The runner commits into the DB (`before_tests` commits fixtures; `process_auto_attendance` commits attendance), and `FrappeTestCase` only rolls back its own txn — rows leak into real data. `run-tests` belongs only to CI's throwaway `test_site` (`.github/workflows/ci.yml`).
- **Run this project's tests via the rollback console harness** instead: `frappe.flags.in_test = True`, monkeypatch `frappe.db.commit` → no-op, isolate each test with a savepoint (a `unittest.TextTestResult` subclass that opens a savepoint in `startTest` and rolls back in `stopTest`), and `frappe.db.rollback()` in `finally`. Drive it with `bench --site miyano console` / `bench execute`.
- **Payroll-invariance gate:** any attendance change must prove Salary Slip `payment_days` / `absent_days` / LWP are unchanged before vs. after. Payroll reads only `status` / `leave_type` / `half_day_status`; display fields (mã công, `custom_cong`, …) must never move payroll numbers.
- **Ask first / get sign-off** before: changing payroll-bridge logic, running a backfill or data-migration patch (not `git revert`-able), editing `Leave Type`s, or deploying `fixtures` onto the site.
- **Deploy model:** code-defined doctypes & schema → `bench --site miyano migrate`; master data (Leave Types, Attendance Codes, custom fields) → the `fixtures` mechanism, re-synced every migrate.

## Commands

```bash
cd /home/miyano/frappe-bench

bench --site miyano migrate                                   # apply doctype/schema/patch changes
bench --site miyano execute hrms.skip_attendance_diag.diagnose # one-off server function / data fix
bench --site miyano console                                    # REPL; also drives the rollback test harness
bench build --app hrms                                         # rebuild desk bundles after editing hrms/public/js/*
# Tests: do NOT run-tests on miyano — use the rollback harness above.
```

Lint/format is **ruff** via pre-commit (`.pre-commit-config.yaml`; config in `pyproject.toml`): **tabs**, **double quotes**, line length 110, py310. Run `pre-commit run --all-files` from the app dir.

Frontend:

```bash
yarn dev-pwa      # frontend/ dev server → view at http://miyano:8080/hrms (host must be `miyano`, not localhost)
yarn dev-roster   # roster/ dev server
yarn build        # build both SPAs into hrms/public/ + hrms/www/
```

The Vue dev page only renders via host `miyano` (vite `allowedHosts`, and Frappe resolves the site from the hostname), needs `developer_mode = 1` on the site, and `bench start` running for API/login proxying.

## Architecture

**`hrms/hooks.py` is the central wiring file** — nothing self-registers; behavior is bolted on here. Before tracing "how does X happen", grep `hooks.py`. Key sections:

- `override_doctype_class` — HRMS **subclasses ERPNext doctypes** (`Employee`, `Timesheet`, `Payment Entry`, `Project`) via `hrms/overrides/`. The runtime class is the override, not the ERPNext original.
- `doc_events` — cross-doctype side effects (e.g. Journal/Payment Entry submit → update Expense Claim). Logic often lives on a *different* doctype than the one being edited.
- `scheduler_events` — background jobs; notably `hourly_long` → `shift_type.process_auto_attendance_for_all_shifts` (attendance from check-ins), central to the Miyano attendance work.
- `after_migrate` — runs `hrms.setup_vn_defaults.ensure_defaults` (Miyano self-heal, below).
- `fixtures` / `regional_overrides` — master data export filter; India-specific tax/HRA swaps.

**Doctypes** live under `hrms/<module>/doctype/<name>/` (JSON schema + `.py` controller + `.js` desk form + `test_*.py`). Only two modules — `HR` (119 doctypes) and `Payroll` (40) — see `hrms/modules.txt`. Shared logic: `hrms/hr/utils.py`, `hrms/controllers/`, `hrms/mixins/`; `hrms/api/` holds the whitelisted endpoints the Vue apps call.

**Two Vue 3 SPAs** (not desk), built with vite + `frappe-ui`, wired via `website_route_rules`:
- `frontend/` — Ionic PWA, employee self-service (attendance, leave, expense, salary slips) → route `/hrms`.
- `roster/` — TypeScript, shift roster/planning → route `/hr`. (`frappe-ui/` at repo root is a git submodule.)

## Miyano customizations (Vietnamese HR / timekeeping)

An additive VN localization layer. Each feature has a spec in `spec/` — read it before extending.

- **Attendance-code timekeeping (mã công):** 13 `Attendance Code` symbols (X, P, Ô, TS, V, …) driving an Excel-style monthly *bảng chấm công* **without changing payroll**. A two-way `Attendance.before_validate` bridge maps codes ↔ `status`/`leave_type`/`half_day_status` and computes `custom_cong`.
- **Bảng Công Tháng:** submittable monthly-timesheet DocType — a **read-only snapshot** of Attendance (never writes back → payroll-neutral), with a VN print format + sign-off boxes. Detail row totals: `cong/phep/om/thai_san/tnld/nghi_bu/khong_luong/vang`.
- **Công Tác (business trip):** submittable multi-traveler DocType driven by a Frappe **Workflow** ("Cong Tac Approval"); approval auto-generates trip attendance + per-traveler Expense Claims. Introduces a `COO` role.
- **Yêu cầu chấm công (Attendance Request):** native Frappe channel re-enabled (was locked 2026-07-24) for days the employee **is working / must count present** — WFH, missed-punch, on-duty, late/early — approved by the **line manager** (`reports_to`), distinct from Leave Application (time off) and Công Tác (trips). Miyano layer in `attendance_request_miyano.py`: default approver + ToDo assign + submit guard + display codes (WFH→`W`, on-duty→`CT`, missed/late→`X`) written display-only → **payroll-neutral**. `reason` options extended via Property Setter. Spec `spec/attendance-request-vs-leave.md`.
- **Geofence check-in:** server-emitted radius circle on Shift Location maps, click-to-set, read-only overlay on Employee Checkin (enforcement logic unchanged).
- **Working-hours** report + desk dashboard (net vs. standard hours), in `hrms/hr/working_hours.py`.

Key files & mechanisms:

- **Custom doctypes** (VN): `Attendance Code`, `Monthly Attendance Sheet` (+ `Detail`), `Business Trip` (+ `Traveler`) — renamed from VN-romanized names 2026-07-15 (labels stay VN via translations). Plus `Attendance` custom fields (`custom_attendance_code`, `custom_morning_code`, `custom_afternoon_code`, `custom_work_credit`), `Expense Claim-custom_business_trip`, and 5 `Shift Type` split-half-day fields.
- **`hrms/setup_vn_defaults.py::ensure_defaults()`** — wired to `after_install` **and every `after_migrate`**. Idempotently self-heals the Công Tác workflow + `COO` role and warns (never recreates) if fixture master data is missing. Touches no HR Settings or transactional data.
- **Fixtures** (`hrms/fixtures/`): 8 VN `Leave Type`s, 14 `Attendance Code`s, and the custom fields above. **Keep the `hooks.py` `fixtures` export filter in sync with the JSON** — `test_setup_vn_defaults.py` enforces it.
- **`hrms/skip_attendance_diag.py`** — standalone diagnostic/repair tool for check-ins wrongly stuck at `skip_auto_attendance = 1` (run via `bench execute`; see its docstring).
- **GOTCHA:** a leading-underscore method on a Frappe `Document` is intercepted by `__getattr__` (returns `None`) — name helper methods **without** a `_` prefix.

## Development workflow

Spec-driven via the **superpowers** skills (brainstorm → spec → plan → build TDD → verify E2E → review → fix), committing each step. Read the relevant artifact before related work: `spec/*.md` (feature specs), `tasks/plan-*.md` (task breakdowns with done/remaining checkboxes), `SPEC.md` (active spec), `docs/superpowers/` (earlier ones).

Execution style: the user drives with short prompts ("chạy tiếp", "hoàn thiện") and expects the full lifecycle carried autonomously without per-step check-ins — keep momentum. Still surface genuine product decisions briefly, always honor the high-risk sign-off gates above, and reserve outward/irreversible actions (git push, PRs) for explicit approval.

## Conventions

- **Conventional Commits**, enforced by `commitlint.config.js`. Miyano commits scope with `(hr)`, e.g. `feat(hr): ...`.
- **Stage only the files your change touches** (`git add <paths>`, never `git add -A`) — the working tree often carries unrelated in-progress work. `.claude/` is tracked (local tooling config shared across machines).
- **Schema change** = edit the doctype JSON → `bench --site miyano migrate`; a new patch needs an entry in `hrms/patches.txt`.
