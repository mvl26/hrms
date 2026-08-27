# Mã công là neo — Kế hoạch triển khai

> **Cho agent thực thi:** SUB-SKILL BẮT BUỘC — dùng `superpowers:subagent-driven-development`
> (khuyến nghị) hoặc `superpowers:executing-plans` để chạy từng task. Các bước dùng checkbox
> (`- [ ]`) để đánh dấu tiến độ.

**Mục tiêu:** HR tạo bao nhiêu Loại nghỉ tuỳ ý; mỗi loại chỉ cần một dòng `Attendance Code` trỏ tới
là ra đúng mã và đúng số công — và hệ thống chặn mọi đường làm sai thay vì im lặng ra 0 công.

**Kiến trúc:** `Attendance Code` là neo. Tập `category` (nhóm cột) chuyển từ chuỗi tự do thành một
tập đóng khai ở một chỗ, có test ép năm nơi tiêu thụ không lệch. Thêm chốt chặn ở ba tầng:
`Attendance Code.validate` (1 mã ↔ 1 cặp trạng thái–loại nghỉ), form Loại nghỉ (không cho cướp mã
của loại nghỉ khác), và Đơn xin nghỉ (chặn loại nghỉ chưa có mã). Cuối cùng gỡ hằng cứng
`"Nghỉ phép năm"` để mọi loại nghỉ đi chung một đường.

**Tech stack:** Frappe Framework v15 + ERPNext, Python 3.10, `unittest` + `FrappeTestCase` +
`PerTestRollback`, Vue 3 (`frontend/`).

**Spec:** `docs/spec/attendance-code-as-anchor.md` — đọc trước khi bắt đầu bất kỳ task nào.

## Ràng buộc toàn cục

- **KHÔNG BAO GIỜ** `bench --site miyano run-tests`. Chạy test qua harness rollback (mục dưới).
- **Cổng bất biến lương:** kết thúc phải chứng minh `payment_days` / `absent_days` / LWP của Salary
  Slip không đổi trước–sau. Kế hoạch này không ghi vào bản ghi Attendance nào.
- Lint/format: **ruff** qua pre-commit — **tab**, **nháy kép**, dài dòng 110, py310.
  Chạy `pre-commit run --all-files` từ thư mục app.
- Conventional Commits, scope `(hr)`: `feat(hr): ...`, `refactor(hr): ...`, `test(hr): ...`.
- **Chỉ `git add` đúng file mình sửa** — cây làm việc đang có việc dở không liên quan.
- Đổi fixtures phải sửa **cả** `hrms/fixtures/*.json` **và** bộ lọc `fixtures` trong `hooks.py`;
  `hrms/tests/test_setup_vn_defaults.py` bắt lệch.
- Đổi schema doctype (`.json`) → `bench --site miyano migrate` từ `/home/miyano/frappe-bench`.
- Helper trên `Document` **không** đặt tên bắt đầu bằng `_` (bị `__getattr__` nuốt → trả `None`).
- Doctype/fieldname tiếng Anh, label tiếng Việt.
- Tập category chuẩn (chép nguyên văn, đúng dấu):
  `"Công", "Phép", "Ốm", "Thai sản", "Tai nạn LĐ", "Nghỉ bù", "Việc riêng", "Không lương", "Vắng"`

## Chạy test (harness rollback)

Dựng một lần ở Task 1, mọi bước "Run" sau đó gọi lại. `$SCRATCH` = thư mục scratchpad của phiên.

`$SCRATCH/run_test.sh`:

```bash
#!/usr/bin/env bash
# Usage: bash $SCRATCH/run_test.sh "<dotted.module>[.TestClass.test_method]"
cd /home/miyano/frappe-bench
cat > /tmp/hrms_harness.py <<'PY'
import frappe, unittest, os
frappe.flags.in_test = True
_c = frappe.db.commit
frappe.db.commit = lambda *a, **k: None          # không bao giờ ghi thật vào DB site
WATCH = ["Attendance", "Employee", "Employee Checkin", "Leave Application", "Leave Type",
         "Leave Allocation", "Attendance Code", "Monthly Attendance Sheet", "Salary Slip"]
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
2. Thấy `HARNESS_LEAK_DETECTED` thì **dừng, dọn tay ngay** rồi mới đi tiếp. Một câu DDL gây implicit
   commit trên MariaDB sẽ chốt mọi thứ đang dở.
3. Baseline đỏ sẵn có trên site (mốc 2026-07-24) là nhiễu `_Test Company` — so với baseline, đừng
   coi mọi lỗi đỏ là do mình.

## Cấu trúc file

| File | Trách nhiệm | Task |
|---|---|---|
| `hrms/hr/attendance_category.py` | **Tạo.** Tập category chuẩn + helper `select_options()` | 1 |
| `hrms/hr/tests/test_attendance_category.py` | **Tạo.** Ép năm nơi tiêu thụ không lệch | 1 |
| `hrms/hr/doctype/attendance_code/attendance_code.json` | `category`: `Data` → `Select` bắt buộc | 1 |
| `hrms/hr/attendance_legend.py` | Xoá `CATEGORY_ORDER`, import từ module mới | 1 |
| `hrms/hr/doctype/monthly_attendance_sheet/monthly_attendance_sheet.py` | Nâng `category_field` lên module level thành `CATEGORY_FIELD` | 1 |
| `hrms/hr/doctype/attendance_code/attendance_code.py` | **Có validate:** 1 mã ↔ 1 cặp | 2 |
| `hrms/hr/leave_type_code.py` | Chống cướp mã; cảnh báo đỏ | 3 |
| `hrms/setup_vn_defaults.py` | Cảnh báo loại nghỉ chưa gắn mã lúc migrate | 3 |
| `hrms/hr/doctype/leave_application/leave_single_pool.py` | **Task 4:** thêm chốt chặn. **Task 5:** đổi tên thành `leave_attendance_code.py`, rút hằng `POOL_*` | 4, 5 |
| `hrms/hooks.py` | Đăng ký hook mới / đổi đường dẫn module | 4, 5 |
| `hrms/fixtures/custom_field.json` | Gỡ `eval:doc.leave_type=='Nghỉ phép năm'` | 5 |
| `frontend/src/views/leave/Form.vue` | Gỡ hardcode `is_pool` | 5 |

---

### Task 1: Tập category chuẩn — khai một chỗ, ép năm nơi

**Files:**
- Create: `hrms/hr/attendance_category.py`
- Create: `hrms/hr/tests/test_attendance_category.py`
- Modify: `hrms/hr/doctype/attendance_code/attendance_code.json` (field `category`)
- Modify: `hrms/hr/attendance_legend.py:29-39` (xoá `CATEGORY_ORDER`)
- Modify: `hrms/hr/doctype/monthly_attendance_sheet/monthly_attendance_sheet.py:151-174`
- Modify: `hrms/tests/vn_test_utils.py`, `hrms/hr/doctype/attendance_code/test_attendance_code.py`,
  `hrms/hr/doctype/attendance/test_lunch_flag.py`, `hrms/hr/tests/test_leave_type_code.py`
  (bổ sung `category` cho mọi chỗ dựng `Attendance Code`)

**Interfaces:**
- Produces: `hrms.hr.attendance_category.CATEGORIES: tuple[str, ...]`,
  `CATEGORY_WITHOUT_SHEET_COLUMN: tuple[str, ...]`, `select_options() -> str`
- Produces: `hrms.hr.doctype.monthly_attendance_sheet.monthly_attendance_sheet.CATEGORY_FIELD: dict[str, str]`

- [ ] **Bước 1: Dựng harness** — ghi `$SCRATCH/run_test.sh` đúng nội dung ở mục "Chạy test", `chmod +x`.

- [ ] **Bước 2: Chụp mốc lương TRƯỚC khi sửa bất cứ thứ gì**

Cổng bất biến lương cần mốc chụp **trước** thay đổi đầu tiên — chụp sau thì không còn gì để so.
Ghi `$SCRATCH/payroll_snapshot.py`:

```python
import frappe

