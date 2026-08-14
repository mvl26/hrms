# Plan — Nhân viên miễn chấm công (full công tự sinh)

> **Cho người/agent thực thi:** dùng `superpowers:subagent-driven-development` hoặc
> `superpowers:executing-plans`, làm tuần tự T1 → T11, mỗi task kết thúc bằng **một commit**.
> Các bước dùng checkbox `- [ ]` để bám tiến độ.

**Spec:** `docs/spec/attendance-exempt-employees.md` (đọc trước khi bắt đầu — plan này lập luận từ spec).
Nhánh: `feat/skip-attendance-diag`.

**Goal:** người không quẹt thẻ theo giờ cố định (giám đốc, giờ linh hoạt) **tự động đủ công mỗi
ngày làm việc** (mã `X`), trong khi ngày đi công tác vẫn ra **CT** và ngày nghỉ phép vẫn ra **P**.

**Architecture:** một cờ trên `Employee`; một module `hrms/hr/attendance_exempt.py` giữ toàn bộ luật
("ai được miễn / ngày nào / sinh ra cái gì"); bốn điểm móc mỏng vào tuyến chấm công sẵn có chỉ *gọi*
vào module đó; Công Tác được sửa để ghi đè được ngày `X` tự sinh. Mã công là đầu vào duy nhất —
`status` / `leave_type` / `work_credit` do cầu nối `apply_attendance_code_bridge` suy ra.

**Tech Stack:** Frappe v15 + ERPNext + HRMS; custom field qua `fixtures`; scheduler
`hourly_long`; test bằng `unittest` + `FrappeTestCase` + `PerTestRollback` chạy qua harness rollback.

## Global Constraints

- **TUYỆT ĐỐI KHÔNG** `bench --site miyano run-tests` — chạy qua harness rollback (mục dưới).
- Payroll chỉ đọc `status` / `leave_type` / `half_day_status`. Trước khi kết luận xong việc phải có
  **T10 xanh**: người KHÔNG có cờ giữ nguyên `payment_days` / `absent_days` / LWP.
- **Ask-first (DỪNG chờ ký duyệt):** `bench --site miyano migrate` (nạp fixtures lên site thật),
  tick cờ cho người thật, chạy `generate_for_month` trên dữ liệu thật.
- Lint ruff qua pre-commit: **tab**, **nháy kép**, dòng ≤ 110, py310. Binary dùng được:
  `~/.cache/pre-commit/repooq35yk6d/py_env-python3.12/bin/ruff` (mới hơn bản repo ghim — chỉ so với
  HEAD, đừng format lan man).
- Conventional Commits, scope `(hr)`. **Chỉ `git add` đúng file mình đụng** (cây làm việc đang có
  `docs/audit-roadmap-2026-07-16.md` sửa dở của việc khác — không đụng vào).
- Helper trên `Document` **không** đặt tên bắt đầu bằng `_` (bị `__getattr__` nuốt → trả `None`).
- Đổi fixtures phải sửa **cả** `hrms/fixtures/custom_field.json` **và** bộ lọc `fixtures` trong
  `hooks.py:292` — `hrms/tests/test_setup_vn_defaults.py` bắt lệch.
- Tên doctype/fieldname **tiếng Anh**, label tiếng Việt.
- Additive + `git revert`-able: không sửa công thức lương, không viết lại bản ghi lịch sử.

## Chạy test (harness rollback)

Tạo một lần ở T1, mọi bước "Run" sau đó gọi lại:

`$SCRATCH/run_test.sh` (scratchpad của phiên):

```bash
#!/usr/bin/env bash
# Usage: bash $SCRATCH/run_test.sh "<dotted.module>[.TestClass.test_method]"
cd /home/miyano/frappe-bench
cat > /tmp/hrms_harness.py <<'PY'
import frappe, unittest, os
frappe.flags.in_test = True
_c = frappe.db.commit
frappe.db.commit = lambda *a, **k: None          # không bao giờ ghi thật vào DB site
WATCH = ["Attendance", "Employee", "Employee Checkin", "Leave Application", "Shift Type",
         "Holiday List", "Attendance Code", "Monthly Attendance Sheet", "Business Trip",
         "Salary Slip", "Shift Assignment", "Attendance Request"]
def counts():
    return {d: frappe.db.count(d) for d in WATCH}
class R(unittest.TextTestResult):
    def startTest(self, t):
        frappe.db.savepoint("tc"); super().startTest(t)
    def stopTest(self, t):
        super().stopTest(t); frappe.db.rollback(save_point="tc")
before = counts()
try:
    s = unittest.TestLoader().loadTestsFromName(os.environ["HARNESS_TARGET"])
    res = unittest.TextTestRunner(resultclass=R, verbosity=2).run(s)
    print("RESULT:", "OK" if res.wasSuccessful() else "FAIL",
          "errors", len(res.errors), "fails", len(res.failures))
finally:
    frappe.db.commit = _c
    frappe.db.rollback()
    after = counts()
    leaks = {d: (before[d], after[d]) for d in WATCH if before[d] != after[d]}
    print("HARNESS_LEAK_DETECTED" if leaks else "HARNESS_NO_LEAK", leaks or "")
PY
HARNESS_TARGET="$1" bench --site miyano console <<'PY'
exec(compile(open("/tmp/hrms_harness.py").read(), "/tmp/hrms_harness.py", "exec"), {"__name__": "__main__"})
PY
```

Ba điều **bắt buộc** nhớ (đã sập bẫy thật):

1. Nạp bằng `exec(compile(open(path)...))` — **không** pipe cả file vào `bench console` (IPython
   hiểu sai dòng trống trong khối lệnh) và **không** `exec(open().read())` trần (globals ≠ locals →
   `NameError`).
2. Harness **không an toàn 100%**: một câu DDL gây implicit commit trên MariaDB sẽ chốt mọi thứ
   đang dở. Vì thế mới có `HARNESS_NO_LEAK`. Thấy `HARNESS_LEAK_DETECTED` thì **dừng, dọn tay ngay**
   (`frappe.get_all(dt, filters={"creation": [">", "<mốc giờ>"]})`).
3. **Không insert Custom Field trong test** (đó chính là DDL). Field mới lên site bằng `migrate` ở
   T1, test chỉ đọc.

**Baseline test đỏ sẵn** (không phải do mình): 9 error `_Test Company` ở `hrms.hr.tests.test_working_hours`,
15 error thiếu role `WFC *` ở `business_trip`, 44 error `_Test Company` ở `test_salary_slip`. Nghi
ngờ mình làm vỡ thì `git stash` rồi chạy lại đúng module đó.

---

## T1: Fixtures — 3 custom field + bộ lọc `hooks.py`

**Files:**
- Modify: `hrms/fixtures/custom_field.json` (thêm 3 bản ghi)
- Modify: `hrms/hooks.py` (bộ lọc `fixtures` → `Custom Field` → danh sách `name in [...]`)
- Test: `hrms/hr/tests/test_attendance_exempt.py` (tạo mới)

**Interfaces:**
- Produces: 3 Custom Field — `Employee-custom_exempt_from_checkin` (Check),
  `Employee-custom_exempt_from_checkin_from` (Date), `Attendance-custom_auto_filled` (Check,
  `read_only=1`). Mọi task sau đọc đúng ba tên field này.

- [ ] **Bước 1: Dựng harness** — ghi `$SCRATCH/run_test.sh` đúng nội dung ở mục trên, `chmod +x`.

- [ ] **Bước 2: Viết test đỏ** — `hrms/hr/tests/test_attendance_exempt.py`:

