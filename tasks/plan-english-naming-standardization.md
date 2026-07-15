# English Naming Standardization — Implementation Plan (rename VN-romanized doctypes/fields I authored)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development / executing-plans.
> **HIGH-RISK schema migration on shipped doctypes.** DEV-only this round; the prod rename patch run is a
> separate signed-off deploy. Approved rename map + VN-display-via-translations, 2026-07-15.

**Goal:** Rename the VN-romanized DocTypes/reports/fields (created in this project) to **English internal
names**, keeping **Vietnamese UI** via field `label`s + a `vi.csv` translation for DocType/report titles.

**Architecture:** Field renames via `rename_field(doctype, old, new)` (from
`frappe.model.utils.rename_field`); DocType/report renames via `frappe.rename_doc("DocType"|"Report", old,
new, force=True)` — all in **`[pre_model_sync]`** patches so the DB table/links are renamed *before* the
renamed JSON syncs. Every task: edit code → add patch + `patches.txt` entry → `bench migrate` (dev) →
confirm app loads + tests green → commit. One doctype/field-group per task = clean rollback points.

**Tech Stack:** Frappe/ERPNext HRMS v15. Tests via the rollback harness (`scratch/run_test.sh`).

## Global Constraints

- **DEV-only.** Do NOT run against prod. Patches are authored so a later prod migrate performs the rename,
  but that migrate is a separate, signed-off step (prod may hold signed Bảng Công / real Công Tác trips).
- **App must keep loading.** After each doctype rename: `bench --site miyano migrate` must succeed and
  `bench --site miyano execute frappe.ping` (or a trivial import) must work before committing. If a rename
  leaves the app unimportable, fix or revert that task before proceeding (debugging-and-error-recovery).
- **Labels stay Vietnamese.** Only `fieldname`/DocType `name` change; every `label` is preserved.
- **Stage only each task's files** (never `git add -A`).
- **Reversible:** code via `git revert`; the dev DB rename is undone by the inverse rename if needed.

## Approved rename map

DocTypes/report: `Bang Cong Thang`→`Monthly Attendance Sheet`; `Bang Cong Thang Detail`→
`Monthly Attendance Sheet Detail`; `Cong Tac`→`Business Trip`; `Cong Tac Traveler`→`Business Trip Traveler`;
report `Bang Cham Cong Thang`→`Monthly Attendance Report`.

Fields — Attendance: `custom_cong`→`custom_work_credit`. Monthly Attendance Sheet Detail:
`cong`→`work_days`, `phep`→`annual_leave`, `om`→`sick_leave`, `thai_san`→`maternity_leave`,
`tnld`→`work_accident_leave`, `nghi_bu`→`comp_off`, `khong_luong`→`unpaid_leave`, `vang`→`absent`.
(`personal_leave` already English.)

---

## Task 1: Rename the 8 sheet-detail total fields

**Files:** `hrms/hr/doctype/bang_cong_thang_detail/bang_cong_thang_detail.json` (field_order + `fieldname`,
keep labels); `hrms/hr/doctype/bang_cong_thang/bang_cong_thang.py` (`category_field` mapping values);
`hrms/hr/print_format/bang_cong_thang/bang_cong_thang.json` (`row.<old>`→`row.<new>`);
`hrms/hr/doctype/bang_cong_thang/test_bang_cong_thang.py` (`row.cong`/`row.phep`→new);
`hrms/patches/v15_0/rename_sheet_detail_fields.py` (new) + `hrms/patches.txt`.

- [ ] **Step 1:** Update `test_bang_cong_thang.py` assertions to the new field names (`row.work_days`,
  `row.annual_leave`). Run → FAIL (fields still old). `bash scratch/run_test.sh "hrms.hr.doctype.bang_cong_thang.test_bang_cong_thang"`
