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

- [x] ✋ Task 7 (Phase 2c): Backfill patch. **DONE 2026-07-08 (`76d0c7a` code, patches.txt `<this commit>`).**
      User signed off; executed on `miyano` via a guarded runner that snapshots payroll fields
      before/after — set `NN`×1 + `V`×2, **payroll fields byte-identical (0 changed)**, committed. Wired
      into `patches.txt` [post_model_sync] + logged in miyano Patch Log so migrate won't re-run.
  - Writes ONLY display fields `custom_attendance_code` + `custom_cong` (never status/leave_type/
    half_day_status) → payroll untouched; idempotent; preserves manually-set codes; reversible by
    clearing the two fields. 3 tests green.
  - Files: `hrms/patches/v15_0/backfill_attendance_codes.py` (+ test), `patches.txt`.

- [x] Task 8 (Phase 3a): Script Report "Bảng chấm công tháng". DONE `779e53c` — pivot
      employee × day = mã công + category totals (work_fraction). Read-only; verified via the
      framework report runner + unit test. Report name "Bang Cham Cong Thang" (ASCII so
      frappe.scrub matches the folder). Printable via Frappe's report view. **MVP read-layer done.**

- [ ] Task 9 (Phase 3b): VN paper-form Print Format (symbols, totals, sign-off boxes).
      **DEFERRED — needs a print target.** A Frappe Print Format attaches to a DocType; the
      monthly sheet is a Report, so a formal "paper form with sign-off boxes" belongs on the
      Phase 5 submittable "Bảng công tháng" DocType. The Task 8 report is already printable via
      the report view, so the MVP read-layer stands without it. Build with Phase 5.

## 2026-07-08 — full symbol set completed (Phases A–C)

User supplied the authoritative 13-symbol table + confirmed 4 decisions (all recommended).
Built on `feat/skip-attendance-diag`, TDD via the rollback harness, all committed:

- **Phase A** (`df2699c`): expanded to 11 enterable codes (added T / 1/2P / 1/2K / NN; renamed
  KL→K) + new Leave Type "Nghỉ tai nạn lao động". `work_fraction` re-defined as worked-công
  fraction. Fixtures synced to `miyano`; deprecated KL deleted (0 refs).
- **Phase B** (`6ae0cb4`): bridge handles single Half-Day codes (sets `half_day_status=Present`);
  `custom_cong` sums worked fraction over both halves. Payroll-invariance gate extended with a
  half-day scenario — still identical.
- **Phase C** (`d46100f`): report renders CN/NL/N calendar markers (from Holiday List +
  relieving date, no Attendance records) over a full employee roster; totals use worked-công
  semantics + new "Tai nạn LĐ" category.

Verified on `miyano`: 27 feature tests green + an end-to-end sheet render. Still deferred:
Task 7 (backfill patch), Task 9 (print format), Phases 4–5.

## Execution note

Dependency order starts at Task 1 (Phase 0), which is 🔴 BLOCKED (OQ#4) and ✋ ask-first.
Task 2 (DocType schema) is the only fully-ready slice, but the confirmed symbol table
(Task 3) may still influence its field set, so it is built only after OQ#3/#4 are answered
to avoid rework. Therefore: after committing this plan, STOP and collect OQ#3 (symbol table)
+ OQ#4 (Leave Types) + Phase-2 sign-off before building. Deferred: Phases 4–5.