```python
# Copyright (c) 2026, Miyano Việt Nam.
"""Miyano — nhân viên miễn chấm công: ngày làm việc tự sinh đủ công (mã X).

Chạy qua harness rollback (KHÔNG `bench --site miyano run-tests`). Test chỉ ĐỌC custom field,
không bao giờ insert Custom Field trong test (DDL → implicit commit → rò rỉ vào site thật).
"""

import json
import os

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.tests.isolation import PerTestRollback

_CF = os.path.join(frappe.get_app_path("hrms"), "fixtures", "custom_field.json")

EXEMPT_FIELDS = {
	"Employee-custom_exempt_from_checkin": ("Employee", "Check"),
	"Employee-custom_exempt_from_checkin_from": ("Employee", "Date"),
	"Attendance-custom_auto_filled": ("Attendance", "Check"),
}


def custom_fields():
	with open(_CF, encoding="utf-8") as f:
		return {c["name"]: c for c in json.load(f)}


class TestExemptFixtures(PerTestRollback, FrappeTestCase):
	"""E1 — ba custom field của tính năng có trong fixtures VÀ trong bộ lọc hooks."""

	def test_fields_defined_in_fixtures(self):
		defined = custom_fields()
		for name, (dt, fieldtype) in EXEMPT_FIELDS.items():
			with self.subTest(name=name):
				cf = defined.get(name)
				self.assertIsNotNone(cf, f"thiếu Custom Field {name} trong fixtures")
				self.assertEqual(cf["dt"], dt)
				self.assertEqual(cf["fieldtype"], fieldtype)

	def test_auto_filled_is_read_only(self):
		# cờ nguồn gốc do máy ghi — người dùng sửa tay là mở đường cho Công Tác đè nhầm dữ liệu thật
		self.assertEqual(custom_fields()["Attendance-custom_auto_filled"]["read_only"], 1)

	def test_fields_in_hooks_fixture_filter(self):
		import hrms.hooks as hooks

		names = set()
		for entry in hooks.fixtures:
			if isinstance(entry, dict) and entry.get("dt") == "Custom Field":
				nf = (entry.get("filters") or {}).get("name")
				if isinstance(nf, list | tuple) and nf and nf[0] == "in":
					names |= set(nf[1])
		for name in EXEMPT_FIELDS:
			self.assertIn(name, names, f"{name} chưa có trong bộ lọc fixtures của hooks.py")
```

- [ ] **Bước 3: Chạy để thấy ĐỎ**

Run: `bash $SCRATCH/run_test.sh "hrms.hr.tests.test_attendance_exempt"`
Kỳ vọng: FAIL — "thiếu Custom Field Employee-custom_exempt_from_checkin trong fixtures".

- [ ] **Bước 4: Thêm 3 bản ghi vào `hrms/fixtures/custom_field.json`**

Copy nguyên khuôn của một bản ghi sẵn có (mọi khoá phải đủ, `is_system_generated: 1`), chỉ đổi các
giá trị dưới đây. Giữ file **sắp xếp theo `name`** như hiện tại.

```json
{
 "dt": "Employee",
 "fieldname": "custom_exempt_from_checkin",
 "fieldtype": "Check",
 "label": "Miễn chấm công (full công)",
 "insert_after": "default_shift",
 "description": "Không cần quẹt thẻ: mỗi ngày làm việc tự sinh đủ công (mã X). Nghỉ phép và công tác vẫn ghi bình thường.",
 "name": "Employee-custom_exempt_from_checkin",
 "modified": "2026-08-13 10:00:00.000000"
}
```

```json
{
 "dt": "Employee",
 "fieldname": "custom_exempt_from_checkin_from",
 "fieldtype": "Date",
 "label": "Miễn chấm công từ ngày",
 "insert_after": "custom_exempt_from_checkin",
 "depends_on": "eval:doc.custom_exempt_from_checkin",
 "description": "Bỏ trống = tính từ ngày vào làm.",
 "name": "Employee-custom_exempt_from_checkin_from",
 "modified": "2026-08-13 10:00:00.000000"
}
```

```json
{
 "dt": "Attendance",
 "fieldname": "custom_auto_filled",
 "fieldtype": "Check",
 "label": "Công tự sinh (miễn chấm công)",
 "insert_after": "custom_lunch",
 "read_only": 1,
 "print_hide": 1,
 "description": "Máy sinh vì nhân viên được miễn chấm công. Công Tác được phép ghi đè ngày này thành CT.",
 "name": "Attendance-custom_auto_filled",
 "modified": "2026-08-13 10:00:00.000000"
}
```

- [ ] **Bước 5: Thêm 3 tên vào bộ lọc `fixtures` trong `hooks.py`** (khối `"dt": "Custom Field"`,
  sau `"Employee-custom_social_insurance_no"`):

```python
					"Employee-custom_exempt_from_checkin",
					"Employee-custom_exempt_from_checkin_from",
					"Attendance-custom_auto_filled",
```

- [ ] **Bước 6: Chạy lại → XANH**

Run: `bash $SCRATCH/run_test.sh "hrms.hr.tests.test_attendance_exempt"` → `RESULT: OK` (3 test)
Run: `bash $SCRATCH/run_test.sh "hrms.tests.test_setup_vn_defaults"` → không có lỗi MỚI so baseline.

- [ ] **Bước 7: Commit**

```bash
git add hrms/fixtures/custom_field.json hrms/hooks.py hrms/hr/tests/test_attendance_exempt.py
git commit -m "feat(hr): field mien cham cong tren Employee + co cong tu sinh tren Attendance"
```

- [ ] **Bước 8: 🛑 GATE — xin ký duyệt rồi mới `bench --site miyano migrate`**

Field phải có thật trên site thì T2 trở đi mới test được. **Không tự chạy migrate.** Trình bày:
3 custom field additive, không đụng dữ liệu, `git revert` được. Sau khi được duyệt:

```bash
cd /home/miyano/frappe-bench && bench --site miyano migrate
```

Kiểm: `bench --site miyano execute frappe.client.get_count --args '["Employee"]'` chạy được và
`frappe.get_meta("Employee").has_field("custom_exempt_from_checkin")` trả `True`.

---

## T2: `is_exempt` + `exempt_employees` — lõi nhận diện

**Files:**
- Create: `hrms/hr/attendance_exempt.py`
- Test: `hrms/hr/tests/test_attendance_exempt.py` (thêm class)

**Interfaces:**
- Produces:
  - `EXEMPT_CODE = "X"`, `BACKFILL_DAYS = 31`
  - `exempt_fields_installed() -> bool`
  - `is_exempt(employee: str, date) -> bool`
  - `exempt_employees() -> list[frappe._dict]` — mỗi dict có `name`, `date_of_joining`,
    `relieving_date`, `custom_exempt_from_checkin_from`
- Consumes: `hrms.tests.vn_test_utils.test_employee`, `default_company` (chỉ trong test)

- [ ] **Bước 1: Viết test đỏ** — thêm vào `hrms/hr/tests/test_attendance_exempt.py`:

```python
from frappe.utils import add_days, getdate

from hrms.tests.vn_test_utils import test_employee

# Neo ở 2099: không nằm trong Holiday List nào của site → mọi ngày là ngày làm việc, và không đụng
# dữ liệu thật. Cùng quy ước với các test VN khác.
ANCHOR = getdate("2099-06-15")


def make_exempt_employee(email="exempt@miyano.test", from_date=None):
	emp = test_employee(email)
	frappe.db.set_value(
		"Employee",
		emp,
		{"custom_exempt_from_checkin": 1, "custom_exempt_from_checkin_from": from_date},
	)
	return emp


class TestIsExempt(PerTestRollback, FrappeTestCase):
	"""E2 — ai được miễn, ngày nào."""

	def test_flagged_employee_is_exempt(self):
		from hrms.hr.attendance_exempt import is_exempt

		self.assertTrue(is_exempt(make_exempt_employee(), ANCHOR))

	def test_unflagged_employee_is_not_exempt(self):
		from hrms.hr.attendance_exempt import is_exempt

		emp = test_employee("plain@miyano.test")
		frappe.db.set_value("Employee", emp, "custom_exempt_from_checkin", 0)
		self.assertFalse(is_exempt(emp, ANCHOR))

	def test_date_before_effective_date_is_not_exempt(self):
		from hrms.hr.attendance_exempt import is_exempt

		emp = make_exempt_employee(from_date=ANCHOR)
		self.assertFalse(is_exempt(emp, add_days(ANCHOR, -1)))
		self.assertTrue(is_exempt(emp, ANCHOR))

	def test_date_before_joining_is_not_exempt(self):
		from hrms.hr.attendance_exempt import is_exempt

		emp = make_exempt_employee()
		doj = frappe.db.get_value("Employee", emp, "date_of_joining")
		self.assertFalse(is_exempt(emp, add_days(getdate(doj), -1)))

	def test_date_after_relieving_is_not_exempt(self):
		from hrms.hr.attendance_exempt import is_exempt

		emp = make_exempt_employee()
		frappe.db.set_value("Employee", emp, "relieving_date", ANCHOR)
		self.assertTrue(is_exempt(emp, ANCHOR))
		self.assertFalse(is_exempt(emp, add_days(ANCHOR, 1)))

	def test_exempt_employees_lists_only_flagged_active(self):
		from hrms.hr.attendance_exempt import exempt_employees

		emp = make_exempt_employee()
		other = test_employee("plain2@miyano.test")
		frappe.db.set_value("Employee", other, "custom_exempt_from_checkin", 0)
		names = {r.name for r in exempt_employees()}
		self.assertIn(emp, names)
		self.assertNotIn(other, names)

	def test_everything_off_when_fields_not_migrated(self):
		"""Site chưa `migrate` (chưa có cột) → tính năng im lặng, hành vi cũ y nguyên."""
		from unittest.mock import patch

		import hrms.hr.attendance_exempt as ax

		emp = make_exempt_employee()
		with patch.object(ax, "exempt_fields_installed", return_value=False):
			self.assertFalse(ax.is_exempt(emp, ANCHOR))
			self.assertEqual(ax.exempt_employees(), [])
```