- [ ] **Step 2:** In `bang_cong_thang_detail.json` rename the 8 `fieldname`s in both `field_order` and the
  field defs (labels unchanged). In `bang_cong_thang.py` update `category_field` values. In the print
  format replace `row.cong`→`row.work_days`, `row.phep`→`row.annual_leave`, `row.om`→`row.sick_leave`,
  `row.thai_san`→`row.maternity_leave`, `row.tnld`→`row.work_accident_leave`, `row.nghi_bu`→`row.comp_off`,
  `row.khong_luong`→`row.unpaid_leave`, `row.vang`→`row.absent`.
- [ ] **Step 3:** Create `hrms/patches/v15_0/rename_sheet_detail_fields.py`:

```python
import frappe
from frappe.model.utils.rename_field import rename_field

RENAMES = {
	"cong": "work_days",
	"phep": "annual_leave",
	"om": "sick_leave",
	"thai_san": "maternity_leave",
	"tnld": "work_accident_leave",
	"nghi_bu": "comp_off",
	"khong_luong": "unpaid_leave",
	"vang": "absent",
}


def execute():
	if not frappe.db.exists("DocType", "Bang Cong Thang Detail"):
		return
	for old, new in RENAMES.items():
		if old in frappe.db.get_table_columns("Bang Cong Thang Detail"):
			rename_field("Bang Cong Thang Detail", old, new)
```

Add to `hrms/patches.txt` under `[pre_model_sync]`: `hrms.patches.v15_0.rename_sheet_detail_fields #2026-07-15`
- [ ] **Step 4:** `bench --site miyano migrate` → then `bash scratch/run_test.sh "hrms.hr.doctype.bang_cong_thang.test_bang_cong_thang"` and the report test → GREEN.
- [ ] **Step 5:** Commit (staging the 5 files above).

---

## Task 2: Rename `custom_cong` → `custom_work_credit`

**Files:** `hrms/fixtures/custom_field.json` (fieldname + `name` `Attendance-custom_cong`→`Attendance-custom_work_credit`);
`hrms/hooks.py` (Custom Field filter name); `hrms/hr/doctype/attendance/attendance.py` (bridge: all `self.custom_cong`);
`hrms/hr/report/bang_cham_cong_thang/bang_cham_cong_thang.py` (any `custom_cong` select/use);
test files referencing `custom_cong` (`test_attendance_code_bridge.py`, `test_bang_cong_thang.py`,
`test_vn_half_day_classifier.py`); `hrms/patches/v15_0/rename_custom_cong.py` + `patches.txt`.

- [ ] **Step 1:** `grep -rn "custom_cong" hrms/ --include=*.py --include=*.json | grep -v __pycache__` — enumerate every ref.
- [ ] **Step 2:** Update all test assertions `.custom_cong`→`.custom_work_credit`. Run bridge + classifier + sheet tests → FAIL.
- [ ] **Step 3:** Rename in `attendance.py` (bridge sets `self.custom_work_credit`), the report, the fixture
  JSON (`fieldname` + `name`), and `hooks.py` filter name.
- [ ] **Step 4:** Patch `hrms/patches/v15_0/rename_custom_cong.py`:

```python
import frappe
from frappe.model.utils.rename_field import rename_field


def execute():
	if "custom_cong" in frappe.db.get_table_columns("Attendance"):
		rename_field("Attendance", "custom_cong", "custom_work_credit")
```

Add under `[pre_model_sync]`: `hrms.patches.v15_0.rename_custom_cong #2026-07-15`
- [ ] **Step 5:** `bench migrate` → confirm Custom Field `Attendance-custom_work_credit` exists and
  `Attendance-custom_cong` is gone (`frappe.db.exists`); run bridge + classifier + sheet + fixtures + payroll-invariance tests → GREEN.
- [ ] **Step 6:** Commit.

---

## Task 3: Rename report `Bang Cham Cong Thang` → `Monthly Attendance Report`

**Files:** `git mv hrms/hr/report/bang_cham_cong_thang hrms/hr/report/monthly_attendance_report` and rename
the `.py/.js/.json/test_*` basenames; update the report JSON `name`+`report_name`; update the consumer
import in `hrms/hr/doctype/bang_cong_thang/bang_cong_thang.py` (`from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import get_sheet_rows`)
and the report's own test import; patch + `patches.txt`.