rows = frappe.get_all(
    "Salary Slip",
    filters={"docstatus": ["<", 2]},
    fields=["name", "payment_days", "absent_days", "leave_without_pay", "total_working_days"],
    order_by="name",
)
print("SLIPS:", len(rows))
print("SUM:", {
    k: round(sum(float(r[k] or 0) for r in rows), 3)
    for k in ("payment_days", "absent_days", "leave_without_pay", "total_working_days")
})
```

Chạy nó qua `bench --site miyano console` bằng `exec(compile(open(...).read(), ...))` (xem ba điều
bắt buộc ở mục "Chạy test"), lưu đầu ra vào `$SCRATCH/payroll_before.txt`. Task 6 sẽ chụp lại và so.

- [ ] **Bước 3: Viết test đỏ**

`hrms/hr/tests/test_attendance_category.py`:

```python
# Copyright (c) 2026, Miyano Việt Nam.
"""Tập NHÓM (category) của mã công phải khớp ở MỌI nơi tiêu thụ.

Category quyết định ngày đó rơi vào cột nào của bảng công và có vào "Tổng công" hay không. Trước
đây tập giá trị hợp lệ bị chép cứng ở năm chỗ, không chỗ nào biết chỗ nào — gõ sai một ký tự là
ngày đó lặng lẽ rơi khỏi mọi cột tổng. Test này khiến "thêm một nhóm" thành việc không thể làm
nửa vời.

Chạy qua harness rollback (KHÔNG bench run-tests trên miyano).
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.hr.attendance_category import CATEGORIES, CATEGORY_WITHOUT_SHEET_COLUMN, select_options
from hrms.tests.isolation import PerTestRollback


class TestAttendanceCategory(PerTestRollback, FrappeTestCase):
	def test_doctype_select_options_match_the_canon(self):
		"""Tuỳ chọn của field `category` trong JSON == CATEGORIES, đúng thứ tự."""
		path = frappe.get_app_path("hrms", "hr", "doctype", "attendance_code", "attendance_code.json")
		with open(path) as f:
			schema = json.load(f)
		field = next(f for f in schema["fields"] if f["fieldname"] == "category")
		self.assertEqual(field["fieldtype"], "Select")
		self.assertEqual(field.get("reqd"), 1, "thiếu nhóm thì mã lặng lẽ được tính là nghỉ có lương")
		self.assertEqual(field["options"], select_options())

	def test_every_category_has_a_colour_state(self):
		"""Thiếu trong CATEGORY_STATE thì ô của mã đó không được tô màu."""
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import CATEGORY_STATE

		missing = [c for c in CATEGORIES if c not in CATEGORY_STATE]
		self.assertEqual(missing, [], f"nhóm chưa có màu: {missing}")

	def test_every_category_has_a_sheet_column(self):
		"""Thiếu cột trên Bảng Công Tháng thì số ngày của nhóm đó rơi khỏi bản in đã chốt."""
		from hrms.hr.doctype.monthly_attendance_sheet.monthly_attendance_sheet import CATEGORY_FIELD

		missing = [
			c for c in CATEGORIES if c not in CATEGORY_FIELD and c not in CATEGORY_WITHOUT_SHEET_COLUMN
		]
		self.assertEqual(missing, [], f"nhóm chưa có cột: {missing}")

	def test_report_constants_only_name_known_categories(self):
		"""REPORT_CATEGORIES / NON_PAID_LEAVE_CATEGORIES không được nhắc tới nhóm không tồn tại."""
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import (
			BUCKET_MARRIAGE,
			NON_PAID_LEAVE_CATEGORIES,
			REPORT_CATEGORIES,
		)

		known = set(CATEGORIES) | {BUCKET_MARRIAGE}
		for cat, _label in REPORT_CATEGORIES:
			self.assertIn(cat, known, f"cột báo cáo trỏ tới nhóm lạ: {cat}")
		for cat in NON_PAID_LEAVE_CATEGORIES:
			self.assertIn(cat, CATEGORIES, f"luật Tổng công trỏ tới nhóm lạ: {cat}")

	def test_legend_order_is_the_canon(self):
		"""Chú thích sắp theo đúng tập chuẩn, không giữ bản chép riêng."""
		from hrms.hr.attendance_legend import CATEGORY_ORDER

		self.assertEqual(tuple(CATEGORY_ORDER), CATEGORIES)

	def test_every_code_on_this_site_uses_a_known_category(self):
		"""Dữ liệu thật phải nằm trong tập chuẩn — nếu không, đổi sang Select sẽ chặn lần lưu sau."""
		rows = frappe.get_all("Attendance Code", fields=["name", "category"])
		bad = [r.name for r in rows if r.category not in CATEGORIES]
		self.assertEqual(bad, [], f"mã có nhóm ngoài tập chuẩn: {bad}")
```

- [ ] **Bước 4: Chạy test, xác nhận ĐỎ**

Run: `bash $SCRATCH/run_test.sh "hrms.hr.tests.test_attendance_category"`
Expected: FAIL — `ModuleNotFoundError: hrms.hr.attendance_category`

- [ ] **Bước 5: Tạo module tập chuẩn**

`hrms/hr/attendance_category.py`:

```python
# Copyright (c) 2026, Miyano Việt Nam.
"""Miyano — tập NHÓM (category) chuẩn của mã công. Khai một chỗ, năm nơi tiêu thụ.

`Attendance Code.category` quyết định ngày mang mã đó rơi vào cột nào của bảng công tháng và có
được cộng vào "Tổng công" hay không. Trước 2026-08-24 field này là `Data` tự do, còn tập giá trị
hợp lệ bị chép cứng ở năm chỗ: `REPORT_CATEGORIES`, `NON_PAID_LEAVE_CATEGORIES`, `CATEGORY_STATE`
(báo cáo chấm công tháng), `CATEGORY_FIELD` (Bảng Công Tháng) và `CATEGORY_ORDER` (chú thích). Gõ
`"Phep"` thay vì `"Phép"` thì mã vẫn hiện đúng từng ngày nhưng ngày đó **lặng lẽ rơi khỏi mọi cột
tổng** — không lỗi, không cảnh báo.