- [ ] **Bước 2: Chạy để thấy ĐỎ**

Run: `bash $SCRATCH/run_test.sh "hrms.hr.tests.test_attendance_exempt.TestIsExempt"`
Kỳ vọng: FAIL — `ModuleNotFoundError: hrms.hr.attendance_exempt`.

- [ ] **Bước 3: Viết `hrms/hr/attendance_exempt.py`**

```python
# Copyright (c) 2026, Miyano Việt Nam.
"""Miyano — nhân viên MIỄN CHẤM CÔNG: ngày làm việc tự sinh đủ công.

Một số người (giám đốc, người có giờ làm không cố định) không quẹt thẻ, nhưng công của họ là công
khoán theo tháng. Không có module này thì `mark_absent_for_dates_with_no_attendance` chấm họ VẮNG cả
tháng và `payment_days` bị trừ sạch.

Module giữ TOÀN BỘ luật; các điểm móc trong shift_type / attendance / business_trip chỉ gọi vào đây.
Ngày tự sinh ghi bằng MÃ CÔNG (`X`) — `status` / `leave_type` / `custom_work_credit` do cầu nối
`Attendance.apply_attendance_code_bridge` suy ra, không đặt tay (một nguồn sự thật).
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, get_last_day, getdate

from erpnext.setup.doctype.employee.employee import is_holiday

EXEMPT_CODE = "X"
# Cửa sổ lùi tối đa của lượt quét tự động — CHỐT CHẶN CHI PHÍ, không phải luật nghiệp vụ: bật cờ cho
# người vào làm từ 2020 mà không giới hạn thì mỗi giờ job lại cày sáu năm lịch sử. Bù xa hơn thì
# dùng `generate_for_month`.
BACKFILL_DAYS = 31

EMPLOYEE_FIELDS = [
	"name",
	"status",
	"company",
	"default_shift",
	"date_of_joining",
	"relieving_date",
	"custom_exempt_from_checkin",
	"custom_exempt_from_checkin_from",
]


def exempt_fields_installed() -> bool:
	"""Fixtures đã lên site chưa. Chưa thì mọi thứ im lặng và hành vi cũ y nguyên — cùng khuôn
	phòng thủ với `Attendance.get_split_shift_config`."""
	return frappe.get_meta("Employee").has_field("custom_exempt_from_checkin")


def is_exempt(employee: str, date) -> bool:
	if not employee or not exempt_fields_installed():
		return False
	row = frappe.db.get_value("Employee", employee, EMPLOYEE_FIELDS, as_dict=True)
	if not row or not cint(row.custom_exempt_from_checkin) or row.status != "Active":
		return False
	date = getdate(date)
	start = row.custom_exempt_from_checkin_from or row.date_of_joining
	if start and date < getdate(start):
		return False
	if row.relieving_date and date > getdate(row.relieving_date):
		return False
	return True


def exempt_employees() -> list:
	if not exempt_fields_installed():
		return []
	return frappe.get_all(
		"Employee",
		filters={"status": "Active", "custom_exempt_from_checkin": 1},
		fields=EMPLOYEE_FIELDS,
	)
```

- [ ] **Bước 4: Chạy lại → XANH**

Run: `bash $SCRATCH/run_test.sh "hrms.hr.tests.test_attendance_exempt"` → `RESULT: OK` (E1 + E2, 10 test),
`HARNESS_NO_LEAK`.

- [ ] **Bước 5: Commit**

```bash
git add hrms/hr/attendance_exempt.py hrms/hr/tests/test_attendance_exempt.py
git commit -m "feat(hr): lõi nhan dien nhan vien mien cham cong (is_exempt)"
```

---

## T3: `fill_full_day` — sinh một ngày công, đủ lá chắn

**Files:**
- Modify: `hrms/hr/attendance_exempt.py`
- Test: `hrms/hr/tests/test_attendance_exempt.py`

**Interfaces:**
- Produces: `fill_full_day(employee: str, date) -> str | None` — trả tên Attendance vừa tạo, hoặc
  `None` khi bỏ qua (đã có bản ghi / ngày nghỉ / kỳ đã chốt / có Yêu cầu chấm công / không exempt).
- Consumes: `is_exempt` (T2), `hrms.hr.period_lock.is_period_locked`,
  `hrms.hr.doctype.attendance_request.attendance_request_miyano.reapply_attendance_request`

- [ ] **Bước 1: Viết test đỏ**

```python
class TestFillFullDay(PerTestRollback, FrappeTestCase):
	"""E3 — sinh một ngày công và các lá chắn."""

	def setUp(self):
		self.emp = make_exempt_employee()

	def attendance_on(self, date):
		return frappe.db.get_value(
			"Attendance",
			{"employee": self.emp, "attendance_date": getdate(date), "docstatus": ["<", 2]},
			["name", "status", "custom_attendance_code", "custom_work_credit", "custom_auto_filled"],
			as_dict=True,
		)

	def test_creates_full_day_present(self):
		from hrms.hr.attendance_exempt import fill_full_day

		self.assertIsNotNone(fill_full_day(self.emp, ANCHOR))
		att = self.attendance_on(ANCHOR)
		self.assertEqual(att.custom_attendance_code, "X")
		self.assertEqual(att.status, "Present")
		self.assertEqual(att.custom_work_credit, 1.0)
		self.assertEqual(att.custom_auto_filled, 1)
		self.assertEqual(frappe.db.get_value("Attendance", att.name, "docstatus"), 1)

	def test_is_idempotent(self):
		from hrms.hr.attendance_exempt import fill_full_day

		fill_full_day(self.emp, ANCHOR)
		self.assertIsNone(fill_full_day(self.emp, ANCHOR))
		self.assertEqual(
			frappe.db.count("Attendance", {"employee": self.emp, "attendance_date": ANCHOR}), 1
		)

	def test_skips_holiday(self):
		from hrms.hr.attendance_exempt import fill_full_day

		hl = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": "Miyano Exempt Test 2099",
				"from_date": "2099-01-01",
				"to_date": "2099-12-31",
				"holidays": [{"holiday_date": ANCHOR, "description": "Ngày nghỉ test"}],
			}
		).insert()
		frappe.db.set_value("Employee", self.emp, "holiday_list", hl.name)
		self.assertIsNone(fill_full_day(self.emp, ANCHOR))
		self.assertIsNone(self.attendance_on(ANCHOR))

	def test_does_not_overwrite_existing_record(self):
		from hrms.hr.attendance_exempt import fill_full_day

		# HR cố ý chấm vắng — người thật thắng máy
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": ANCHOR,
				"custom_attendance_code": "V",
			}
		)
		att.insert()
		att.submit()
		self.assertIsNone(fill_full_day(self.emp, ANCHOR))
		self.assertEqual(self.attendance_on(ANCHOR).custom_attendance_code, "V")

	def test_skips_when_not_exempt(self):
		from hrms.hr.attendance_exempt import fill_full_day

		plain = test_employee("plain3@miyano.test")
		frappe.db.set_value("Employee", plain, "custom_exempt_from_checkin", 0)
		self.assertIsNone(fill_full_day(plain, ANCHOR))

	def test_skips_locked_period(self):
		"""Kỳ đã chốt là ĐÓNG BĂNG. Mock `is_period_locked` — luật khoá kỳ đã có test riêng ở
		`hrms/hr/tests/test_period_lock.py`; ở đây chỉ chứng minh `fill_full_day` có hỏi nó."""
		from unittest.mock import patch

		from hrms.hr.attendance_exempt import fill_full_day

		with patch("hrms.hr.period_lock.is_period_locked", return_value=True):
			self.assertIsNone(fill_full_day(self.emp, ANCHOR))
		self.assertIsNone(self.attendance_on(ANCHOR))
```

