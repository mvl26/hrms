# Spec: "Bảng Công Tháng" — submittable monthly timekeeping sheet + VN print form (Phase 5a)

> Status: **DRAFT for approval.** Extends the shipped VN attendance-code feature
> (`spec/attendance-code-timekeeping.md`, MVP + full 13-symbol set + auto-flows + backfill DONE).
> This spec covers the Phase-5 submittable document and its paper print form only. Business Trip
> DocType and geofence check-in remain out of scope (separate future specs). Saved under `spec/`
> per this repo's convention (same folder as the base spec; discoverable by `/build auto`).

## Objective

Give HR an **official, submittable, printable monthly timekeeping sheet** ("Bảng công tháng") per
đơn vị — a frozen snapshot of a month's attendance (mã công per day + category totals per employee),
approved via draft→submit and printed on a Vietnamese paper form with sign-off boxes for archival.

The existing **report** "Bảng chấm công tháng" is a *live, read-only view*. This DocType is the
*frozen, signed, archival record* for a specific (đơn vị, tháng). They coexist and share one
derivation core — the DocType never re-implements timekeeping logic.

**Target users:** HR User / HR Manager (create, populate, submit, print); đơn vị heads & HR sign the
printed form.

## Locked design decisions (confirmed 2026-07-08)

1. **Scope = 1 document / đơn vị / tháng**, listing ALL employees as child rows (nhân viên × ngày).
   Matches the VN paper form; one sign-off per đơn vị.
2. **Read-only snapshot from Attendance.** A "Lấy dữ liệu chấm công" button aggregates the month's
   Attendance into child rows. Corrections are made in Attendance, then re-pulled. The document
   **NEVER writes back to Attendance** → provably payroll-neutral (it only reads).
3. **Draft → Submit (docstatus)** for approval; signatures are on the printed form (no Frappe Workflow).
4. **Print sign-off boxes: "Người chấm công" (người lập biểu) + "Phòng Nhân sự".** (No dept-head /
   director boxes.)

## Data model

### Parent — `Bang Cong Thang` (label "Bảng Công Tháng"), `is_submittable = 1`

| field | type | notes |
|---|---|---|
| `naming_series` | Select | default `BCT-.YYYY.-.#####` |
| `company` | Link Company | reqd |
| `department` | Link Department | optional — scope to a phòng ban |
| `include_company_descendants` | Check | default 1 (mirror report filter) |
| `year` | Int | reqd |
| `month` | Select 1–12 | reqd |
| `from_date` / `to_date` | Date | read-only, computed from month/year |
| `prepared_by` | Link User | default = session user (name on "Người chấm công" box) |
| `remarks` | Small Text | optional |
| `employees` | Table → `Bang Cong Thang Detail` | the grid |
| `amended_from` | Link Bang Cong Thang | read-only (required for submittable) |

- **Naming** by series; a `validate` guard forbids a second **draft/submitted** sheet for the same
  (company, department, month, year).
- `from_date`/`to_date` are derived in `validate` (first/last day of month).

### Child — `Bang Cong Thang Detail`, `istable = 1`

| field | type | notes |
|---|---|---|
| `employee` | Link Employee | |
| `employee_name` | Data | |
| `d01` … `d31` | Data, read-only | daily symbol (X, P, 1/2P, Ô, CN, NL, N, V, …); empty for days past month length |
| `cong`, `phep`, `om`, `thai_san`, `tnld`, `nghi_bu`, `khong_luong`, `vang` | Float, read-only, precision 2 | the 8 fixed category totals |

- The 8 category columns are **fixed** (mirror the shipped Attendance-Code categories). Adding a new
  category later needs a schema field + a mapping entry — documented, not dynamic.

## Populate logic (the one moving part)

`Bang Cong Thang.populate_from_attendance()` (`@frappe.whitelist`, **draft-only**):
1. Derive `from_date`/`to_date` from month/year.
2. Call the **shared** `get_sheet_rows(filters)` (see refactor) → list of
   `{employee, employee_name, days: {1: "X", …}, totals: {"Công": 1.5, "Phép": 0.5, …}}`.
3. Clear `employees`, then append one child row per result: map `days[n] → d{n:02d}`, and each
   category total → its fixed field (`Công→cong`, `Phép→phep`, `Ốm→om`, `Thai sản→thai_san`,
   `Tai nạn LĐ→tnld`, `Nghỉ bù→nghi_bu`, `Không lương→khong_luong`, `Vắng→vang`).
4. Never touches Attendance.

### Shared refactor (no logic duplication)

Extract `get_sheet_rows(filters) -> list[dict]` into the report module
`hrms/hr/report/bang_cham_cong_thang/bang_cham_cong_thang.py`, built from the existing
`get_employees` / `get_attendances` / `get_holidays` / `get_code_map` / `_resolve_day` helpers.
Refactor the report's `get_data` to consume `get_sheet_rows` too, so the report and the DocType
produce identical cells/totals by construction (locked by a parity test).