Đây là điểm mở rộng THẬT của hệ thống mã công: Loại nghỉ thì tạo bao nhiêu tuỳ ý, nhưng mỗi mã
phải xếp vào một nhóm mà bảng công đã có cột. `hrms/hr/tests/test_attendance_category.py` ép năm
nơi kia không được lệch với danh sách ở đây.
"""

# Thứ tự đọc từ trái sang là đi từ "trả đủ" tới "không trả" — cũng là thứ tự khối chú thích.
CATEGORIES = (
	"Công",
	"Phép",
	"Ốm",
	"Thai sản",
	"Tai nạn LĐ",
	"Nghỉ bù",
	"Việc riêng",
	"Không lương",
	"Vắng",
)

# Nhóm CỐ Ý không có cột riêng trên Bảng Công Tháng: phần đi làm đã nằm trong "Tổng công", tách ra
# thành hai con số công trên cùng một bảng là mời người đọc hiểu nhầm.
CATEGORY_WITHOUT_SHEET_COLUMN = ("Công",)


def select_options() -> str:
	"""Chuỗi `options` cho field Select của `Attendance Code.category`."""
	return "\n".join(CATEGORIES)
```

- [ ] **Bước 6: Đổi field `category` sang Select bắt buộc**

Trong `hrms/hr/doctype/attendance_code/attendance_code.json`, thay khối field `category` bằng:

```json
  {
   "description": "Nhóm cột trên bảng công tháng, ví dụ Công / Phép / Ốm. Quyết định ngày đó vào cột nào và có tính Tổng công hay không.",
   "fieldname": "category",
   "fieldtype": "Select",
   "in_list_view": 1,
   "label": "Category",
   "options": "Công\nPhép\nỐm\nThai sản\nTai nạn LĐ\nNghỉ bù\nViệc riêng\nKhông lương\nVắng",
   "reqd": 1
  },
```

- [ ] **Bước 7: Nâng `CATEGORY_FIELD` lên module level**

Trong `hrms/hr/doctype/monthly_attendance_sheet/monthly_attendance_sheet.py`: chuyển dict
`category_field` (đang là biến cục bộ trong `populate_from_attendance`) lên đầu module thành hằng
`CATEGORY_FIELD`, và chuyển hai import `BUCKET_MARRIAGE`, `TOTAL_PAID` lên module level cùng nó
(báo cáo **không** import ngược Bảng Công Tháng nên không có vòng lặp import).

```python
from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import (
	BUCKET_MARRIAGE,
	TOTAL_PAID,
)

# Nhóm của mã công → cột tổng trên bảng. Bảng chỉ mang MỘT con số công: "Tổng công" = số ngày công
# ty trả lương, lấy đúng cột của báo cáo → một kỳ không thể có hai con số công. Phần đi làm thực tế
# không có cột riêng ở đây; cần tách bạch thì xem mã công từng ngày, hoặc cột Công của báo cáo.
CATEGORY_FIELD = {
	TOTAL_PAID: "total_paid_days",
	"Phép": "annual_leave",
	# KH (nghỉ kết hôn) tách khỏi "Việc riêng" — HR chốt 2026-08-04. Phải có mặt ở ĐÂY nữa, không
	# thì ngày KH rơi khỏi bảng: bảng chỉ ghi những loại có trong bảng ánh xạ này.
	BUCKET_MARRIAGE: "marriage_leave",
	"Việc riêng": "personal_leave",
	"Ốm": "sick_leave",
	"Thai sản": "maternity_leave",
	"Tai nạn LĐ": "work_accident_leave",
	"Nghỉ bù": "comp_off",
	"Không lương": "unpaid_leave",
	"Vắng": "absent",
	"Nghỉ lễ": "public_holiday",
}
```

Trong `populate_from_attendance`, xoá dict cục bộ + hai import cục bộ, đổi chỗ dùng thành
`CATEGORY_FIELD`.

- [ ] **Bước 8: Chú thích dùng chung tập chuẩn**

Trong `hrms/hr/attendance_legend.py`, xoá khối `CATEGORY_ORDER = [...]` và thay bằng:

```python
from hrms.hr.attendance_category import CATEGORIES

# đi làm trước → nghỉ có lương → không lương → vắng: đọc từ trái sang là đi từ "trả đủ" tới
# "không trả". Nguồn duy nhất là `attendance_category.CATEGORIES` — chú thích không giữ bản chép
# riêng, nếu không thêm nhóm mới là mã tụt xuống cuối chú thích mà không ai biết.
CATEGORY_ORDER = list(CATEGORIES)
```

- [ ] **Bước 9: `bench migrate` để áp schema**

Run: `cd /home/miyano/frappe-bench && bench --site miyano migrate`
Expected: chạy xong, không lỗi. `category` giờ là Select bắt buộc.

- [ ] **Bước 10: Chạy test, xác nhận XANH**

Run: `bash $SCRATCH/run_test.sh "hrms.hr.tests.test_attendance_category"`
Expected: `RESULT: OK` và `HARNESS_NO_LEAK`

- [ ] **Bước 11: Sửa mọi chỗ dựng `Attendance Code` trong test**

`category` giờ bắt buộc. Bổ sung nhóm cho 13 chỗ dựng mã ở 4 file:

- `hrms/tests/vn_test_utils.py::ensure_short_hours_code` — mã `1/2X` đã có `"category": "Công"`,
  kiểm tra lại là đủ.
- `hrms/hr/doctype/attendance_code/test_attendance_code.py::create_attendance_code` — thêm mặc định:

```python
		"category": kwargs.pop("category", "Công"),
```

- `hrms/hr/doctype/attendance/test_lunch_flag.py` và `hrms/hr/tests/test_leave_type_code.py` — mọi
  `frappe.get_doc({"doctype": "Attendance Code", ...})` thêm `"category"`: mã `On Leave` dùng
  `"Phép"`, mã đi làm dùng `"Công"`.

- [ ] **Bước 12: Chạy lại bốn bộ test bị ảnh hưởng**

```bash
for m in hrms.hr.doctype.attendance_code.test_attendance_code \
         hrms.hr.doctype.attendance_code.test_attendance_code_fixtures \
         hrms.hr.doctype.attendance.test_lunch_flag \
         hrms.hr.tests.test_leave_type_code; do
  bash $SCRATCH/run_test.sh "$m"
done
```
Expected: `RESULT: OK` cả bốn, `HARNESS_NO_LEAK`.

- [ ] **Bước 13: Chạy bộ báo cáo + Bảng Công Tháng (không được vỡ vì nâng hằng)**

```bash
for m in hrms.hr.report.monthly_attendance_report.test_monthly_attendance_report \
         hrms.hr.report.monthly_attendance_report.test_attendance_xlsx \
         hrms.hr.doctype.monthly_attendance_sheet.test_monthly_attendance_sheet; do
  bash $SCRATCH/run_test.sh "$m"
done
```
Expected: `RESULT: OK` cả ba.

- [ ] **Bước 14: Lint + commit**

```bash
cd /home/miyano/frappe-bench/apps/hrms
pre-commit run --files hrms/hr/attendance_category.py hrms/hr/tests/test_attendance_category.py \
  hrms/hr/attendance_legend.py hrms/hr/doctype/attendance_code/attendance_code.json \
  hrms/hr/doctype/monthly_attendance_sheet/monthly_attendance_sheet.py
git add hrms/hr/attendance_category.py hrms/hr/tests/test_attendance_category.py \
  hrms/hr/attendance_legend.py hrms/hr/doctype/attendance_code/attendance_code.json \
  hrms/hr/doctype/monthly_attendance_sheet/monthly_attendance_sheet.py \
  hrms/tests/vn_test_utils.py hrms/hr/doctype/attendance_code/test_attendance_code.py \
  hrms/hr/doctype/attendance/test_lunch_flag.py hrms/hr/tests/test_leave_type_code.py
git commit -m "feat(hr): nhom ma cong thanh tap dong, khai mot cho"
```

---

### Task 2: `Attendance Code` có validate — 1 mã ↔ 1 loại

**Files:**
- Modify: `hrms/hr/doctype/attendance_code/attendance_code.py`
- Test: `hrms/hr/doctype/attendance_code/test_attendance_code.py`

**Interfaces:**
- Consumes: `hrms.hr.attendance_category.CATEGORIES` (Task 1)
- Produces: `AttendanceCode.validate()` — `frappe.ValidationError` khi trùng cặp

- [ ] **Bước 1: Viết test đỏ**

Thêm vào `hrms/hr/doctype/attendance_code/test_attendance_code.py`:

```python
	def test_rejects_second_code_for_the_same_leave_type_and_status(self):
		"""Bất biến HR yêu cầu: 1 mã ↔ 1 (trạng thái, loại nghỉ).

		Hai mã cùng cặp thì reverse-derive phải ĐOÁN xem ngày nghỉ đó hiện mã nào — và `P` với một
		mã lạ nào đó không thay thế được cho nhau."""
		create_attendance_code(
			"ZP", maps_to_status="On Leave", category="Phép", leave_type="Nghỉ phép năm", work_fraction=0
		)
		with self.assertRaises(frappe.ValidationError):
			create_attendance_code(
				"ZQ",
				maps_to_status="On Leave",
				category="Phép",
				leave_type="Nghỉ phép năm",
				work_fraction=0,
			)

	def test_allows_same_leave_type_on_a_different_status(self):
		"""Cặp cả-ngày/nửa-ngày (P và 1/2P) là hợp lệ — chúng khác `maps_to_status`."""
		create_attendance_code(
			"ZH", maps_to_status="Half Day", category="Phép", leave_type="Nghỉ ốm", work_fraction=0.5
		)
		doc = create_attendance_code(
			"ZF", maps_to_status="On Leave", category="Ốm", leave_type="Nghỉ ốm", work_fraction=0
		)
		self.assertEqual(doc.name, "ZF")

	def test_allows_many_codes_without_a_leave_type(self):
		"""Mã đi làm (X, CT, W) không có loại nghỉ — luật duy nhất KHÔNG được áp cho chúng."""
		create_attendance_code("ZW", maps_to_status="Work From Home", category="Công")
		doc = create_attendance_code("ZV", maps_to_status="Work From Home", category="Công")
		self.assertEqual(doc.name, "ZV")

	def test_allows_an_on_leave_code_not_linked_yet(self):
		"""Mã nghỉ phải tạo được lúc CHƯA gắn loại nghỉ — form Loại nghỉ chọn mã đã tồn tại.

		Bắt buộc `leave_type` ở đây là bế tắc con-gà-quả-trứng (xem spec §3.2)."""
		doc = create_attendance_code("ZU", maps_to_status="On Leave", category="Phép", work_fraction=0)
		self.assertIsNone(doc.leave_type)

	def test_all_fixture_codes_pass_validation(self):
		"""17 mã đang có trên site phải qua được — nếu không, `bench migrate` re-sync fixtures sẽ vỡ."""
		for name in frappe.get_all("Attendance Code", pluck="name"):
			frappe.get_doc("Attendance Code", name).validate()
```

- [ ] **Bước 2: Chạy test, xác nhận ĐỎ**

Run: `bash $SCRATCH/run_test.sh "hrms.hr.doctype.attendance_code.test_attendance_code"`
Expected: FAIL — `test_rejects_second_code_for_the_same_leave_type_and_status` không raise gì
(controller đang là `pass`).

- [ ] **Bước 3: Viết validate**

`hrms/hr/doctype/attendance_code/attendance_code.py`:

```python
# Copyright (c) 2026, Miyano Việt Nam.
import frappe
from frappe import _
from frappe.model.document import Document


class AttendanceCode(Document):
	"""Mã công — NEO của toàn bộ tuyến chấm công VN.

	Mã quyết định ngày đó hiện ký hiệu gì, tính mấy công, và rơi vào cột nào. Loại nghỉ thì HR tạo
	bao nhiêu tuỳ ý, nhưng mỗi loại nghỉ phải có mã trỏ tới thì ngày nghỉ mới ra đúng công —
	xem `docs/spec/attendance-code-as-anchor.md`.
	"""

	def validate(self):
		self.validate_unique_leave_mapping()

	def validate_unique_leave_mapping(self):
		"""Một cặp (trạng thái, loại nghỉ) chỉ được đúng MỘT mã.

		Đây là bất biến HR yêu cầu ("1 code ứng 1 loại nghỉ"), và cũng là thứ khiến reverse-derive
		không bao giờ phải đoán: `_pick_reverse_code` nhận nhiều mã cùng khớp thì buộc phải chọn
		bừa, mà `W` (làm tại nhà) với `CT` (đi công tác) là ví dụ sống của hai mã KHÔNG thay thế
		được cho nhau.

		Mã KHÔNG có loại nghỉ (X, CT, W, V, 1/2X) nằm ngoài luật này — chúng phân biệt nhau bằng
		`CANONICAL_REVERSE_CODE` chứ không bằng loại nghỉ.
		"""
		if not self.leave_type:
			return
		clash = frappe.db.exists(
			"Attendance Code",
			{
				"name": ("!=", self.name),
				"leave_type": self.leave_type,
				"maps_to_status": self.maps_to_status,
			},
		)
		if clash:
			frappe.throw(
				_(
					"Mã công {0} đã ứng với loại nghỉ {1} ở trạng thái {2}. Một cặp (trạng thái, "
					"loại nghỉ) chỉ được có đúng một mã — sửa hoặc gỡ mã kia trước."
				).format(frappe.bold(clash), frappe.bold(self.leave_type), frappe.bold(self.maps_to_status)),
				title=_("Trùng mã cho một loại nghỉ"),
			)
```

- [ ] **Bước 4: Chạy test, xác nhận XANH**

Run: `bash $SCRATCH/run_test.sh "hrms.hr.doctype.attendance_code.test_attendance_code"`
Expected: `RESULT: OK`, `HARNESS_NO_LEAK`

- [ ] **Bước 5: Xác nhận fixtures vẫn sync được**

Run: `cd /home/miyano/frappe-bench && bench --site miyano migrate`
Expected: chạy xong, không `ValidationError` từ `Attendance Code`.

- [ ] **Bước 6: Lint + commit**

```bash
cd /home/miyano/frappe-bench/apps/hrms
pre-commit run --files hrms/hr/doctype/attendance_code/attendance_code.py \
  hrms/hr/doctype/attendance_code/test_attendance_code.py
git add hrms/hr/doctype/attendance_code/attendance_code.py \
  hrms/hr/doctype/attendance_code/test_attendance_code.py
git commit -m "feat(hr): mot ma cong ung dung mot cap trang thai-loai nghi"
```

---

### Task 3: Loại nghỉ — chống cướp mã, cảnh báo đỏ, soi lúc migrate

**Files:**
- Modify: `hrms/hr/leave_type_code.py:38-90`
- Modify: `hrms/setup_vn_defaults.py:32-58`
- Test: `hrms/hr/tests/test_leave_type_code.py`, `hrms/tests/test_setup_vn_defaults.py`

**Interfaces:**
- Produces: `hrms.setup_vn_defaults.leave_types_without_code() -> list[str]`;
  `ensure_defaults()` trả thêm khoá `"leave_types_without_code"`

- [ ] **Bước 1: Viết test đỏ**

Thêm vào `hrms/hr/tests/test_leave_type_code.py`:

```python
	def test_refuses_to_steal_a_code_owned_by_another_leave_type(self):
		"""BẪY CÓ THẬT: HR tạo loại nghỉ mới để thay "Nghỉ phép năm" rồi chọn luôn mã `P`.

		Trước đây `P` bị gỡ khỏi "Nghỉ phép năm" trong im lặng — mọi ngày phép cũ mất đường tra
		ngược và bảng công hiện sai. Đổi chủ một mã phải là việc cố ý, làm ở Attendance Code."""
		lt = self._leave_type("Nghỉ thử cướp mã")
		with self.assertRaises(frappe.ValidationError):
			sync_code_to_leave_type(frappe._dict(name=lt.name, custom_attendance_code="P"))
		self.assertEqual(self._code_link("P"), "Nghỉ phép năm", "P phải còn nguyên chủ cũ")

	def test_reassigning_a_code_to_its_own_leave_type_is_a_no_op(self):
		"""Lưu lại chính loại nghỉ đang giữ mã thì không được coi là cướp."""
		sync_code_to_leave_type(frappe._dict(name="Nghỉ phép năm", custom_attendance_code="P"))
		self.assertEqual(self._code_link("P"), "Nghỉ phép năm")
```

Thêm vào `hrms/tests/test_setup_vn_defaults.py`:

```python
	def test_reports_leave_types_without_any_attendance_code(self):
		"""Loại nghỉ chưa gắn mã phải lộ ra lúc migrate, không đợi tới lúc in bảng công."""
		from hrms.setup_vn_defaults import leave_types_without_code

		self.assertEqual(leave_types_without_code(), [], "tiền đề: site đang sạch")

		frappe.get_doc(
			{"doctype": "Leave Type", "leave_type_name": "Nghỉ thử chưa gắn mã", "is_lwp": 0}
		).insert(ignore_permissions=True)

		self.assertIn("Nghỉ thử chưa gắn mã", leave_types_without_code())
```

- [ ] **Bước 2: Chạy test, xác nhận ĐỎ**

```bash
bash $SCRATCH/run_test.sh "hrms.hr.tests.test_leave_type_code"
bash $SCRATCH/run_test.sh "hrms.tests.test_setup_vn_defaults"
```
Expected: FAIL — cướp mã không raise; `ImportError: leave_types_without_code`.

- [ ] **Bước 3: Chống cướp mã**

Trong `hrms/hr/leave_type_code.py::sync_code_to_leave_type`, ngay **sau** khối kiểm tra
`status not in LEAVE_STATUSES` và **trước** vòng dọn mã cũ, chèn:

```python
	# Mã đang thuộc một loại nghỉ KHÁC thì đây là đổi chủ, không phải gắn mới. Trước 2026-08-24
	# đoạn dưới ghi đè trong im lặng: HR tạo loại nghỉ mới để thay "Nghỉ phép năm", chọn `P`, và
	# `P` rời khỏi "Nghỉ phép năm" — mọi ngày phép cũ mất đường tra ngược. Đổi chủ phải là việc cố
	# ý, làm thẳng ở Attendance Code.
	owner = frappe.db.get_value("Attendance Code", code, "leave_type")
	if owner and owner != leave_type:
		frappe.throw(
			_(
				"Mã công {0} đang ứng với loại nghỉ {1}. Chọn một mã khác, hoặc gỡ liên kết ở "
				"Mã Công {0} trước nếu thật sự muốn chuyển mã sang {2}."
			).format(frappe.bold(code), frappe.bold(owner), frappe.bold(leave_type)),
			title=_("Mã công đã có chủ"),
		)
```

- [ ] **Bước 4: Cảnh báo đỏ, nói rõ hệ quả**

Trong cùng file, thay thân `warn_if_unmapped` bằng:

```python
	if doc.get("name") and not full_day_code_for(doc.get("name")):
		frappe.msgprint(
			_(
				"Loại nghỉ {0} chưa có mã công nào. Ngày nghỉ theo loại này sẽ ra <b>0 công</b> và "
				"để trống trên bảng chấm công, còn đơn nghỉ theo loại này sẽ bị chặn. Chọn "
				"\"Mã công cả ngày\" ở trên, hoặc tạo một Mã Công có Loại nghỉ = {0}."
			).format(frappe.bold(doc.get("name"))),
			title=_("Chưa gắn mã công"),
			indicator="red",
		)
```

- [ ] **Bước 5: Soi lúc migrate**

Trong `hrms/setup_vn_defaults.py`, thêm hàm và nối vào `ensure_defaults`:

```python
def leave_types_without_code() -> list[str]:
	"""Loại nghỉ chưa có mã công CẢ NGÀY nào trỏ tới — ngày nghỉ theo chúng sẽ ra 0 công.

	Không tự sửa: mã công là master data do HR quyết, đoán một ký hiệu thay họ chỉ tạo rác."""
	linked = set(
		frappe.get_all(
			"Attendance Code",
			filters={"maps_to_status": "On Leave", "leave_type": ("is", "set")},
			pluck="leave_type",
		)
	)
	return sorted(name for name in frappe.get_all("Leave Type", pluck="name") if name not in linked)
```

Trong `ensure_defaults()`, sau khối `missing`:

```python
	unmapped = leave_types_without_code()
	if unmapped:
		frappe.logger("hrms").warning(
			f"hrms.setup_vn_defaults.ensure_defaults: loại nghỉ chưa có mã công cả ngày "
			f"(ngày nghỉ theo chúng sẽ ra 0 công): {unmapped}"
		)
```

và thêm vào dict trả về:

```python
		"leave_types_without_code": unmapped,
```

Cập nhật docstring đầu module: liệt kê thêm việc soi loại nghỉ chưa gắn mã.

- [ ] **Bước 6: Chạy test, xác nhận XANH**

```bash
bash $SCRATCH/run_test.sh "hrms.hr.tests.test_leave_type_code"
bash $SCRATCH/run_test.sh "hrms.tests.test_setup_vn_defaults"
```
Expected: `RESULT: OK` cả hai, `HARNESS_NO_LEAK`.

- [ ] **Bước 7: Lint + commit**

```bash
cd /home/miyano/frappe-bench/apps/hrms
pre-commit run --files hrms/hr/leave_type_code.py hrms/setup_vn_defaults.py \
  hrms/hr/tests/test_leave_type_code.py hrms/tests/test_setup_vn_defaults.py
git add hrms/hr/leave_type_code.py hrms/setup_vn_defaults.py \
  hrms/hr/tests/test_leave_type_code.py hrms/tests/test_setup_vn_defaults.py
git commit -m "feat(hr): khong cho cuop ma cong cua loai nghi khac, soi loai nghi thieu ma"
```

---

### Task 4: Chốt chặn ở Đơn xin nghỉ

**Files:**
- Modify: `hrms/hr/doctype/leave_application/leave_single_pool.py`
- Modify: `hrms/hooks.py:160-163`
- Test: `hrms/hr/doctype/leave_application/test_leave_type_code_gate.py` (tạo mới)

**Interfaces:**
- Consumes: `leave_single_pool.code_for_leave_type(leave_type, status) -> str | None`
- Produces: `leave_single_pool.validate_leave_type_has_code(doc, method=None)`

- [ ] **Bước 1: Viết test đỏ**

`hrms/hr/doctype/leave_application/test_leave_type_code_gate.py`:

```python
# Copyright (c) 2026, Miyano Việt Nam.
"""Chốt chặn: đơn nghỉ theo loại chưa có mã công thì KHÔNG lưu được.

