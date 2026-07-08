# Spec: Vietnamese attendance-code timekeeping ("Bảng chấm công" / quản lý công)

> Status: **MVP (Phase 0–3a) BUILT & committed** on `feat/skip-attendance-diag`. **2026-07-08:**
> user supplied the authoritative 13-symbol table and confirmed the 4 open decisions (all
> recommended) → this revision finalizes the full symbol set (adds T, 1/2P, 1/2K, NN, K, and
> calendar markers CN/NL/N) and the `work_fraction = worked-công fraction` semantics. Build
> scope this round: code + fixtures + tests + `bench migrate` on the **dev** site `miyano` +
> commit. **No production deploy** (still ask-first).

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

### Authoritative symbol set — CONFIRMED 2026-07-08

`work_fraction` = **phần ngày tính là công đi làm thực tế** (worked-công fraction: 1 / 0.5 / 0).
`half_day_status` is NOT a field on Attendance Code — the bridge derives it (any code whose
`maps_to_status = Half Day` → `half_day_status = Present`, i.e. the worked half is present).

**Mã nhập trực tiếp (tạo 1 bản ghi Attendance/ngày):**

| code | code_name | category | work_fraction | is_paid | maps_to_status | leave_type |
|------|-----------|----------|:---:|:---:|-----------|-----------|
| X    | Đi làm đủ công          | Công        | 1.0 | ✔ | Present  | — |
| NN   | Làm nửa ngày (hưởng lương) | Công     | 0.5 | ✔ | Half Day | — |
| P    | Nghỉ phép năm           | Phép        | 0.0 | ✔ | On Leave | Nghỉ phép năm |
| 1/2P | Nghỉ phép nửa ngày      | Phép        | 0.5 | ✔ | Half Day | Nghỉ phép năm |
| Ô    | Nghỉ ốm (bản thân)      | Ốm          | 0.0 | ✔ | On Leave | Nghỉ ốm |
| Cô   | Nghỉ chăm con ốm        | Ốm          | 0.0 | ✔ | On Leave | Nghỉ chăm con ốm |
| TS   | Nghỉ thai sản           | Thai sản    | 0.0 | ✔ | On Leave | Nghỉ thai sản |
| T    | Nghỉ tai nạn lao động   | Tai nạn LĐ  | 0.0 | ✔ | On Leave | Nghỉ tai nạn lao động |
| NB   | Nghỉ bù                 | Nghỉ bù     | 0.0 | ✔ | On Leave | Nghỉ bù (is_compensatory) |
| K    | Nghỉ không lương cả ngày | Không lương | 0.0 | ✘ | On Leave | Nghỉ không lương (is_lwp=1) |
| 1/2K | Nghỉ không lương nửa ngày | Không lương | 0.5 | ✘ | Half Day | Nghỉ không lương (is_lwp=1) |
| V    | Vắng không lý do        | Vắng        | 0.0 | ✘ | Absent   | — |

`V` (added 2026-07-08) is the display symbol for an **Absent** day — an auto-attendance record
marked Absent (checkin below the hours threshold) or a manual Absent. Display-only: `Absent`
already docks a full day in payroll, so mapping it to a symbol changes nothing.

### Auto-flows: checkin & leave → Attendance (verified 2026-07-08)

The bridge's reverse-derivation runs in `before_validate`, which Frappe executes **even under
`flags.ignore_validate=True`** — so both auto-flows populate the mã công with no extra hooks:

- **Employee Checkin → auto-attendance:** Present→`X`, Absent→`V`, Half Day→`NN` (công from work_fraction).
- **Leave Application → Attendance:** On Leave + leave_type → `P/Ô/Cô/TS/T/NB/K`; Half Day + leave_type → `1/2P`.

Half-day payroll: only `half_day_status="Absent"` docks pay (salary_slip.py ~line 555). For `NN`
(no leave application) `check_leave_record` forces `half_day_status=Absent` → paid half; for `1/2P`/`1/2K`
the leave half is handled by its leave_type. The payroll-invariance gate covers X/K/P/**V**/half-day.

