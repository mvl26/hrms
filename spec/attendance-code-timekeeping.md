# Spec: Vietnamese attendance-code timekeeping ("Bảng chấm công" / quản lý công)

> Status: **DRAFT for approval.** Nothing here is built yet. This transcribes the user's
> 5-phase plan into a reviewable spec and flags the decisions/data still needed. Do not
> start implementation until the Open Questions are resolved and the plan is approved.

## Objective

Give hospital HR an Excel-grid style monthly timekeeping sheet ("bảng chấm công") driven by
Vietnamese attendance symbols (mã công), **without changing payroll behaviour**. Every day
maps to one Attendance record carrying a morning + afternoon code; those codes are the
data-ified single source of truth that (a) drive the native `status`/`leave_type`/`half_day`
fields payroll already reads, and (b) render as the familiar VN symbols on the sheet.

**Success (MVP = Phases 1–3):** HR can read a correct, printable monthly sheet per employee
(symbol per day + category totals), and Salary Slip figures (`payment_days`, `absent_days`,
LWP) are provably unchanged versus before the feature.

## Locked design decision

**One Attendance record per day + morning/afternoon codes** (user's recommended default).
A single all-day shift 08:00–17:00 with *Every Valid Check-in and Check-out*. This avoids
`get_duplicate_attendance_record` and `validate_overlapping_shift_attendance` entirely →
near version-independent (v14/v15) and matches "1 ngày = 1 công". Rotating multi-shift
(2 records/day) is deferred to Phase 4 and only if a real rotating roster appears.

## Phased scope

| Phase | Deliverable | Risk | In MVP |
|---|---|---|---|
| 0 | Feature branch; standardize Leave Type catalog (VN law anchors) | Med (touches Leave Type master) | prereq |
| 1 | `Attendance Code` DocType + seed VN symbols via fixtures | Low (new master) | ✅ |
| 2 | Custom fields + two-way `before_validate` bridge + backfill patch | **High (core + payroll + data migration)** | ✅ |
| 3 | Script Report "Bảng chấm công tháng" + VN Print Format | None (read-only) | ✅ |
| 4 | Morning/afternoon & multi-shift refinement | Med (version-dependent) | ✗ |
| 5 | Business Trip doctype; submittable monthly sheet; geofence checkin | Varies | ✗ |

## Data model — `Attendance Code` (Phase 1)

Fields (from the user's plan): `code` (unique, e.g. "X"), `code_name`, `category`
(Công / Phép / Ốm / Không lương / Công tác / …), `work_fraction` (0, 0.5, 1),
`is_paid` (check), `maps_to_status` (Present / Absent / Half Day / On Leave / Work From Home),
`leave_type` (Link, nullable), `color`.

### Proposed starter symbol set — ⚠ DRAFT, NEEDS YOUR CONFIRMATION

These are a **tentative** guess to react to, NOT authoritative. Correct/replace before seeding
— this is exactly the domain data I must not invent.

| code | code_name | category | work_fraction | is_paid | maps_to_status | leave_type |
|------|-----------|----------|:---:|:---:|-----------|-----------|
| X  | Công (đủ ngày) | Công | 1.0 | ✔ | Present | — |
| X/2| Nửa công | Công | 0.5 | ✔ | Half Day | — |
| P  | Nghỉ phép năm | Phép | 1.0 | ✔ | On Leave | Nghỉ phép năm |
| Ô  | Nghỉ ốm | Ốm | 1.0 | ✔ | On Leave | Nghỉ ốm |
| TS | Thai sản | Ốm/Chế độ | 1.0 | ✔ | On Leave | Thai sản |
| KL | Nghỉ không lương | Không lương | 0.0 | ✘ | On Leave | Nghỉ không lương (is_lwp=1) |
| NB | Nghỉ bù | Công | 1.0 | ✔ | On Leave | Nghỉ bù (is_compensatory) |
| CT | Đi công tác | Công tác | 1.0 | ✔ | Work From Home / Present | — |
| K  | Vắng không lý do | Không lương | 0.0 | ✘ | Absent | — |

**Please provide the real table** (all symbols your hospitals use + the 7 columns above).

## Phase 0 — Leave Type anchors (VN law)

Standardize/ensure these Leave Types exist with correct flags so codes can point at them:
Nghỉ phép năm (`is_lwp=0`), Nghỉ ốm, Thai sản, Nghỉ không lương (`is_lwp=1`),
Nghỉ bù (`is_compensatory=1`), … Exported as fixtures. **Open:** exact names (VN vs EN),
and whether we may modify Leave Types that already exist on live sites (risk to existing
leave data) or only create missing ones.

## Phase 2 — the bridge (core of the feature)

Custom fields via fixtures on Attendance: `custom_attendance_code`, `custom_morning_code`,
`custom_afternoon_code`, `custom_cong` (read-only, computed). `before_validate`:

- **Forward** (user typed codes): from morning/afternoon codes → set native `status`,
  `leave_type`, `half_day`, `half_day_status`, and `custom_cong = Σ work_fraction`.
  E.g. sáng=X + chiều=P → Half Day, half_day_status Present, leave_type = phép năm, cong=0.5.
- **Reverse** (record made by auto-attendance/leave, no code yet): from `status` + `leave_type`
  → derive the code(s) for display.

Payroll keeps reading `status` unchanged → **no payroll code edits.** Plus a **backfill
patch** to populate `custom_attendance_code` on existing Attendance.

## Phase 3 — the sheet (read-only)

Script Report "Bảng chấm công tháng": pivot Attendance by employee × day, cell = code,
summary columns sum `work_fraction` by category (Công/Phép/Ốm/KL/CT). VN paper-form Print
Format (symbols, totals, sign-off boxes). Read-only → data-safe.

## Testing strategy (mandatory)

- **Payroll invariance (gate for Phase 2):** build a Salary Slip on fixed data, record
  `payment_days` / `absent_days` / LWP; add codes / run the bridge; rebuild the slip; assert
  the three figures are **identical**. This test must exist and pass before the bridge merges.
- TDD per task (RED→GREEN). Run tests safely on the real `miyano` site via the console
  harness noted in memory (monkeypatch `frappe.db.commit`, rollback in finally) — do **not**
  `bench run-tests` here (ERPNext `before_tests` commits fixtures into this live company DB).
- Run one month in parallel with the old process before cut-over.

## Rollout

Everything (Attendance Code records + Custom Fields + Leave Types) exported as **fixtures**
so `bench migrate` deploys to all hospital sites. Fixture deploy to production sites is an
**ask-first** step, not autonomous.

## Boundaries

- **Always:** TDD + payroll-invariance test before touching the bridge; export additive
  fixtures; stage only each task's files.
- **Ask first (STOP for sign-off):** Phase 2 `before_validate` bridge, the backfill patch,
  any Leave Type modification on existing data, and every fixtures→site deploy.
- **Never:** edit payroll (Salary Slip) logic; change native `status` semantics; relax the
  payroll-invariance test to make things pass; deploy fixtures to production without sign-off.

## Open Questions (block start)

1. **Baseline** — how to handle the unrelated uncommitted changes (frontend/*, expense_*, .claude).
2. **Branch base** — new feature branch off develop / feat/skip-attendance-diag / version-15?
3. **The VN symbol table** — the authoritative list (see draft above).
4. **Leave Types** — exact names + may we modify existing ones, or create-if-missing only?
5. **Run scope** — spec+plan-only for now, or build through Phase 1, or full MVP (1–3)?

## Success Criteria (MVP)

- [ ] `Attendance Code` DocType + confirmed VN symbols seeded via fixtures.
- [ ] Two-way bridge sets native fields correctly; `custom_cong` = Σ work_fraction.
- [ ] Payroll-invariance test passes (payment_days/absent_days/LWP unchanged).
- [ ] "Bảng chấm công tháng" report + Print Format render a correct monthly sheet.
- [ ] All new work reversible via `git revert`; fixtures additive.