- [ ] **Bước 2: Chạy để thấy ĐỎ**

Run: `bash $SCRATCH/run_test.sh "hrms.hr.tests.test_attendance_exempt.TestFillFullDay"`
Kỳ vọng: FAIL — `ImportError: cannot import name 'fill_full_day'`.

- [ ] **Bước 3: Cài đặt** — thêm vào `hrms/hr/attendance_exempt.py`:

```python
def fill_full_day(employee: str, date) -> str | None:
	"""Sinh MỘT ngày công đủ (mã X) cho người miễn chấm công. Trả None nếu không được phép sinh.

	Thứ tự lá chắn là có chủ ý: rẻ trước, đắt sau, và "đã có dữ liệu" luôn thắng."""
	from hrms.hr.doctype.attendance_request.attendance_request_miyano import reapply_attendance_request
	from hrms.hr.period_lock import is_period_locked

	date = getdate(date)
	if not is_exempt(employee, date):
		return None
	if frappe.db.exists(
		"Attendance", {"employee": employee, "attendance_date": date, "docstatus": ["<", 2]}
	):
		return None  # người thật (hoặc kênh khác) đã quyết định ngày này
	if is_holiday(employee, date, raise_exception=False):
		return None  # T7/CN/lễ: không ai có công, kể cả người miễn chấm công
	if is_period_locked(employee, date):
		return None  # kỳ đã chốt là đóng băng
	if reapply_attendance_request(employee, date):
		return None  # đơn đã duyệt dựng lại ngày công theo đơn — đơn thắng

	row = frappe.db.get_value("Employee", employee, ["company", "default_shift"], as_dict=True)
	doc = frappe.get_doc(
		{
			"doctype": "Attendance",
			"employee": employee,
			"attendance_date": date,
			"company": row.company,
			"shift": row.default_shift,
			"custom_attendance_code": EXEMPT_CODE,
			"custom_auto_filled": 1,
		}
	)
	doc.flags.ignore_permissions = True
	doc.insert(ignore_permissions=True)
	doc.submit()
	doc.add_comment("Comment", _("Tự sinh: nhân viên miễn chấm công (full công)"))
	return doc.name
```

- [ ] **Bước 4: Chạy lại → XANH**

Run: `bash $SCRATCH/run_test.sh "hrms.hr.tests.test_attendance_exempt"` → `RESULT: OK` (E1–E3, 16 test),
`HARNESS_NO_LEAK`. Thấy `HARNESS_LEAK_DETECTED` ở `Holiday List` → xoá tay bản ghi
`Miyano Exempt Test 2099` rồi chạy lại.

- [ ] **Bước 5: Commit**

```bash
git add hrms/hr/attendance_exempt.py hrms/hr/tests/test_attendance_exempt.py
git commit -m "feat(hr): sinh ngay cong du (ma X) cho nguoi mien cham cong"
```

---

## T4: Điểm móc (a) — thay chấm vắng bằng full công

**Files:**
- Modify: `hrms/hr/doctype/shift_type/shift_type.py:225-249` (`mark_absent_for_dates_with_no_attendance`)
- Test: `hrms/hr/tests/test_attendance_exempt.py`

**Interfaces:**
- Consumes: `is_exempt`, `fill_full_day` (T2, T3)

- [ ] **Bước 1: Viết test đỏ**

```python
class TestAbsentBranch(PerTestRollback, FrappeTestCase):
	"""E4 — nhánh chấm vắng của Shift Type: người có cờ ra X, người thường vẫn V."""

	def test_exempt_gets_full_day_instead_of_absent(self):
		from hrms.hr.attendance_exempt import fill_full_day, is_exempt

		emp = make_exempt_employee()
		# mô phỏng đúng nhánh trong mark_absent_for_dates_with_no_attendance
		self.assertTrue(is_exempt(emp, ANCHOR))
		self.assertIsNotNone(fill_full_day(emp, ANCHOR))
		self.assertEqual(
			frappe.db.get_value(
				"Attendance", {"employee": emp, "attendance_date": ANCHOR}, "custom_attendance_code"
			),
			"X",
		)

	def test_shift_type_marks_exempt_present_not_absent(self):
		from hrms.hr.doctype.attendance.attendance import mark_attendance
		from hrms.hr.attendance_exempt import is_exempt

		plain = test_employee("plain4@miyano.test")
		frappe.db.set_value("Employee", plain, "custom_exempt_from_checkin", 0)
		self.assertFalse(is_exempt(plain, ANCHOR))
		# BẤT BIẾN: người không có cờ vẫn đi đúng đường cũ
		name = mark_attendance(plain, ANCHOR, "Absent")
		self.assertEqual(frappe.db.get_value("Attendance", name, "status"), "Absent")
```

- [ ] **Bước 2: Chạy — hai test này XANH sẵn** (chúng khoá hành vi, chưa cần code mới).

Run: `bash $SCRATCH/run_test.sh "hrms.hr.tests.test_attendance_exempt.TestAbsentBranch"` → OK.

- [ ] **Bước 3: Sửa `shift_type.py`** — trong `mark_absent_for_dates_with_no_attendance`, ngay sau
  khối `reapply_attendance_request`:

```python
				# Người MIỄN CHẤM CÔNG: không quẹt thẻ là bình thường, không phải vắng. Phải chặn ở
				# ĐÂY chứ không chỉ ở lượt quét riêng (`process_exempt_employees`): cả hai chạy trong
				# cùng lượt `hourly_long` và nhánh này chạy TRƯỚC, ghi V xong thì lượt quét đến sau
				# thấy "đã có bản ghi" và bỏ qua — người có phân ca vẫn vắng cả tháng.
				from hrms.hr.attendance_exempt import fill_full_day, is_exempt

				if is_exempt(employee, date):
					fill_full_day(employee, date)
					continue

				attendance = mark_attendance(employee, date, "Absent", self.name)
```

- [ ] **Bước 4: Chạy lại cả bộ liên quan**

Run: `bash $SCRATCH/run_test.sh "hrms.hr.tests.test_attendance_exempt"` → OK
Run: `bash $SCRATCH/run_test.sh "hrms.hr.doctype.shift_type.test_shift_type"` → **so với baseline**,
không có lỗi mới.

- [ ] **Bước 5: Commit**

```bash
git add hrms/hr/doctype/shift_type/shift_type.py hrms/hr/tests/test_attendance_exempt.py
git commit -m "feat(hr): nguoi mien cham cong khong bi cham vang khi thieu luot cham"
```

---

## T5: Điểm móc (b) — lượt quét độc lập với phân ca + scheduler

**Files:**
- Modify: `hrms/hr/attendance_exempt.py`
- Modify: `hrms/hooks.py:207-211` (`scheduler_events["hourly_long"]`)
- Test: `hrms/hr/tests/test_attendance_exempt.py`

**Interfaces:**
- Produces: `process_exempt_employees()` — không tham số, chạy được từ scheduler và `bench execute`.

- [ ] **Bước 1: Viết test đỏ**