For a **single Half-Day code** (NN / 1/2P / 1/2K) the bridge sets `status=Half Day`,
`half_day_status=Present`, `leave_type = code.leave_type` (None for NN → worked half + unpaid
absent half; the leave half for 1/2P/1/2K). This is byte-identical to what a human entering
Half Day natively would set → payroll stays invariant.

**Mã hiển thị trên bảng, suy ra từ lịch (KHÔNG tạo Attendance record, KHÔNG đụng payroll):**

| code | ý nghĩa | nguồn suy ra |
|------|---------|--------------|
| CN | Chủ nhật (nghỉ tuần) | Holiday List của nhân viên, `weekly_off = 1` |
| NL | Nghỉ lễ trong năm | Holiday List, ngày lễ (không phải weekly_off) |
| N  | Đã ngừng làm việc | ngày > `relieving_date`, hoặc Employee status Inactive/Left |

Priority khi tô ô: `N` (đã nghỉ việc) > bản ghi Attendance > `NL` > `CN` > trống.

### work_fraction & totals semantics (report)

- **Cột Công** = Σ `custom_cong` = Σ (`work_fraction` × 0.5) trên từng nửa ngày → công thực đi làm.
- **Mỗi cột nghỉ** (Phép / Ốm / Thai sản / Tai nạn LĐ / Nghỉ bù / Không lương) = Σ
  (1 − `work_fraction`) × 0.5 của các nửa ngày có `category` tương ứng.
- Ví dụ 1/2P: worked 0.5 → Công +0.5; leave 0.5, category Phép → Phép +0.5. NN: Công +0.5,
  nửa còn lại là vắng không lương (không cộng vào cột nghỉ nào).

## Phase 0 — Leave Type anchors (VN law)

Standardize/ensure these Leave Types exist with correct flags so codes can point at them
(all `is_lwp=0` unless noted): Nghỉ phép năm, Nghỉ ốm, Nghỉ chăm con ốm, Nghỉ thai sản,
**Nghỉ tai nạn lao động** (new 2026-07-08), Nghỉ bù (`is_compensatory=1`), Nghỉ không lương
(`is_lwp=1`). Exported as fixtures. **Resolved:** create-if-missing only, never modify existing
live Leave Types (OQ#4). BHXH-funded leaves (Ô/Cô/TS/T) stay `is_lwp=0` so company payroll is
unchanged — BHXH benefit computed outside this system (user decision 2026-07-08).

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

## Open Questions — RESOLVED

1. **Baseline** — build continues on `feat/skip-attendance-diag`; unrelated dirty files left alone,
   staging is per-task/surgical.
2. **Branch base** — `feat/skip-attendance-diag` (MVP already lives here).
3. **The VN symbol table** — CONFIRMED 2026-07-08 (see "Authoritative symbol set" above).
4. **Leave Types** — create-if-missing only; never modify existing. Names as listed in Phase 0.
5. **Run scope (this round)** — full symbol set end-to-end: code + fixtures + tests +
   `bench migrate` on dev site `miyano` + commit. No production deploy.
6. **CN/NL/N** — calendar markers rendered by the report (no Attendance records, no schema change).

## Success Criteria (MVP)

- [x] `Attendance Code` DocType + confirmed VN symbols (13) seeded via fixtures.
- [x] Two-way bridge sets native fields correctly (incl. single half-day codes); `custom_cong` = Σ worked work_fraction.
- [x] Payroll-invariance test passes (payment_days/absent_days/LWP unchanged) — full-day + half-day scenarios.
- [x] "Bảng chấm công tháng" report renders a correct monthly sheet: symbols per day, CN/NL/N calendar
      markers, per-category totals. (Print Format still deferred to Phase 5 submittable sheet.)
- [x] All new work reversible via `git revert`; fixtures additive; verified on dev site `miyano` (27 tests green).