Đây là chỗ duy nhất chặn được mà không bế tắc con-gà-quả-trứng — lúc này cả loại nghỉ lẫn mã đều đã
có cơ hội tồn tại. Không có chốt này thì ngày nghỉ ra 0 công trong im lặng (spec §1.1).

Chốt gắn vào `before_validate`, KHÔNG phải `validate`: `Document.hook` chạy method của controller
TRƯỚC rồi mới tới hook của `doc_events` (xem `frappe/model/document.py::hook`), nên gắn vào
`validate` thì `LeaveApplication.validate()` của upstream (số dư phép, trùng đơn, ngày lễ) nổ trước
— người dùng thấy sai nguyên nhân, và test thì xanh vì nhầm lý do.

Chạy qua harness rollback (KHÔNG bench run-tests trên miyano).
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import default_company, test_employee

UNMAPPED = "Nghỉ thử chưa có mã"


class TestLeaveTypeCodeGate(PerTestRollback, FrappeTestCase):
	def setUp(self):
		self.employee = test_employee("gate_ma_cong@codes.com")
		self.company = default_company()

	def unmapped_leave_type(self):
		frappe.get_doc({"doctype": "Leave Type", "leave_type_name": UNMAPPED, "is_lwp": 0}).insert(
			ignore_permissions=True
		)
		return UNMAPPED

	def allocate(self, leave_type):
		alloc = frappe.get_doc(
			{
				"doctype": "Leave Allocation",
				"employee": self.employee,
				"leave_type": leave_type,
				"from_date": "2099-01-01",
				"to_date": "2099-12-31",
				"new_leaves_allocated": 10,
			}
		)
		alloc.insert(ignore_permissions=True)
		alloc.submit()

	def leave_doc(self, leave_type, day, half_day=0):
		return frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": self.employee,
				"leave_type": leave_type,
				"from_date": day,
				"to_date": day,
				"half_day": half_day,
				"half_day_date": day if half_day else None,
				"custom_half_day_period": "Sáng" if half_day else None,
				"company": self.company,
				"status": "Approved",
				"leave_approver": frappe.session.user,
			}
		)

	def test_blocks_a_leave_type_with_no_full_day_code(self):
		"""Loại nghỉ chưa gắn mã → chặn ngay, và chặn vì ĐÚNG lý do (không phải hết phép)."""
		lt = self.unmapped_leave_type()
		self.allocate(lt)  # số dư đủ → nếu vẫn chặn thì đúng là do thiếu mã
		with self.assertRaisesRegex(frappe.ValidationError, "mã công"):
			self.leave_doc(lt, "2099-06-15").insert(ignore_permissions=True)

	def test_blocks_half_day_when_only_a_full_day_code_exists(self):
		"""Nghỉ NỬA ngày cần mã Half Day riêng — "Nghỉ ốm" chỉ có `Ô` (cả ngày)."""
		self.allocate("Nghỉ ốm")
		with self.assertRaisesRegex(frappe.ValidationError, "Half Day"):
			self.leave_doc("Nghỉ ốm", "2099-06-15", half_day=1).insert(ignore_permissions=True)

	def test_allows_a_leave_type_that_has_both_codes(self):
		"""Đối chứng: "Nghỉ phép năm" có cả `P` lẫn `1/2P` → cả hai dạng đều qua.

		Hai ngày KHÁC nhau: cùng ngày sẽ vướng chốt trùng đơn của upstream, không liên quan gì
		tới thứ test này đang đo."""
		self.allocate("Nghỉ phép năm")
		self.leave_doc("Nghỉ phép năm", "2099-06-15").insert(ignore_permissions=True)
		self.leave_doc("Nghỉ phép năm", "2099-06-17", half_day=1).insert(ignore_permissions=True)

	def test_message_names_the_leave_type_and_the_status_needed(self):
		"""Thông báo phải nói đủ để HR tự sửa được, không bắt đi hỏi."""
		lt = self.unmapped_leave_type()
		self.allocate(lt)
		with self.assertRaises(frappe.ValidationError):
			self.leave_doc(lt, "2099-06-15").insert(ignore_permissions=True)
		message = str(frappe.message_log[-1]) if frappe.message_log else ""
		self.assertIn(lt, message)
		self.assertIn("On Leave", message)

	def test_half_day_without_a_period_is_rejected(self):
		"""Nửa ngày mà không nói nửa nào thì bản ghi là mơ hồ — chặn, cho MỌI loại nghỉ."""
		self.allocate("Nghỉ phép năm")
		doc = self.leave_doc("Nghỉ phép năm", "2099-06-15", half_day=1)
		doc.custom_half_day_period = None
		with self.assertRaises(frappe.ValidationError):
			doc.insert(ignore_permissions=True)
