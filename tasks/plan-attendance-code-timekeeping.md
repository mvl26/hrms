# Plan: Vietnamese attendance-code timekeeping (MVP = Phases 1–3)

Derived from `spec/attendance-code-timekeeping.md`. Branch: `feat/skip-attendance-diag`
(per user). Baseline: leave the unrelated dirty files (frontend/*, expense_*, .claude/)
untouched — each task stages ONLY its own files.

**Legend:** 🔴 BLOCKED on domain data (must not invent) · ✋ ASK-FIRST sign-off before
running · ⬜ ready to build.

- [x] Task 0: Write this plan (preparatory commit).
  - Files: `tasks/plan-attendance-code-timekeeping.md`

- [x] Task 1 (Phase 0): Leave Type anchors. DONE (`4428184`) — created 6 VN Leave Types
      (create-if-missing; existing English ones untouched), filtered fixture. Integrity test green.
  - Blocked by OQ#4: exact VN/EN Leave Type names + flags (`is_lwp`, `is_compensatory`),
    and policy — create-if-missing only, or may we modify Leave Types that already exist on
    live sites (risk to existing leave data)?
  - Ask-first: any modification of existing Leave Types.
  - Acceptance: required Leave Types exist with correct flags; exported as additive fixtures.
  - Verify: fixture load on miyano via rollback harness; assert flags.
  - Files: `hrms/fixtures` (leave_type), `hooks.py` (fixtures list).

- [x] Task 2 (Phase 1a): `Attendance Code` DocType (schema only, no seed data).
  - Fields from spec: `code` (unique), `code_name`, `category`, `work_fraction` (0/0.5/1),
    `is_paid`, `maps_to_status` (Present/Absent/Half Day/On Leave/Work From Home),
    `leave_type` (Link, nullable), `color`.
  - Acceptance: DocType installs; a code inserts; duplicate `code` rejected.
  - Verify: TDD via rollback harness (create code, assert unique constraint).
  - Files: `hrms/hr/doctype/attendance_code/*`.
  - Depends on: Task 0. (Structurally independent of the symbol data.)

- [x] Task 3 (Phase 1b): Seed the VN symbol set via fixtures. DONE (`4e90cd4`) — user provided
      the 7 mã (X/P/Ô/Cô/TS/NB/KL); seeded as Attendance Code fixtures linked to Phase-0 Leave
      Types. Integrity test green. **STOP HERE — Task 4 (Phase 2) is ask-first (core + payroll).**
  - Blocked by OQ#3: the authoritative mã-công table (all symbols + the 7 columns). The
    spec's draft table is explicitly NOT authoritative and must not be seeded as-is.
  - Acceptance: confirmed symbols present as fixtures; each maps to a valid status/leave_type.
  - Verify: fixture load; assert each code resolves.
  - Files: `hrms/fixtures/attendance_code.json`, `hooks.py`.
  - Depends on: Task 1 (leave_type links), Task 2.

- [x] Task 4 (Phase 2a): Custom fields on Attendance via fixtures. DONE `c26786e`.
  - `custom_attendance_code`, `custom_morning_code`, `custom_afternoon_code`,
    `custom_cong` (read-only, computed).
  - Ask-first: adds fields to core Attendance (fixtures → all sites).
  - Files: `hrms/fixtures/custom_field.json`, `hooks.py`.
  - Depends on: Task 2.

- [x] Task 5 (Phase 2 GATE): Payroll-invariance test. DONE `f00d163` — native vs code entry
      give identical payment_days/absent_days/LWP. Gate passed.
  - Build a Salary Slip on fixed data; record `payment_days`/`absent_days`/LWP; add codes +
    run the bridge; rebuild; assert the three are identical.
  - Verify: rollback harness (no `bench run-tests` — before_tests commits into live DB).
  - Files: `hrms/hr/doctype/attendance/test_attendance.py` (or a new test module).
  - Depends on: Task 4.

- [x] Task 6 (Phase 2b): `before_validate` two-way bridge. DONE `e141745` — 6 bridge unit tests
      green; payroll-invariance (Task 5) green; shift_type regression (29) green.
  - HIGH-RISK: touches core Attendance validation feeding payroll. Correct mapping depends on
    the confirmed symbol table (Task 3). Ask-first sign-off before merge.
  - Acceptance: forward + reverse mappings correct; payroll-invariance test (Task 5) green.
  - Files: `hrms/hr/doctype/attendance/attendance.py`.
  - Depends on: Task 3, Task 5.

- [ ] 🔴✋ Task 7 (Phase 2c): Backfill patch to populate `custom_attendance_code` on existing
      Attendance. **← STOP HERE. Not run: data migration that mutates existing rows, NOT
      reversible via git revert. Needs explicit sign-off + dry-run plan.**
  - HIGH-RISK data migration — NOT reversible via `git revert` alone (mutates rows).
    Explicit sign-off + a dry-run/rollback plan required before running on any site.
  - Files: `hrms/patches/*`, `patches.txt`.
  - Depends on: Task 6.

- [ ] ⬜ Task 8 (Phase 3a): Script Report "Bảng chấm công tháng" (read-only pivot:
      employee × day = code; summary columns sum `work_fraction` by category).
  - Data-safe (read-only). Files: `hrms/hr/report/bang_cham_cong_thang/*`.
  - Depends on: Task 3 (codes exist to display).

- [ ] ⬜ Task 9 (Phase 3b): VN paper-form Print Format (symbols, totals, sign-off boxes).
  - Data-safe. Files: print format fixture / `hrms/fixtures`.
  - Depends on: Task 8.

## Execution note

Dependency order starts at Task 1 (Phase 0), which is 🔴 BLOCKED (OQ#4) and ✋ ask-first.
Task 2 (DocType schema) is the only fully-ready slice, but the confirmed symbol table
(Task 3) may still influence its field set, so it is built only after OQ#3/#4 are answered
to avoid rework. Therefore: after committing this plan, STOP and collect OQ#3 (symbol table)
+ OQ#4 (Leave Types) + Phase-2 sign-off before building. Deferred: Phases 4–5.