- [ ] **Step 1:** `git mv` the folder + files (`bang_cham_cong_thang.*`→`monthly_attendance_report.*`, incl. `test_*`).
- [ ] **Step 2:** In the report `.json` set `"name"` and `"report_name"` to `Monthly Attendance Report`;
  keep `ref_doctype`. Update `module` if scrubbed. Update the `.js` `frappe.query_reports["Monthly Attendance Report"]` key.
- [ ] **Step 3:** Update imports: the `get_sheet_rows` import in `bang_cong_thang.py` + the test file's own import path.
- [ ] **Step 4:** Patch `hrms/patches/v15_0/rename_bang_cham_cong_thang_report.py`:

```python
import frappe


def execute():
	if frappe.db.exists("Report", "Bang Cham Cong Thang") and not frappe.db.exists(
		"Report", "Monthly Attendance Report"
	):
		frappe.rename_doc("Report", "Bang Cham Cong Thang", "Monthly Attendance Report", force=True)
```

Add under `[pre_model_sync]`: `hrms.patches.v15_0.rename_bang_cham_cong_thang_report #2026-07-15`
- [ ] **Step 5:** `bench migrate` → app loads; run the renamed report test + `test_bang_cong_thang` (uses get_sheet_rows) → GREEN.
- [ ] **Step 6:** Commit.

---

## Task 4: Rename `Bang Cong Thang` (+Detail) → `Monthly Attendance Sheet` (+Detail)

**Files:** `git mv` folders `bang_cong_thang`→`monthly_attendance_sheet`, `bang_cong_thang_detail`→
`monthly_attendance_sheet_detail`; rename basenames + controller classes (`BangCongThang`→`MonthlyAttendanceSheet`,
`BangCongThangDetail`→`MonthlyAttendanceSheetDetail`); JSON `name`+child-table field `options`+`amended_from`
options; print format folder `hrms/hr/print_format/bang_cong_thang` + its `doc_type`; test imports; patch + `patches.txt`.

- [ ] **Step 1:** `git mv` both doctype folders + files; rename the print-format folder + set its `doc_type` to `Monthly Attendance Sheet`.
- [ ] **Step 2:** Update JSON `name` for both; in the parent, the `employees` Table field `options`→`Monthly Attendance Sheet Detail` and `amended_from` options→`Monthly Attendance Sheet`; rename controller classes + `test_*` imports/paths.
- [ ] **Step 3:** Patch `hrms/patches/v15_0/rename_bang_cong_thang_doctypes.py` (child first, then parent):

```python
import frappe


def execute():
	pairs = [
		("Bang Cong Thang Detail", "Monthly Attendance Sheet Detail"),
		("Bang Cong Thang", "Monthly Attendance Sheet"),
	]
	for old, new in pairs:
		if frappe.db.exists("DocType", old) and not frappe.db.exists("DocType", new):
			frappe.rename_doc("DocType", old, new, force=True)
	# print format attached to the renamed doctype
	if frappe.db.exists("Print Format", "Bang Cong Thang"):
		frappe.db.set_value("Print Format", "Bang Cong Thang", "doc_type", "Monthly Attendance Sheet")
```

Add under `[pre_model_sync]`: `hrms.patches.v15_0.rename_bang_cong_thang_doctypes #2026-07-15`
- [ ] **Step 4:** `bench migrate` → app loads; run `test_bang_cong_thang` (path now `monthly_attendance_sheet`) + report test → GREEN.
- [ ] **Step 5:** Commit.

---

## Task 5: Rename `Cong Tac` (+Traveler) → `Business Trip` (+Traveler) — highest risk