```

- [ ] **Bước 2: Chạy test, xác nhận ĐỎ**

Run: `bash $SCRATCH/run_test.sh "hrms.hr.doctype.leave_application.test_leave_type_code_gate"`
Expected: FAIL — đơn nghỉ theo loại chưa có mã vẫn lưu được.

- [ ] **Bước 3: Viết chốt chặn**

Thêm vào `hrms/hr/doctype/leave_application/leave_single_pool.py`:

```python
def validate_leave_type_has_code(doc, method=None):
	"""Loại nghỉ của đơn phải có mã công ứng với TRẠNG THÁI mà đơn sẽ sinh ra.

	Không có mã thì ngày nghỉ ra 0 công và bảng chấm công để trống — hoặc tệ hơn, giữ nguyên mã `V`
	của bản ghi vắng có sẵn, làm lương (đọc `status`) và bảng công (đọc mã) nói ngược nhau.

	Gắn vào `before_validate`, KHÔNG phải `validate`: `Document.hook` chạy method của controller
	TRƯỚC rồi mới tới hook `doc_events`, nên ở `validate` thì mọi chốt của upstream (số dư phép,
	trùng đơn, ngày lễ) nổ trước và người dùng thấy sai nguyên nhân. Thiếu mã công là vấn đề gốc
	hơn số dư phép, phải báo trước.

	Đơn nghỉ nửa ngày cần THÊM một mã `Half Day` (token đơn kiểu `1/2P`) — mã cả ngày không mô tả
	được nửa ngày đi làm. Cách chữa cho cả hai là tạo một Mã Công, một dòng master data.
	"""
	leave_type = doc.get("leave_type")
	if not leave_type:
		return

	needed = ["On Leave"]
	if cint(doc.get("half_day")):
		needed.append("Half Day")

	for status in needed:
		if code_for_leave_type(leave_type, status):
			continue
		frappe.throw(
			frappe._(
				"Loại nghỉ {0} chưa có mã công cho trạng thái {1}. Tạo một Mã Công với "
				"Trạng thái = {1} và Loại nghỉ = {0}, rồi lưu lại đơn này."
			).format(frappe.bold(leave_type), frappe.bold(status)),
			title=frappe._("Thiếu mã công"),
		)