```python
class TestSweep(PerTestRollback, FrappeTestCase):
	"""E5 — lượt quét không lệ thuộc phân ca (8/2026 trên site chưa có Shift Assignment nào)."""

	def test_sweep_fills_recent_working_days_without_shift_assignment(self):
		from hrms.hr.attendance_exempt import process_exempt_employees

		yesterday = add_days(getdate(), -1)
		emp = make_exempt_employee(email="sweep@miyano.test", from_date=add_days(yesterday, -2))
		self.assertFalse(
			frappe.db.exists("Shift Assignment", {"employee": emp, "docstatus": 1}),
			"test này phải chạy với nhân viên KHÔNG có phân ca",
		)
		process_exempt_employees()
		created = frappe.get_all(
			"Attendance",
			filters={"employee": emp, "attendance_date": [">=", add_days(yesterday, -2)]},
			fields=["attendance_date", "custom_attendance_code"],
		)
		self.assertTrue(created, "lượt quét không sinh ngày công nào")
		self.assertTrue(all(r.custom_attendance_code == "X" for r in created))

	def test_sweep_does_not_touch_today(self):
		from hrms.hr.attendance_exempt import process_exempt_employees

		emp = make_exempt_employee(email="sweep2@miyano.test", from_date=add_days(getdate(), -2))
		process_exempt_employees()
		# ngày hôm nay CHƯA HẾT → chưa kết luận được
		self.assertFalse(
			frappe.db.exists("Attendance", {"employee": emp, "attendance_date": getdate()})
		)

	def test_sweep_is_idempotent(self):
		from hrms.hr.attendance_exempt import process_exempt_employees

		emp = make_exempt_employee(email="sweep3@miyano.test", from_date=add_days(getdate(), -3))
		process_exempt_employees()
		before = frappe.db.count("Attendance", {"employee": emp})
		process_exempt_employees()
		self.assertEqual(frappe.db.count("Attendance", {"employee": emp}), before)

	def test_sweep_respects_backfill_window(self):
		from hrms.hr.attendance_exempt import BACKFILL_DAYS, process_exempt_employees

		old = add_days(getdate(), -(BACKFILL_DAYS + 10))
		emp = make_exempt_employee(email="sweep4@miyano.test", from_date=old)
		process_exempt_employees()
		self.assertFalse(
			frappe.db.exists("Attendance", {"employee": emp, "attendance_date": old}),
			"lượt quét tự động không được cày quá cửa sổ BACKFILL_DAYS",
		)

	def test_scheduler_hook_registered_after_auto_attendance(self):
		import hrms.hooks as hooks

		jobs = hooks.scheduler_events["hourly_long"]
		self.assertIn("hrms.hr.attendance_exempt.process_exempt_employees", jobs)
		self.assertGreater(
			jobs.index("hrms.hr.attendance_exempt.process_exempt_employees"),
			jobs.index("hrms.hr.doctype.shift_type.shift_type.process_auto_attendance_for_all_shifts"),
			"lượt quét phải chạy SAU auto-attendance",
		)
```

- [ ] **Bước 2: Chạy để thấy ĐỎ**

Run: `bash $SCRATCH/run_test.sh "hrms.hr.tests.test_attendance_exempt.TestSweep"`
Kỳ vọng: FAIL — `ImportError: cannot import name 'process_exempt_employees'`.

- [ ] **Bước 3: Cài đặt** — thêm vào `hrms/hr/attendance_exempt.py`:

```python
def process_exempt_employees():
	"""Scheduler `hourly_long`: lấp đầy ngày công cho MỌI người có cờ, kể cả người không được phân
	ca tháng đó (phân ca ở Miyano cấp theo từng tháng, quên là mất công cả tháng)."""
	if not exempt_fields_installed():
		return
	end = add_days(getdate(), -1)  # hôm nay chưa hết thì chưa kết luận
	floor = add_days(end, -BACKFILL_DAYS)
	for emp in exempt_employees():
		start = getdate(emp.custom_exempt_from_checkin_from or emp.date_of_joining or floor)
		if start < floor:
			start = floor
		stop = end
		if emp.relieving_date and getdate(emp.relieving_date) < stop:
			stop = getdate(emp.relieving_date)
		day = start
		while day <= stop:
			fill_full_day(emp.name, day)
			day = add_days(day, 1)
		# giữ tiến độ giữa các nhân viên, y như `process_auto_attendance`
		frappe.db.commit()  # nosemgrep
```

- [ ] **Bước 4: Đăng ký scheduler** — `hrms/hooks.py`, cuối danh sách `hourly_long`:

```python
		"hrms.hr.doctype.shift_schedule_assignment.shift_schedule_assignment.process_auto_shift_creation",
		# Miyano: người miễn chấm công — chạy SAU auto-attendance để không đua với nhánh chấm vắng.
		"hrms.hr.attendance_exempt.process_exempt_employees",
```

- [ ] **Bước 5: Chạy lại → XANH**

Run: `bash $SCRATCH/run_test.sh "hrms.hr.tests.test_attendance_exempt"` → OK, `HARNESS_NO_LEAK`.

- [ ] **Bước 6: Commit**

```bash
git add hrms/hr/attendance_exempt.py hrms/hooks.py hrms/hr/tests/test_attendance_exempt.py
git commit -m "feat(hr): luot quet sinh cong cho nguoi mien cham cong (khong le thuoc phan ca)"
```

---

## T6: Điểm móc (c) — có quẹt thẻ cũng không bị hạ mã

**Files:**
- Modify: `hrms/hr/doctype/shift_type/shift_type.py:115-134` (sau `get_attendance`)
- Modify: `hrms/hr/doctype/attendance/attendance.py:203-204` (cuối `apply_vn_half_day_classifier`)
- Test: `hrms/hr/tests/test_attendance_exempt.py`

**Interfaces:**
- Consumes: `is_exempt`, `EXEMPT_CODE`

- [ ] **Bước 1: Viết test đỏ**

```python
class TestNoDowngradeOnCheckin(PerTestRollback, FrappeTestCase):
	"""E6 — giám đốc ghé một tiếng vẫn đủ công; giờ vào/ra vẫn ghi thật cho báo cáo."""

	def shift_with_split(self):
		name = "Miyano Exempt Test Shift"
		if not frappe.db.exists("Shift Type", name):
			frappe.get_doc(
				{
					"doctype": "Shift Type",
					"__newname": name,
					"start_time": "08:00:00",
					"end_time": "17:30:00",
					"custom_split_half_day": 1,
					"custom_lunch_start": "12:00:00",
					"custom_lunch_end": "13:30:00",
				}
			).insert()
		return name

	def test_short_attendance_stays_full_day_for_exempt(self):
		emp = make_exempt_employee(email="short@miyano.test")
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": emp,
				"attendance_date": ANCHOR,
				"shift": self.shift_with_split(),
				"in_time": f"{ANCHOR} 10:00:00",
				"out_time": f"{ANCHOR} 11:00:00",
				"status": "Present",
			}
		)
		att.insert()
		self.assertEqual(att.custom_attendance_code, "X")
		self.assertEqual(att.status, "Present")
		self.assertGreater(att.working_hours, 0, "giờ có mặt vẫn phải ghi thật cho báo cáo")

	def test_short_attendance_still_downgrades_for_plain_employee(self):
		# BẤT BIẾN: người không có cờ vẫn đi đúng luật cũ (1/2X / V tuỳ giờ)
		plain = test_employee("short2@miyano.test")
		frappe.db.set_value("Employee", plain, "custom_exempt_from_checkin", 0)
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": plain,
				"attendance_date": ANCHOR,
				"shift": self.shift_with_split(),
				"in_time": f"{ANCHOR} 10:00:00",
				"out_time": f"{ANCHOR} 11:00:00",
				"status": "Present",
			}
		)
		att.insert()
		self.assertNotEqual(att.custom_attendance_code, "X")
```

- [ ] **Bước 2: Chạy để thấy ĐỎ**

Run: `bash $SCRATCH/run_test.sh "hrms.hr.tests.test_attendance_exempt.TestNoDowngradeOnCheckin"`
Kỳ vọng: FAIL ở test đầu — mã ra `1/2X` hoặc `V` thay vì `X`.

- [ ] **Bước 3: Sửa `attendance.py`** — cuối `apply_vn_half_day_classifier`, thay hai dòng cuối:

```python
		self.working_hours = ket_qua.hours
		from hrms.hr.attendance_exempt import EXEMPT_CODE, is_exempt

		if is_exempt(self.employee, self.attendance_date):
			# Người miễn chấm công: giờ vào/ra chỉ để BÁO CÁO, không bao giờ quyết định công. Bỏ
			# bước này thì giám đốc ghé một tiếng bị quy 1/2K và mất nửa ngày lương.
			self.custom_attendance_code = EXEMPT_CODE
			return
		self.custom_attendance_code = ket_qua.code
```

- [ ] **Bước 4: Sửa `shift_type.py`** — trong `process_auto_attendance`, ngay sau khối gán từ
  `self.get_attendance(single_shift_logs)`:

```python
			from hrms.hr.attendance_exempt import is_exempt

			if is_exempt(employee, attendance_date):
				# ngưỡng giờ của ca không áp cho người miễn chấm công
				attendance_status = "Present"
```

- [ ] **Bước 5: Chạy lại → XANH**

Run: `bash $SCRATCH/run_test.sh "hrms.hr.tests.test_attendance_exempt"` → OK
Run: `bash $SCRATCH/run_test.sh "hrms.hr.doctype.attendance.test_vn_half_day_classifier"` → OK
Run: `bash $SCRATCH/run_test.sh "hrms.hr.doctype.attendance.test_attendance_code_bridge"` → OK

- [ ] **Bước 6: Commit**

```bash
git add hrms/hr/doctype/attendance/attendance.py hrms/hr/doctype/shift_type/shift_type.py \
        hrms/hr/tests/test_attendance_exempt.py
git commit -m "feat(hr): quet the it gio khong ha ma cong cua nguoi mien cham cong"
```