## Lifecycle

- **Draft:** header editable; "Lấy dữ liệu chấm công" button (re)populates child rows (read-only in grid).
- **Submit:** freezes the snapshot (docstatus 1). No side effects on Attendance/payroll.
- **Cancel / Amend:** standard docstatus 2 / `amended_from`.
- **No-duplicate** guard on (company, department, month, year) among docstatus < 2.

## Print Format — "Bảng Công Tháng" (paper form)

Standard Print Format (Jinja/HTML, landscape, small font), attached to `Bang Cong Thang`:
- **Header:** company name (+ logo via letterhead), title "BẢNG CHẤM CÔNG THÁNG {month}/{year}",
  đơn vị/phòng ban, kỳ công {from_date}–{to_date}.
- **Grid:** STT · Mã NV · Họ tên · d01…d{days-in-month} · Công · Phép · Ốm · Thai sản · Tai nạn LĐ ·
  Nghỉ bù · Không lương · Vắng. Only real days of the month are rendered (28–31).
- **Legend:** the mã-công symbol table (code → nghĩa) pulled from `Attendance Code`.
- **Footer:** date line "…, ngày … tháng … năm …" + **two sign boxes: "NGƯỜI CHẤM CÔNG"**
  (shows `prepared_by`) **and "PHÒNG NHÂN SỰ"**.

## Project structure (files to create)

```
hrms/hr/doctype/bang_cong_thang/            bang_cong_thang.json/.py/.js/__init__.py/test_*.py
hrms/hr/doctype/bang_cong_thang_detail/     bang_cong_thang_detail.json/.py/__init__.py
hrms/hr/print_format/bang_cong_thang/       bang_cong_thang.json  (is_standard "Yes")
hrms/hr/report/bang_cham_cong_thang/bang_cham_cong_thang.py   (+ get_sheet_rows refactor)
```
Permissions: System Manager, HR Manager, HR User (create/read/write/submit/cancel/print).

## Code style

Follow the shipped feature's conventions: ASCII module/doctype folder names (`bang_cong_thang`) with
VN labels via the JSON `label`; tab indentation; typed helper signatures; docstrings explaining the
"why" (snapshot / read-only / payroll-neutral). Reuse report helpers — do not re-derive timekeeping.

## Testing strategy (run via the session's rollback harness — NEVER `bench run-tests` on `miyano`)

- **Parity:** `get_sheet_rows` yields the same cells/totals as the report for the shipped scenarios
  (X, P, X/P half-day, NN/1/2P/1/2K, CN/NL/N, Absent→V).
- **Populate:** seed a month of Attendance → create sheet → `populate_from_attendance()` → assert child
  `d0X` symbols + the 8 category totals; correct day count per month.
- **Read-only / payroll-neutral:** snapshot Attendance count + a Salary Slip figure before; create +
  populate + submit the sheet; assert **Attendance rows and payroll figures unchanged** (the doc never writes).
- **Lifecycle:** submit freezes; no-duplicate (company, department, month, year) guard raises; amend works.
- **Populate blocked after submit** (draft-only).

## Boundaries

- **Always:** read-only snapshot; reuse the report's derivation core; migrate normally; VN labels + ASCII folders.
- **Ask-first:** deploying fixtures/print format to **production** sites (per the base feature's rule).
- **Never:** write back to Attendance from this document; change payroll or native status semantics;
  re-implement timekeeping logic; add write-back entry (explicitly rejected in decision #2).

## Acceptance criteria

- [ ] `Bang Cong Thang` (submittable) + `Bang Cong Thang Detail` DocTypes install; permissions set.
- [ ] "Lấy dữ liệu chấm công" populates child rows (d01..dN + 8 totals) identical to the report; draft-only.
- [ ] Submitting/creating the sheet writes **zero** Attendance rows; payroll figures unchanged (test-proven).
- [ ] No-duplicate guard on (company, department, month, year); from/to dates auto-derived.
- [ ] Print Format renders the grid + symbol legend + the two sign boxes (Người chấm công, Phòng Nhân sự).
- [ ] All reversible via `git revert`; verified on dev `miyano` via the rollback harness.

## Out of scope (future specs)

Business Trip DocType; geofence check-in; Frappe Workflow multi-step approval; write-back entry from the
sheet; dynamic category columns; Phase 4 rotating multi-shift.

## Suggested task breakdown (for `/build auto`)

1. `get_sheet_rows` shared refactor in the report (+ parity test).
2. `Bang Cong Thang Detail` child DocType.
3. `Bang Cong Thang` parent DocType (schema + validate: dates, no-duplicate, amended_from).
4. `populate_from_attendance()` + client button (`.js`) + populate/parity tests.
5. Lifecycle + read-only/payroll-neutral + no-duplicate tests.
6. Print Format (grid + legend + 2 sign boxes).
7. Permissions/fixtures + `bench migrate` on `miyano` + end-to-end verify + docs/plan update.