```

- [ ] **Bước 4: Đăng ký hook**

Trong `hrms/hooks.py`, đổi khối `"Leave Application"` thành:

```python
	# Miyano: chốt chặn loại nghỉ phải có mã công (before_validate — phải nổ TRƯỚC chốt số dư phép
	# của upstream); validate mã lý do; sau duyệt ghi mã lên Attendance (thuần hiển thị).
	"Leave Application": {
		"before_validate": "hrms.hr.doctype.leave_application.leave_single_pool.validate_leave_type_has_code",
		"validate": "hrms.hr.doctype.leave_application.leave_single_pool.validate_pool_code",
		"on_submit": "hrms.hr.doctype.leave_application.leave_single_pool.set_leave_attendance_code",
	},
```

- [ ] **Bước 5: Chạy test, xác nhận XANH**

Run: `bash $SCRATCH/run_test.sh "hrms.hr.doctype.leave_application.test_leave_type_code_gate"`
Expected: `RESULT: OK`, `HARNESS_NO_LEAK`

- [ ] **Bước 6: Bộ test đơn nghỉ cũ không được vỡ**

```bash
for m in hrms.hr.doctype.leave_application.test_leave_single_pool \
         hrms.hr.doctype.leave_application.test_half_day_leave_payroll \
         hrms.hr.doctype.leave_application.test_leave_code_on_existing_attendance; do
  bash $SCRATCH/run_test.sh "$m"
done
```
Expected: `RESULT: OK` cả ba.

- [ ] **Bước 7: Lint + commit**

```bash
cd /home/miyano/frappe-bench/apps/hrms
pre-commit run --files hrms/hr/doctype/leave_application/leave_single_pool.py hrms/hooks.py \
  hrms/hr/doctype/leave_application/test_leave_type_code_gate.py
git add hrms/hr/doctype/leave_application/leave_single_pool.py hrms/hooks.py \
  hrms/hr/doctype/leave_application/test_leave_type_code_gate.py
git commit -m "feat(hr): chan don nghi theo loai chua co ma cong"
```

---

### Task 5: Gỡ hằng cứng "Nghỉ phép năm" — mọi loại nghỉ đi chung một đường

Refactor thuần: **hành vi không được đổi**. Bộ test của Task 4 và các test đơn nghỉ cũ là lưới an toàn.

**Files:**
- Create: `hrms/hr/doctype/leave_application/leave_attendance_code.py` (nội dung rút gọn của
  `leave_single_pool.py`)
- Delete: `hrms/hr/doctype/leave_application/leave_single_pool.py`
- Rename: `test_leave_single_pool.py` → `test_leave_attendance_code.py`
- Modify: `hrms/hooks.py`, `hrms/fixtures/custom_field.json`, `frontend/src/views/leave/Form.vue:263-273`
- Modify (import): `hrms/hr/doctype/leave_application/test_half_day_leave_payroll.py`,
  `test_leave_code_on_existing_attendance.py`, `hrms/hr/doctype/attendance/test_code_resync_on_leave_record.py`,
  `hrms/hr/doctype/leave_application/test_leave_type_code_gate.py` và mọi file khác `grep` ra

**Interfaces:**
- Produces: `leave_attendance_code.code_for_leave_type`, `.work_credit`,
  `.validate_leave_type_has_code`, `.validate_half_day_period`, `.set_leave_attendance_code`
- Removed: `POOL_LEAVE_TYPE`, `POOL_REASONS`, `HALF_DAY_CODE`, `resolve_reason_code`, `validate_pool_code`

- [ ] **Bước 1: Ghi lại đối chứng TRƯỚC khi sửa**

Thêm vào `hrms/hr/doctype/leave_application/test_leave_type_code_gate.py`:

```python
	def test_annual_leave_still_derives_the_same_codes_after_the_constants_go(self):
		"""Đối chứng gỡ hằng: "Nghỉ phép năm" phải ra đúng `P` / `1/2P` như thời còn POOL_REASONS."""
		from hrms.hr.doctype.leave_application.leave_single_pool import code_for_leave_type

		self.assertEqual(code_for_leave_type("Nghỉ phép năm", "On Leave"), "P")
		self.assertEqual(code_for_leave_type("Nghỉ phép năm", "Half Day"), "1/2P")
		self.assertEqual(code_for_leave_type("Nghỉ không lương", "On Leave"), "K")
		self.assertEqual(code_for_leave_type("Nghỉ không lương", "Half Day"), "1/2K")
```

Run: `bash $SCRATCH/run_test.sh "hrms.hr.doctype.leave_application.test_leave_type_code_gate"`
Expected: `RESULT: OK` — đây là **tiền đề**, phải xanh TRƯỚC khi gỡ hằng.

- [ ] **Bước 2: Tạo module mới**

`git mv hrms/hr/doctype/leave_application/leave_single_pool.py hrms/hr/doctype/leave_application/leave_attendance_code.py`
rồi sửa nội dung:

- Xoá `POOL_LEAVE_TYPE`, `POOL_REASONS`, `HALF_DAY_CODE`, `resolve_reason_code`, `validate_pool_code`.
- Giữ nguyên `code_for_leave_type`, `work_credit`, `validate_leave_type_has_code`.
- Thêm `validate_half_day_period` (tách từ `validate_pool_code`, nay áp cho mọi loại nghỉ):

```python
def validate_half_day_period(doc, method=None):
	"""Nghỉ nửa ngày phải chọn buổi (Sáng/Chiều) — cho MỌI loại nghỉ.

	Không phải luật mới: fixture của trường đã khai `mandatory_depends_on = eval:doc.half_day` và
	PWA cũng bắt buộc. Chỉ có chốt phía server là đang hẹp hơn khai báo (chỉ bắt với quỹ phép năm),
	nay khớp lại — nếu không, đường ghi qua API vẫn lọt bản ghi nửa ngày không rõ nửa nào."""
	if cint(doc.get("half_day")) and not doc.get("custom_half_day_period"):
		frappe.throw(frappe._("Nghỉ nửa ngày phải chọn buổi nghỉ: Sáng hay Chiều."))
