# Plan: "Bảng Công Tháng" submittable DocType + VN print form (Phase 5a)

Derived from `spec/bang-cong-thang-doctype.md`. Branch: `feat/skip-attendance-diag`.
Read-only snapshot feature — additive, git-revertable, never writes Attendance → no payroll risk.
Tests run via the session rollback harness (NEVER `bench run-tests` on `miyano`). One commit per task.

- [x] Task 1: `get_sheet_rows(filters)` shared refactor in the report — semantic rows
      `{employee, employee_name, days:{d->sym}, totals:{cat->float}}`; report `get_data` consumes it.
      Parity locked by existing report tests + a structural test. Files: report `.py` + its test.
- [x] Task 2: `Bang Cong Thang Detail` child DocType (istable): employee, employee_name, d01..d31,
      8 category totals. Files: `hrms/hr/doctype/bang_cong_thang_detail/*`.
- [x] Task 3: `Bang Cong Thang` parent DocType (is_submittable): company/department/month/year/
      from_date/to_date/prepared_by/remarks/employees/amended_from + `validate` (derive dates,
      no-duplicate guard). Files: `hrms/hr/doctype/bang_cong_thang/*` (json/py/__init__).
- [x] Task 4: `populate_from_attendance()` (whitelist, draft-only) + client button (`.js`) that fills
      child rows from `get_sheet_rows`. Files: `bang_cong_thang.py`/`.js` + test.
- [x] Task 5: Lifecycle + read-only/payroll-neutral + no-duplicate tests (submit freezes; create+
      populate+submit writes 0 Attendance & payroll unchanged; duplicate raises). Files: test only.
- [x] Task 6: Print Format "Bảng Công Tháng" (grid d01..dN + 8 totals + symbol legend + 2 sign boxes:
      Người chấm công, Phòng Nhân sự). Files: `hrms/hr/print_format/bang_cong_thang/*` + render test.
- [x] Task 7: Permissions/fixtures + `bench migrate`/reload on `miyano` + end-to-end verify + docs/plan.

**Stop-and-ask triggers:** none expected (additive, read-only). Deploy to production remains ask-first.