---

## T7: Điểm móc (d) — nghỉ phép nửa ngày không bị trừ nửa còn lại

**Files:**
- Modify: `hrms/hr/doctype/shift_type/shift_type.py:371-397` (`mark_absent_for_half_day_dates`)
- Test: `hrms/hr/tests/test_attendance_exempt.py`

- [ ] **Bước 1: Viết test đỏ** (test #5 và #6 của spec — đơn nghỉ duyệt SAU khi đã sinh X):

```python
class TestLeaveOverridesGeneratedDay(PerTestRollback, FrappeTestCase):
	"""E7 — đơn nghỉ luôn thắng ngày X tự sinh; nửa ngày phép chỉ trừ 0,5."""

	def setUp(self):
		self.emp = make_exempt_employee(email="leave@miyano.test")

	def apply_leave(self, half_day=False):
		from hrms.hr.doctype.leave_application.test_leave_application import make_allocation_record

		# BẮT BUỘC truyền from_date/to_date: mặc định của helper là 2013-01-01..2019-12-31, không
		# phủ mốc 2099 → đơn nghỉ vỡ vì "không đủ phép" chứ không phải vì code của mình.
		make_allocation_record(
			employee=self.emp,
			leave_type="Nghỉ phép năm",
			from_date="2099-01-01",
			to_date="2099-12-31",
		)
		leave = frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": self.emp,
				"leave_type": "Nghỉ phép năm",
				"from_date": ANCHOR,
				"to_date": ANCHOR,
				"half_day": 1 if half_day else 0,
				"half_day_date": ANCHOR if half_day else None,
				"status": "Approved",
				"company": frappe.db.get_value("Employee", self.emp, "company"),
			}
		)
		leave.insert()
		leave.submit()
		return leave

	def test_full_day_leave_replaces_generated_day(self):
		from hrms.hr.attendance_exempt import fill_full_day

		fill_full_day(self.emp, ANCHOR)
		self.apply_leave()
		att = frappe.db.get_value(
			"Attendance",
			{"employee": self.emp, "attendance_date": ANCHOR, "docstatus": ["<", 2]},
			["status", "leave_type", "custom_attendance_code"],
			as_dict=True,
		)
		self.assertEqual(att.status, "On Leave")
		self.assertEqual(att.leave_type, "Nghỉ phép năm")
		self.assertEqual(att.custom_attendance_code, "P")

	def test_half_day_leave_keeps_other_half_present(self):
		from hrms.hr.attendance_exempt import fill_full_day

		fill_full_day(self.emp, ANCHOR)
		self.apply_leave(half_day=True)
		att = frappe.db.get_value(
			"Attendance",
			{"employee": self.emp, "attendance_date": ANCHOR, "docstatus": ["<", 2]},
			["status", "half_day_status", "custom_attendance_code"],
			as_dict=True,
		)
		self.assertEqual(att.status, "Half Day")
		self.assertEqual(att.half_day_status, "Present", "nửa còn lại của người miễn chấm công LÀ công")
		self.assertEqual(att.custom_attendance_code, "1/2P")
```

- [ ] **Bước 2: Chạy — ghi lại kết quả**

Run: `bash $SCRATCH/run_test.sh "hrms.hr.tests.test_attendance_exempt.TestLeaveOverridesGeneratedDay"`

Hai khả năng, xử lý khác nhau:
- **XANH sẵn** → điểm móc (d) chỉ là lưới an toàn (`modify_half_day_status` chỉ bật khi ngày đang
  **Absent**, mà người có cờ thì đang Present). Vẫn thêm guard ở Bước 3 và giữ test.
- **ĐỎ** ở `half_day_status` → guard là đường chạy chính, Bước 3 sửa cho xanh.

- [ ] **Bước 3: Thêm guard vào `mark_absent_for_half_day_dates`** (đầu vòng lặp, trong nhánh
  `if shift_details and ...`):

```python
			if shift_details and shift_details.shift_type.name == self.name:
				from hrms.hr.attendance_exempt import is_exempt

				if is_exempt(employee, attendance.attendance_date):
					# Nửa còn lại của người miễn chấm công là CÔNG, không phải vắng vì thiếu lượt chấm.
					# `get_half_absent_days` đọc `half_day_status` để trừ 0,5 → ép Absent là trừ oan.
					continue
```

- [ ] **Bước 4: Chạy lại → XANH**

Run: `bash $SCRATCH/run_test.sh "hrms.hr.tests.test_attendance_exempt"` → OK
Run: `bash $SCRATCH/run_test.sh "hrms.hr.doctype.attendance.test_code_resync_on_leave_record"` → OK

- [ ] **Bước 5: Commit**

```bash
git add hrms/hr/doctype/shift_type/shift_type.py hrms/hr/tests/test_attendance_exempt.py
git commit -m "feat(hr): nghi phep nua ngay cua nguoi mien cham cong khong bi tru nua con lai"
```

---

## T8: Công Tác ghi đè ngày `X` tự sinh thành `CT`

**Files:**
- Modify: `hrms/hr/doctype/business_trip/business_trip.py:84-119`
- Test: `hrms/hr/tests/test_attendance_exempt.py`

**Interfaces:**
- Produces trên `BusinessTrip`: `attendance_row(employee, date) -> frappe._dict | None`,
  `auto_filled_attendance(employee, date) -> str | None`,
  `convert_auto_filled_to_trip(attendance: str)`. `has_attendance` giữ nguyên chữ ký `-> bool`.

- [ ] **Bước 1: Viết test đỏ**

```python
class TestBusinessTripOverridesGeneratedDay(PerTestRollback, FrappeTestCase):
	"""E8 — CT phải thắng ngày X tự sinh, nhưng KHÔNG được đè ngày có quẹt thẻ thật."""

	def make_trip(self, employee, date):
		# `destination` là field BẮT BUỘC của Business Trip (kiểm business_trip.json 2026-08-13);
		# gọi thẳng `create_travel_attendance()` để test đúng một hàm, không đi qua Workflow duyệt.
		trip = frappe.get_doc(
			{
				"doctype": "Business Trip",
				"company": frappe.db.get_value("Employee", employee, "company"),
				"destination": "Hà Nội",
				"purpose": "Test công tác",
				"from_date": date,
				"to_date": date,
				"travelers": [{"employee": employee}],
			}
		)
		trip.insert()
		return trip

	def test_generated_day_becomes_ct(self):
		from hrms.hr.attendance_exempt import fill_full_day

		emp = make_exempt_employee(email="trip@miyano.test")
		fill_full_day(emp, ANCHOR)
		self.make_trip(emp, ANCHOR).create_travel_attendance()
		att = frappe.db.get_value(
			"Attendance",
			{"employee": emp, "attendance_date": ANCHOR, "docstatus": ["<", 2]},
			["custom_attendance_code", "status", "custom_auto_filled"],
			as_dict=True,
		)
		self.assertEqual(att.custom_attendance_code, "CT")
		self.assertEqual(att.status, "Work From Home")
		self.assertEqual(att.custom_auto_filled, 0, "đã thành ngày công tác thật, không còn là ngày tự sinh")
		self.assertEqual(
			frappe.db.count("Attendance", {"employee": emp, "attendance_date": ANCHOR}), 1
		)

	def test_real_checkin_day_is_not_overwritten(self):
		emp = make_exempt_employee(email="trip2@miyano.test")
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": emp,
				"attendance_date": ANCHOR,
				"in_time": f"{ANCHOR} 08:00:00",
				"out_time": f"{ANCHOR} 17:30:00",
				"custom_attendance_code": "X",
			}
		)
		att.insert()
		att.submit()
		self.make_trip(emp, ANCHOR).create_travel_attendance()
		self.assertEqual(
			frappe.db.get_value("Attendance", att.name, "custom_attendance_code"),
			"X",
			"ngày có giờ vào/ra thật là dữ liệu thật — Công Tác không được đè",
		)
```

- [ ] **Bước 2: Chạy để thấy ĐỎ**

Run: `bash $SCRATCH/run_test.sh "hrms.hr.tests.test_attendance_exempt.TestBusinessTripOverridesGeneratedDay"`
Kỳ vọng: FAIL — mã vẫn là `X` (Công Tác đang bỏ qua ngày đã có bản ghi).

- [ ] **Bước 3: Sửa `business_trip.py`** — thay `has_attendance` và vòng lặp trong
  `create_travel_attendance`:

```python
	def attendance_row(self, employee, date):
		return frappe.db.get_value(
			"Attendance",
			{"employee": employee, "attendance_date": date, "docstatus": ["<", 2]},
			["name", "custom_auto_filled", "in_time", "out_time"],
			as_dict=True,
		)

	def has_attendance(self, employee, date):
		return bool(self.attendance_row(employee, date))

	def auto_filled_attendance(self, employee, date) -> str | None:
		"""Ngày công do máy sinh cho người miễn chấm công (và chưa có giờ vào/ra thật) — coi như ô
		trống: chuyến công tác được phép ghi đè thành CT. Mọi bản ghi khác là dữ liệu thật."""
		row = self.attendance_row(employee, date)
		if row and cint(row.custom_auto_filled) and not row.in_time and not row.out_time:
			return row.name
		return None

	def convert_auto_filled_to_trip(self, attendance: str):
		"""X (tự sinh) -> CT trên bản ghi ĐÃ SUBMIT.

		Dùng `db_set` chứ không `save`: không field mã công nào có `allow_on_submit`, `save` sẽ ném
		lỗi. Đây đúng khuôn mà `leave_application.create_or_update_attendance` đang dùng.
		`custom_work_credit` không đổi (X và CT đều `work_fraction = 1.0`), và `Present ->
		Work From Home` không đụng lương (payroll chỉ trừ theo Absent / Half Day / leave_type LWP)."""
		from hrms.hr.period_lock import is_period_locked

		doc = frappe.get_doc("Attendance", attendance)
		if is_period_locked(doc.employee, doc.attendance_date):
			return
		doc.db_set(
			{"custom_attendance_code": "CT", "status": "Work From Home", "custom_auto_filled": 0}
		)
		doc.add_comment(
			"Comment", _("Chuyển công tự sinh (miễn chấm công) sang CT theo Công Tác {0}").format(self.name)
		)
```

Trong vòng lặp `while day <= end:` của `create_travel_attendance`:

```python
			if not is_holiday(t.employee, day, raise_exception=False):
				existing = self.auto_filled_attendance(t.employee, day)
				if existing:
					self.convert_auto_filled_to_trip(existing)
				elif not self.has_attendance(t.employee, day):
					att = frappe.get_doc(
						{
							"doctype": "Attendance",
							"employee": t.employee,
							"attendance_date": day,
							"custom_attendance_code": "CT",
							"company": self.company or frappe.db.get_value("Employee", t.employee, "company"),
						}
					)
					att.flags.ignore_permissions = True
					att.insert(ignore_permissions=True)
					att.submit()
			day = add_days(day, 1)
```

Nhớ import `cint` và `_` ở đầu file nếu chưa có.

- [ ] **Bước 4: Chạy lại → XANH**

Run: `bash $SCRATCH/run_test.sh "hrms.hr.tests.test_attendance_exempt"` → OK
Run: `bash $SCRATCH/run_test.sh "hrms.hr.doctype.business_trip.test_business_trip"` → **15 error
baseline** (thiếu role `WFC *`), không có lỗi MỚI.

- [ ] **Bước 5: Commit**

```bash
git add hrms/hr/doctype/business_trip/business_trip.py hrms/hr/tests/test_attendance_exempt.py
git commit -m "feat(hr): cong tac ghi de duoc ngay cong tu sinh (X -> CT)"
```

---

## T9: `generate_for_month` + nút chạy bù trên danh sách Attendance

**Files:**
- Modify: `hrms/hr/attendance_exempt.py`
- Modify: `hrms/hr/doctype/attendance/attendance_list.js`
- Test: `hrms/hr/tests/test_attendance_exempt.py`

**Interfaces:**
- Produces: `generate_for_month(month, year, employee=None) -> int` (whitelisted, HR Manager /
  System Manager) — trả **số ngày đã sinh**.

- [ ] **Bước 1: Viết test đỏ**

```python
class TestGenerateForMonth(PerTestRollback, FrappeTestCase):
	"""E9 — chạy bù theo tháng (dùng khi bật cờ giữa chừng hoặc sau khi huỷ chốt kỳ)."""

	def test_generates_past_month_and_returns_count(self):
		from frappe.utils import get_first_day, get_last_day

		from hrms.hr.attendance_exempt import generate_for_month

		last_month = get_first_day(add_days(get_first_day(getdate()), -1))
		emp = make_exempt_employee(email="backfill@miyano.test", from_date=last_month)
		count = generate_for_month(last_month.month, last_month.year, employee=emp)
		self.assertGreater(count, 0)
		self.assertEqual(
			count,
			frappe.db.count(
				"Attendance",
				{
					"employee": emp,
					"attendance_date": ["between", [last_month, get_last_day(last_month)]],
					"custom_auto_filled": 1,
				},
			),
		)

	def test_second_run_generates_nothing(self):
		from frappe.utils import get_first_day

		from hrms.hr.attendance_exempt import generate_for_month

		last_month = get_first_day(add_days(get_first_day(getdate()), -1))
		emp = make_exempt_employee(email="backfill2@miyano.test", from_date=last_month)
		generate_for_month(last_month.month, last_month.year, employee=emp)
		self.assertEqual(generate_for_month(last_month.month, last_month.year, employee=emp), 0)

	def test_does_not_generate_future_days(self):
		from hrms.hr.attendance_exempt import generate_for_month

		today = getdate()
		emp = make_exempt_employee(email="backfill3@miyano.test", from_date=today)
		generate_for_month(today.month, today.year, employee=emp)
		self.assertFalse(
			frappe.db.exists(
				"Attendance", {"employee": emp, "attendance_date": [">=", today]}
			),
			"không sinh công cho hôm nay và tương lai",
		)
```

- [ ] **Bước 2: Chạy để thấy ĐỎ**

Run: `bash $SCRATCH/run_test.sh "hrms.hr.tests.test_attendance_exempt.TestGenerateForMonth"`
Kỳ vọng: FAIL — `ImportError: cannot import name 'generate_for_month'`.

- [ ] **Bước 3: Cài đặt** — thêm vào `hrms/hr/attendance_exempt.py`:

```python
@frappe.whitelist()
def generate_for_month(month, year, employee: str | None = None) -> int:
	"""Chạy bù cả tháng — cho người bật cờ giữa chừng, hoặc sau khi huỷ chốt kỳ để sửa.

	Trả về SỐ NGÀY đã sinh để HR đối chiếu; không sinh ngày hôm nay và tương lai."""
	frappe.only_for(("HR Manager", "System Manager"))
	start = getdate(f"{cint(year)}-{cint(month):02d}-01")
	end = get_last_day(start)
	yesterday = add_days(getdate(), -1)
	if end > yesterday:
		end = yesterday
	rows = [frappe._dict(name=employee)] if employee else exempt_employees()
	created = 0
	for emp in rows:
		day = start
		while day <= end:
			if fill_full_day(emp.name, day):
				created += 1
			day = add_days(day, 1)
	return created
```

- [ ] **Bước 4: Nút trên danh sách Attendance** — `attendance_list.js`, trong `onload`:

```javascript
		listview.page.add_inner_button(__("Sinh công tháng (miễn chấm công)"), () => {
			const d = new frappe.ui.Dialog({
				title: __("Sinh công cho nhân viên miễn chấm công"),
				fields: [
					{ fieldname: "month", fieldtype: "Int", label: __("Tháng"), reqd: 1,
					  default: frappe.datetime.str_to_obj(frappe.datetime.get_today()).getMonth() + 1 },
					{ fieldname: "year", fieldtype: "Int", label: __("Năm"), reqd: 1,
					  default: frappe.datetime.str_to_obj(frappe.datetime.get_today()).getFullYear() },
					{ fieldname: "employee", fieldtype: "Link", options: "Employee",
					  label: __("Nhân viên (bỏ trống = tất cả)") },
				],
				primary_action_label: __("Sinh công"),
				primary_action(values) {
					frappe.call({
						method: "hrms.hr.attendance_exempt.generate_for_month",
						args: values,
						freeze: true,
						callback: (r) => {
							frappe.msgprint(__("Đã sinh {0} ngày công.", [r.message || 0]));
							listview.refresh();
						},
					});
					d.hide();
				},
			});
			d.show();
		});
```

- [ ] **Bước 5: Chạy lại → XANH + build asset**

Run: `bash $SCRATCH/run_test.sh "hrms.hr.tests.test_attendance_exempt"` → OK
Run: `cd /home/miyano/frappe-bench && bench build --app hrms`

- [ ] **Bước 6: Commit**

```bash
git add hrms/hr/attendance_exempt.py hrms/hr/doctype/attendance/attendance_list.js \
        hrms/hr/tests/test_attendance_exempt.py
git commit -m "feat(hr): nut sinh cong thang cho nguoi mien cham cong"
```

---

## T10: 🛑 GATE bất biến lương

**Files:**
- Test: `hrms/payroll/doctype/salary_slip/test_exempt_payroll.py` (tạo mới)

**Interfaces:**
- Consumes: `fill_full_day`; khuôn theo `test_attendance_code_payroll_invariance.py` (cùng thư mục).

- [ ] **Bước 1: Viết test**

```python
# Copyright (c) 2026, Miyano Việt Nam.
"""GATE: tính năng miễn chấm công chỉ được đụng số lương của ĐÚNG người được tick.

- Người KHÔNG có cờ: `payment_days` / `absent_days` / LWP y hệt trước và sau (bất biến cứng).
- Người CÓ cờ: công = số ngày làm việc trong kỳ (đó là thay đổi CÓ CHỦ Ý, đã ký duyệt 2026-08-13).
"""

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings
from frappe.utils import add_days, flt, getdate

from hrms.hr.attendance_exempt import fill_full_day, process_exempt_employees
from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import default_company, test_employee

MONTH_START = getdate("2099-06-01")
MONTH_END = getdate("2099-06-30")


def working_days_details(employee, start, end):
	"""Đo payroll qua `SalarySlip.get_working_days_details` — KHÔNG dựng cấu trúc lương.

	`make_employee_salary_slip` cần chart-of-accounts của `_Test Company` (miyano không có) → 44
	error nhiễu. Đường này cho đúng ba con số cần chứng minh mà không cần fixtures đó; cùng cách
	`hrms/tests/test_timekeeping_e2e.py` đang dùng."""
	slip = frappe.new_doc("Salary Slip")
	slip.employee = employee
	slip.company = default_company()
	slip.start_date = getdate(start)
	slip.end_date = getdate(end)
	slip.get_working_days_details()
	return frappe._dict(
		total=flt(slip.total_working_days),
		payment_days=flt(slip.payment_days),
		absent_days=flt(slip.absent_days),
		lwp=flt(slip.leave_without_pay),
	)


class TestExemptPayroll(PerTestRollback, FrappeTestCase):
	@change_settings("Payroll Settings", {"payroll_based_on": "Attendance"})
	def test_sweep_does_not_touch_plain_employee(self):
		"""BẤT BIẾN CỨNG: lượt quét chạy trên dữ liệu THẬT của tháng này mà người không có cờ không
		đổi một con số nào, và không có Attendance nào được sinh cho họ."""
		plain = test_employee("payroll_plain@miyano.test")
		frappe.db.set_value("Employee", plain, "custom_exempt_from_checkin", 0)
		start = add_days(getdate(), -31)
		end = add_days(getdate(), -1)

		before = working_days_details(plain, start, end)
		rows_before = frappe.db.count("Attendance", {"employee": plain})

		process_exempt_employees()

		self.assertEqual(working_days_details(plain, start, end), before)
		self.assertEqual(frappe.db.count("Attendance", {"employee": plain}), rows_before)

	@change_settings("Payroll Settings", {"payroll_based_on": "Attendance"})
	def test_exempt_employee_is_paid_every_working_day(self):
		emp = test_employee("payroll_exempt@miyano.test")
		frappe.db.set_value(
			"Employee",
			emp,
			{
				"custom_exempt_from_checkin": 1,
				"custom_exempt_from_checkin_from": MONTH_START,
				"relieving_date": None,
				"status": "Active",
			},
		)
		day = MONTH_START
		while day <= MONTH_END:
			fill_full_day(emp, day)
			day = add_days(day, 1)

		res = working_days_details(emp, MONTH_START, MONTH_END)
		self.assertEqual(res.absent_days, 0.0, "người miễn chấm công không còn ngày vắng nào")
		self.assertEqual(res.lwp, 0.0)
		self.assertEqual(res.payment_days, res.total, "đủ công cả kỳ")
```

- [ ] **Bước 2: Chạy**

Run: `bash $SCRATCH/run_test.sh "hrms.payroll.doctype.salary_slip.test_exempt_payroll"`
Kỳ vọng: `RESULT: OK` (2 test) + `HARNESS_NO_LEAK`. Nếu đỏ vì `_Test Company` thì đó là **noise
baseline** — kiểm bằng `git stash` rồi chạy lại.

- [ ] **Bước 3: Chạy TOÀN BỘ bộ test VN, so baseline**

```bash
for m in hrms.hr.tests.test_attendance_exempt \
         hrms.hr.doctype.attendance.test_attendance_code_bridge \
         hrms.hr.doctype.attendance.test_vn_half_day_classifier \
         hrms.hr.doctype.attendance.test_code_resync_on_leave_record \
         hrms.hr.doctype.attendance.test_lunch_flag \
         hrms.hr.doctype.shift_type.test_shift_type \
         hrms.tests.test_timekeeping_e2e \
         hrms.tests.test_setup_vn_defaults \
         hrms.payroll.doctype.salary_slip.test_exempt_payroll; do
  echo "== $m"; bash $SCRATCH/run_test.sh "$m" | tail -3
done
```

Mọi lỗi phải nằm trong nhóm baseline đã biết (`_Test Company`, role `WFC *`). Lỗi khác là của mình.

- [ ] **Bước 4: Commit**

```bash
git add hrms/payroll/doctype/salary_slip/test_exempt_payroll.py
git commit -m "test(hr): gate bat bien luong cho tinh nang mien cham cong"
```

---

## T11: Tài liệu + checklist triển khai

**Files:**
- Modify: `CLAUDE.md` (mục "Miyano customizations")
- Modify: `docs/spec/attendance-exempt-employees.md` (đổi trạng thái)
- Modify: `docs/tasks/plan-attendance-exempt.md` (ghi STATUS ở đầu)

- [ ] **Bước 1: Thêm một gạch đầu dòng vào `CLAUDE.md`**, sau mục "Yêu cầu chấm công":

```markdown
- **Miễn chấm công (full công):** nhân viên tick `Employee.custom_exempt_from_checkin` (giám đốc,
  giờ làm không cố định) được `hrms/hr/attendance_exempt.py` tự sinh **X** cho mọi ngày làm việc —
  qua nhánh chấm vắng của `Shift Type` và một lượt quét `hourly_long` độc lập với phân ca. Nghỉ
  phép / Yêu cầu chấm công ghi đè sẵn; **Công Tác** được sửa để đổi ngày `X` tự sinh
  (`Attendance.custom_auto_filled`) thành **CT**. Spec `docs/spec/attendance-exempt-employees.md`.
```

- [ ] **Bước 2: Đổi trạng thái spec** → `**Implemented** — <ngày>` kèm một dòng kết quả test.

- [ ] **Bước 3: Ghi STATUS đầu plan** (theo khuôn các plan khác): số task xong, số test xanh,
  còn treo gì.

- [ ] **Bước 4: Commit**

```bash
git add CLAUDE.md docs/spec/attendance-exempt-employees.md docs/tasks/plan-attendance-exempt.md
git commit -m "docs(hr): ghi nhan tinh nang mien cham cong vao CLAUDE.md + chot spec"
```

- [ ] **Bước 5: 🛑 GATE triển khai — trình bày rồi CHỜ ký duyệt**

Không tự chạy bất kỳ bước nào dưới đây:

1. `bench --site miyano migrate` — nếu T1 Bước 8 chưa chạy.
2. Tick cờ cho đúng người đã thống nhất (site hiện có 1 "Giám đốc"), điền ngày hiệu lực.
3. `generate_for_month` cho tháng hiện tại → đối chiếu bảng chấm công **trước khi chốt kỳ**.
4. Restart app để scheduler nạp code mới (miyano chạy supervisor + `gunicorn --preload`;
   **Claude không restart được** — người vận hành làm).

Ghi rõ khi trình: T8/2026 hiện **chưa có Shift Assignment nào** — nhánh (b) là thứ giữ cho tháng
này không trống, nhưng người **không** có cờ vẫn sẽ không được sinh công cho tới khi HR phân ca.
Đó là vấn đề sẵn có, **ngoài phạm vi** plan này, nêu ra để không ai tưởng tính năng mới gây ra.