```

- Thay `set_leave_attendance_code` bằng bản chỉ tra bảng:

```python
def set_leave_attendance_code(doc, method=None):
	"""Sau khi Đơn xin nghỉ duyệt sinh Attendance (upstream ``update_attendance``), ghi mã suy từ
	bảng ``Attendance Code`` lên Attendance để bảng công hiện đúng — MỘT đường cho mọi loại nghỉ.

	Không thể phó mặc cho bridge reverse-derive: khi ngày đó ĐÃ có bản ghi (Vắng do auto-attendance),
	upstream đi nhánh ``db_set`` nên ``before_validate`` không chạy và mã ``V`` kẹt lại dù status đã
	là On Leave.

	Trước 2026-08-24 "Nghỉ phép năm" đi một nhánh riêng qua hằng ``POOL_REASONS``; đã kiểm chứng
	nhánh đó cho ĐÚNG cùng kết quả với việc tra bảng, nên nó bị gỡ — mã công là neo duy nhất.

	THUẦN HIỂN THỊ: chỉ đặt mã qua ``db_set`` — không đụng status/leave_type/half_day_status nên
	lương không đổi. Ngày nghỉ nửa ngày dùng token đơn (1/2P)."""
	leave_type = doc.get("leave_type")
	full_code = code_for_leave_type(leave_type, "On Leave")
	half_code = code_for_leave_type(leave_type, "Half Day")
	half_day_date = doc.get("half_day_date")
	is_half = cint(doc.get("half_day")) and half_day_date

	for att in frappe.get_all(
		"Attendance",
		filters={"leave_application": doc.name, "docstatus": ["<", 2]},
		fields=["name", "attendance_date"],
	):
		day_code = (
			half_code if is_half and getdate(att.attendance_date) == getdate(half_day_date) else full_code
		)
		if not day_code:
			continue  # không map được thì GIỮ NGUYÊN mã cũ, không bịa

		# db_set thuần hiển thị nên không đụng status/leave_type/half_day_status → lương bất biến.
		frappe.db.set_value(
			"Attendance",
			att.name,
			{
				"custom_attendance_code": day_code,
				"custom_morning_code": None,
				"custom_afternoon_code": None,
				"custom_work_credit": work_credit(day_code),
			},
			update_modified=False,
		)
```

- Viết lại docstring đầu module cho khớp tên mới (chủ đề: suy mã công cho đơn nghỉ, mã công là neo;
  trỏ tới `docs/spec/attendance-code-as-anchor.md`).

- [ ] **Bước 3: Cập nhật hooks**

```python
	# Miyano: mã công là neo — chặn loại nghỉ chưa có mã, bắt chọn buổi khi nghỉ nửa ngày. Cả hai ở
	# `before_validate` để nổ TRƯỚC chốt số dư phép của upstream (xem docstring của module). Sau
	# duyệt thì ghi mã lên Attendance (thuần hiển thị).
	"Leave Application": {
		"before_validate": [
			"hrms.hr.doctype.leave_application.leave_attendance_code.validate_leave_type_has_code",
			"hrms.hr.doctype.leave_application.leave_attendance_code.validate_half_day_period",
		],
		"on_submit": "hrms.hr.doctype.leave_application.leave_attendance_code.set_leave_attendance_code",
	},
```

- [ ] **Bước 4: Sửa mọi import còn trỏ tên cũ**

Run: `cd /home/miyano/frappe-bench/apps/hrms && grep -rn "leave_single_pool" --include=*.py --include=*.md .`
Sửa hết sang `leave_attendance_code`. `git mv` file test:
`git mv hrms/hr/doctype/leave_application/test_leave_single_pool.py hrms/hr/doctype/leave_application/test_leave_attendance_code.py`
Trong file test đó, bỏ các test chỉ kiểm `validate_pool_code`/`resolve_reason_code`; giữ và đổi
tên các test kiểm mã ghi lên Attendance.

- [ ] **Bước 5: Gỡ hardcode trong fixtures**

Trong `hrms/fixtures/custom_field.json`, với bản ghi `Leave Application-custom_leave_reason`:
đặt `"depends_on": null` và `"mandatory_depends_on": null` (trường giữ lại làm dấu vết lịch sử,
thôi bắt buộc và thôi gắn với một tên loại nghỉ cụ thể).

Bộ lọc `fixtures` trong `hooks.py` **không đổi** (tên trường không đổi) — nhưng chạy
`bash $SCRATCH/run_test.sh "hrms.tests.test_setup_vn_defaults"` để chắc.

- [ ] **Bước 6: Gỡ hardcode trong PWA**

Trong `frontend/src/views/leave/Form.vue`, thay `setLeaveReasonVisibility` bằng:

```js
// Miyano: "Loại nghỉ" chỉ còn là ghi chú, không suy ra mã công nữa — mã công tra thẳng từ
// Attendance Code (xem docs/spec/attendance-code-as-anchor.md). Ẩn hẳn khỏi đơn.
function setLeaveReasonVisibility() {
	const field = formFields.data?.find(
		(field) => field.fieldname === "custom_leave_reason"
	)
	if (!field) return
	field.hidden = true
	field.reqd = false
}
```

Sửa mọi nơi gọi hàm này để bỏ tham số `leave_type`.

- [ ] **Bước 7: Build lại PWA**

Run: `cd /home/miyano/frappe-bench/apps/hrms && yarn build`
Expected: build xong không lỗi.

- [ ] **Bước 8: Chạy toàn bộ test đơn nghỉ + chấm công**

```bash
for m in hrms.hr.doctype.leave_application.test_leave_type_code_gate \
         hrms.hr.doctype.leave_application.test_leave_attendance_code \
         hrms.hr.doctype.leave_application.test_half_day_leave_payroll \
         hrms.hr.doctype.leave_application.test_leave_code_on_existing_attendance \
         hrms.hr.doctype.attendance.test_code_resync_on_leave_record \
         hrms.hr.doctype.attendance.test_attendance_code_bridge; do
  bash $SCRATCH/run_test.sh "$m"
done
```
Expected: `RESULT: OK` cả sáu. Bước 1 đã chốt đối chứng `P`/`1/2P` nên nếu hành vi lệch là lộ ngay.

- [ ] **Bước 9: Lint + commit**

```bash
cd /home/miyano/frappe-bench/apps/hrms
pre-commit run --all-files
git add hrms/hr/doctype/leave_application/ hrms/hooks.py hrms/fixtures/custom_field.json \
  frontend/src/views/leave/Form.vue hrms/hr/doctype/attendance/test_code_resync_on_leave_record.py