**Files:** `git mv` folders `cong_tac`→`business_trip`, `cong_tac_traveler`→`business_trip_traveler`; rename
basenames + classes (`CongTac`→`BusinessTrip`, `CongTacTraveler`→`BusinessTripTraveler`); JSON `name`+child
`options`+`amended_from`; the Workflow `Cong Tac Approval` `document_type`→`Business Trip`
(`hrms/hr/workflow/cong_tac_approval/*.json` + `hrms/patches/v15_0/setup_cong_tac_workflow.py::ensure_workflow`);
Expense Claim `custom_business_trip` options in `hrms/fixtures/custom_field.json`→`Business Trip`; any
Notification/print/controller refs (`grep -rn "Cong Tac"`); test files; patch + `patches.txt`.

- [ ] **Step 1:** `grep -rn "Cong Tac" hrms/ --include=*.py --include=*.json --include=*.js | grep -v __pycache__` — enumerate all 34 refs.
- [ ] **Step 2:** `git mv` both folders + files; rename classes + `test_*`; update every code ref from Step 1
  EXCEPT the workflow *record name* `Cong Tac Approval` (a record name, out of scope) — but DO set its
  `document_type` to `Business Trip` (workflow JSON + `ensure_workflow`). Update `custom_business_trip`
  fixture `options`→`Business Trip`.
- [ ] **Step 3:** Patch `hrms/patches/v15_0/rename_cong_tac_doctypes.py`:

```python
import frappe


def execute():
	for old, new in [
		("Cong Tac Traveler", "Business Trip Traveler"),
		("Cong Tac", "Business Trip"),
	]:
		if frappe.db.exists("DocType", old) and not frappe.db.exists("DocType", new):
			frappe.rename_doc("DocType", old, new, force=True)
	# workflow doc points at the renamed doctype
	if frappe.db.exists("Workflow", "Cong Tac Approval"):
		frappe.db.set_value("Workflow", "Cong Tac Approval", "document_type", "Business Trip")
	# Expense Claim link option (rename_doc updates it, but pin it for idempotency)
	if frappe.db.exists("Custom Field", "Expense Claim-custom_business_trip"):
		frappe.db.set_value(
			"Custom Field", "Expense Claim-custom_business_trip", "options", "Business Trip"
		)
```

Add under `[pre_model_sync]`: `hrms.patches.v15_0.rename_cong_tac_doctypes #2026-07-15`
- [ ] **Step 4:** `bench migrate` → app loads; run `test_cong_tac` (path now `business_trip`) + a workflow smoke
  (`frappe.db.get_value("Workflow","Cong Tac Approval","document_type") == "Business Trip"`) → GREEN.
- [ ] **Step 5:** Commit.

---

## Task 6: VN translations + full regression + docs

**Files:** `hrms/translations/vi.csv` (append DocType/report title translations); `tasks/plan-english-naming-standardization.md` (tick).

- [ ] **Step 1:** Append to `hrms/translations/vi.csv` (create if absent) so HR sees VN titles:
  `Monthly Attendance Sheet,Bảng Công Tháng` · `Monthly Attendance Sheet Detail,Chi tiết Bảng Công Tháng` ·
  `Business Trip,Công Tác` · `Business Trip Traveler,Người đi công tác` · `Monthly Attendance Report,Bảng chấm công tháng`.
  (Verify the file's column format from any existing `apps/*/*/translations/vi.csv`; match it.)
- [ ] **Step 2:** `bench migrate` + clear cache; full regression sweep (all modules touched across A/B + the renamed ones) → all GREEN.
- [ ] **Step 3:** Tick boxes; commit docs.

---

## Self-Review

**Coverage:** every approved rename has a task (fields T1–T2, report T3, sheet doctypes T4, trip doctypes T5,
translations T6). Patches are `[pre_model_sync]` so DB precedes JSON sync. **Risk order:** contained field
renames first; app-breaking doctype renames last, each gated by a migrate+app-load+test check with a
per-task commit rollback point. **Prod:** patches authored but their prod migrate is a separate sign-off.
**Type consistency:** new fieldnames/doctype names used identically across JSON, controllers, print, tests,
patches. Workflow *record* name `Cong Tac Approval` intentionally kept (record name, not doctype/field).