git commit -m "refactor(hr): go hang cung Nghi phep nam, moi loai nghi tra bang ma cong"
```

---

### Task 6: Xác minh đầu-cuối + cổng bất biến lương

**Files:**
- Test: `hrms/hr/tests/test_custom_leave_type_end_to_end.py` (tạo mới)
- Modify: `docs/spec/attendance-code-as-anchor.md` (đổi Trạng thái sang Implemented)

**Interfaces:**
- Consumes: mọi thứ của Task 1–5

- [ ] **Bước 1: Viết test đầu-cuối — đúng kịch bản đã tái hiện ở spec §1.1**

`hrms/hr/tests/test_custom_leave_type_end_to_end.py`:

```python
# Copyright (c) 2026, Miyano Việt Nam.
"""Loại nghỉ HR tự tạo phải chạy ĐÚNG như loại nghỉ fixtures — đó là cả mục tiêu của thay đổi này.

Tái hiện đúng sự cố 2026-08-24 (spec §1.1): loại nghỉ tạo tay không gắn mã cho ra 0 công, im lặng.
Sau thay đổi: chưa gắn mã thì bị CHẶN; gắn một dòng Mã Công là ra đúng mã và CÔNG = 1, trên cả hai
đường (ngày chưa có chấm công, và ngày đã có bản ghi Vắng).

Chạy qua harness rollback (KHÔNG bench run-tests trên miyano).
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import default_company, test_employee

LEAVE_TYPE = "Nghỉ chuyên cần Miyano"
CODE = "CC"
DAY_FRESH = "2099-06-15"
DAY_WITH_ABSENT = "2099-06-16"


class TestCustomLeaveTypeEndToEnd(PerTestRollback, FrappeTestCase):
	def setUp(self):
		self.employee = test_employee("loai_nghi_tu_tao@codes.com")
		self.company = default_company()
		frappe.get_doc(
			{"doctype": "Leave Type", "leave_type_name": LEAVE_TYPE, "is_lwp": 0, "max_leaves_allowed": 30}
		).insert(ignore_permissions=True)

	def add_code(self):
		"""ĐÚNG MỘT dòng master data — đây là toàn bộ việc HR phải làm cho một loại nghỉ mới."""
		frappe.get_doc(
			{
				"doctype": "Attendance Code",
				"code": CODE,
				"code_name": "Nghỉ chuyên cần",
				"category": "Việc riêng",
				"work_fraction": 0,
				"is_paid": 1,
				"maps_to_status": "On Leave",
				"leave_type": LEAVE_TYPE,
			}
		).insert(ignore_permissions=True)

	def allocate(self):
		alloc = frappe.get_doc(
			{
				"doctype": "Leave Allocation",
				"employee": self.employee,
				"leave_type": LEAVE_TYPE,
				"from_date": "2099-01-01",
				"to_date": "2099-12-31",
				"new_leaves_allocated": 10,
			}
		)
		alloc.insert(ignore_permissions=True)
		alloc.submit()

	def apply_leave(self, day):
		la = frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": self.employee,
				"leave_type": LEAVE_TYPE,
				"from_date": day,
				"to_date": day,
				"company": self.company,
				"status": "Approved",
				"leave_approver": frappe.session.user,
			}
		)
		la.insert(ignore_permissions=True)
		la.submit()
		return la

	def mark_absent(self, day):
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.employee,
				"attendance_date": day,
				"status": "Absent",
				"company": self.company,
			}
		)
		att.insert(ignore_permissions=True)
		att.submit()

	def attendance_of(self, leave_application):
		return frappe.get_all(
			"Attendance",
			filters={"leave_application": leave_application},
			fields=["status", "leave_type", "custom_attendance_code", "custom_work_credit"],
		)[0]

	def test_unmapped_leave_type_is_blocked_not_silently_zero(self):
		"""TRƯỚC: 0 công trong im lặng. SAU: chặn thẳng, kèm hướng dẫn."""
		self.allocate()
		with self.assertRaises(frappe.ValidationError):
			self.apply_leave(DAY_FRESH)

	def test_one_code_makes_a_fresh_day_worth_one_cong(self):
		"""Ngày chưa có chấm công → mã đúng, CÔNG = 1."""
		self.add_code()
		self.allocate()
		att = self.attendance_of(self.apply_leave(DAY_FRESH).name)
		self.assertEqual(att.status, "On Leave")
		self.assertEqual(att.leave_type, LEAVE_TYPE)
		self.assertEqual(att.custom_attendance_code, CODE)
		self.assertEqual(att.custom_work_credit, 1.0)

	def test_one_code_also_fixes_a_day_already_marked_absent(self):
		"""Ngày ĐÃ có bản ghi Vắng — đường `db_set` của upstream, chỗ mã `V` từng kẹt lại."""
		self.add_code()
		self.allocate()
		self.mark_absent(DAY_WITH_ABSENT)
		att = self.attendance_of(self.apply_leave(DAY_WITH_ABSENT).name)
		self.assertEqual(att.status, "On Leave")
		self.assertEqual(att.custom_attendance_code, CODE, "mã V không được kẹt lại")
		self.assertEqual(att.custom_work_credit, 1.0)

	def test_the_day_lands_in_the_right_column_of_the_monthly_sheet(self):
		"""Mã có nhóm "Việc riêng" → ngày đó phải vào đúng cột đó và cộng vào Tổng công."""
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import get_sheet_rows

		self.add_code()
		self.allocate()
		self.apply_leave(DAY_FRESH)

		rows = [
			r
			for r in get_sheet_rows({"month": 6, "year": 2099, "company": self.company})
			if r["employee"] == self.employee
		]
		self.assertTrue(rows, "nhân viên phải có mặt trên bảng công")
		row = rows[0]
		self.assertEqual(row["days"].get(getdate(DAY_FRESH).day), CODE)
		self.assertEqual(row["totals"].get("Việc riêng"), 1.0)
```

- [ ] **Bước 2: Chạy, xác nhận XANH**

Run: `bash $SCRATCH/run_test.sh "hrms.hr.tests.test_custom_leave_type_end_to_end"`
Expected: `RESULT: OK`, `HARNESS_NO_LEAK`

- [ ] **Bước 3: Cổng bất biến lương**

Chạy bộ bất biến lương đang có:

```bash
for m in hrms.payroll.doctype.salary_slip.test_attendance_code_payroll_invariance \
         hrms.tests.test_payroll_gate \
         hrms.tests.test_flex_shift_payroll_gate; do
  bash $SCRATCH/run_test.sh "$m"
done
```
Expected: `RESULT: OK` cả ba.

Rồi chụp lại dữ liệu thật bằng đúng `$SCRATCH/payroll_snapshot.py` của Task 1 Bước 2, ghi ra
`$SCRATCH/payroll_after.txt`, và so:

```bash
diff $SCRATCH/payroll_before.txt $SCRATCH/payroll_after.txt && echo "PAYROLL BAT BIEN"
```
Expected: `diff` không in gì, in ra `PAYROLL BAT BIEN`. Lệch một con số là **dừng lại**, không đi
tiếp — chép cả hai đầu ra vào phần kết luận của spec dù trùng hay lệch.

- [ ] **Bước 4: Chạy lại toàn bộ test VN**

```bash
for m in $(cd /home/miyano/frappe-bench/apps/hrms && \
  find hrms -name "test_*.py" | sed 's|/|.|g; s|\.py$||'); do
  echo "### $m"; bash $SCRATCH/run_test.sh "$m" 2>&1 | tail -3
done
```
So với baseline đỏ sẵn có (mốc 2026-07-24: 190 test / 0 fail / 9 error, đều là nhiễu
`_Test Company`). **Không được có lỗi đỏ mới.**

- [ ] **Bước 5: Cập nhật spec**

Trong `docs/spec/attendance-code-as-anchor.md`: đổi dòng Trạng thái thành
`**Implemented** — <ngày>` kèm số test xanh, và thêm hai con số của cổng bất biến lương.

- [ ] **Bước 6: Lint + commit**

```bash
cd /home/miyano/frappe-bench/apps/hrms
pre-commit run --all-files
git add hrms/hr/tests/test_custom_leave_type_end_to_end.py docs/spec/attendance-code-as-anchor.md
git commit -m "test(hr): loai nghi tu tao chay dung nhu loai nghi fixtures"
```

---

## Sau khi xong

**Chưa deploy.** Task 1 đổi schema (`bench migrate`) và Task 5 đổi fixtures — cả hai đã chạy trên
`miyano` trong quá trình build, nhưng việc **bật cho người dùng** (build lại desk bundle, khởi động
lại app) cần hỏi trước theo cổng sign-off của `CLAUDE.md`. `bench build --app hrms` chỉ cần nếu có
sửa `hrms/public/js/*` — kế hoạch này không sửa.

Hai việc HR phải biết sau khi deploy:

1. Tạo Loại nghỉ mới = **hai bước**: tạo Loại nghỉ, rồi tạo Mã Công trỏ tới nó (chọn nhóm cột). Quên
   bước hai thì đơn nghỉ theo loại đó bị chặn kèm hướng dẫn — không còn ra 0 công trong im lặng.
2. Muốn nghỉ **nửa ngày** theo loại đó thì cần thêm một Mã Công `Half Day` nữa (kiểu `1/2P`).
