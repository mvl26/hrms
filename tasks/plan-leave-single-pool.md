# Kế hoạch: Gộp một quỹ phép năm — Bậc 2 (field + hook + cấu hình)

> **For agentic workers:** build TDD từng task, mỗi task RED → GREEN → regression → commit riêng.
> Test qua **harness rollback** env-python (KHÔNG `bench run-tests` trên miyano; KHÔNG ghi site).

**Goal:** Đơn xin nghỉ lý do P/Ô/Cô cùng rút một quỹ "Nghỉ phép năm" (Frappe tự chặn khi hết), nhưng
bảng công vẫn hiện Ô/Cô/P riêng; TS/N/T miễn trừ, K không lương — **lương bất biến**.

**Architecture:** Đơn xin nghỉ nhóm trừ-quỹ đặt `leave_type="Nghỉ phép năm"` + field `custom_attendance_code`
(lý do). Hook `Leave Application.on_submit` (chạy SAU `update_attendance` của upstream) **ghi đè
`custom_attendance_code`** lên Attendance vừa sinh — thuần hiển thị (db_set, không đổi
status/leave_type/half_day_status). Bảng công phân nhóm + tô màu theo `category` của Attendance Code
nên hiển thị đúng Ô/Cô, còn số dư rút từ một quỹ.

**Tech Stack:** Frappe/ERPNext HRMS v15, Python controllers + fixtures JSON, doc_events hook.

## Global Constraints

- **KHÔNG ghi site, KHÔNG deploy** trong lúc build — chỉ nhánh `feat/skip-attendance-diag` + harness rollback.
- **Lương bất biến**: mỗi task đụng bridge/leave phải chứng minh Salary Slip `payment_days`/`absent_days`/LWP không đổi.
- **Additive, git-revert được**: hook + 1 custom field + (fixture Attendance Code ask-first). Không sửa logic upstream.
- **Bậc 1 (WS3) coi như đã có code** (`hrms/setup_vn_leave.py`); test tự tạo allocation trong harness, không phụ thuộc site.
- Mã trừ-quỹ: `DEDUCTING_CODES = {"P", "1/2P", "Ô", "Cô"}`. Miễn trừ: TS/N/T. Không lương: K/1/2K.
- Test qua harness: `cd /home/miyano/frappe-bench/sites && ../env/bin/python <harness>` (env `HARNESS_MODULES`).

---

### Task 1: Đặc tả hành vi hiện tại (characterization) — đơn phép năm → Attendance "P"

**Files:**
- Test: `hrms/hr/doctype/leave_application/test_leave_single_pool.py` (mới)

**Interfaces:**
- Produces: `_annual_leave_app(emp, from_d, to_d, days_alloc)` helper dùng lại ở task sau.

- [ ] **Step 1: Viết test đặc tả** — nhân viên có allocation "Nghỉ phép năm", nộp+duyệt đơn 1 ngày → Attendance sinh ra `status="On Leave"`, `leave_type="Nghỉ phép năm"`, và (qua bridge) `custom_attendance_code="P"`.

```python
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, nowdate

class TestLeaveSinglePool(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.emp = frappe.db.get_value("Employee", {"status": "Active"}, "name")

	def _alloc(self, leave_type, days, year=2099):
		a = frappe.get_doc({
			"doctype": "Leave Allocation", "employee": self.emp, "leave_type": leave_type,
			"from_date": f"{year}-01-01", "to_date": f"{year}-12-31",
			"new_leaves_allocated": days,
		})
		a.insert(); a.submit(); return a

	def _leave_app(self, leave_type, from_d, to_d, code=None):
		la = frappe.get_doc({
			"doctype": "Leave Application", "employee": self.emp, "leave_type": leave_type,
			"from_date": from_d, "to_date": to_d, "status": "Approved",
		})
		if code:
			la.custom_attendance_code = code
		la.insert(); la.submit(); return la

	def test_annual_leave_app_creates_P_attendance(self):
		self._alloc("Nghỉ phép năm", 12)
		la = self._leave_app("Nghỉ phép năm", "2099-03-05", "2099-03-05")
		att = frappe.db.get_value("Attendance", {"leave_application": la.name},
			["status", "leave_type", "custom_attendance_code"], as_dict=True)
		self.assertEqual(att.status, "On Leave")
		self.assertEqual(att.leave_type, "Nghỉ phép năm")
		self.assertEqual(att.custom_attendance_code, "P")  # reverse-derived by bridge
```

- [ ] **Step 2: Chạy để xác nhận hành vi nền** (có thể cần chỉnh field allocation cho khớp version)

Run: harness `HARNESS_MODULES=hrms.hr.doctype.leave_application.test_leave_single_pool`
Expected: PASS (nếu FAIL vì tên field allocation → sửa test cho khớp, đây là bước đặc tả).

- [ ] **Step 3: Commit**

```bash
git add hrms/hr/doctype/leave_application/test_leave_single_pool.py
git commit -m "test(hr): dac ta don phep nam -> Attendance P (nen bac 2 gop quy)"
```

---

### Task 2: Custom field `custom_attendance_code` trên Leave Application

**Files:**
- Modify: `hrms/fixtures/custom_field.json` (thêm 1 field)
- Modify: `hrms/hooks.py` (bộ lọc fixtures `custom_field` — thêm `Leave Application-custom_attendance_code`)
- Test: `hrms/hr/doctype/leave_application/test_leave_single_pool.py`

**Interfaces:**
- Produces: field `Leave Application.custom_attendance_code` (Link "Attendance Code").

- [ ] **Step 1: Viết test field tồn tại đúng thuộc tính**

```python
	def test_custom_code_field_exists_on_leave_application(self):
		meta = frappe.get_meta("Leave Application")
		f = meta.get_field("custom_attendance_code")
		self.assertIsNotNone(f)
		self.assertEqual(f.fieldtype, "Link")
		self.assertEqual(f.options, "Attendance Code")
```

- [ ] **Step 2: Chạy → FAIL** (field chưa có). Run harness như Task 1.

- [ ] **Step 3: Thêm fixture custom field** vào `hrms/fixtures/custom_field.json` (khối JSON, `dt="Leave Application"`, `fieldname="custom_attendance_code"`, `fieldtype="Link"`, `options="Attendance Code"`, `label="Mã chấm công"`, `insert_after="leave_type"`), và thêm `"Leave Application-custom_attendance_code"` vào danh sách lọc `custom_field` trong `hooks.py`.

- [ ] **Step 4: Nạp field vào site DEV để test đọc meta** *(ask-first: đây là ghi site — dùng `frappe.reload_doc`/`make_property_setter`? KHÔNG. Thay vào đó test tạo field in-memory qua `frappe.get_doc("Custom Field", …).insert()` trong harness rollback, KHÔNG chạm fixtures site).* Viết `setUp` tạo Custom Field trong savepoint nếu chưa có, để test độc lập site.

- [ ] **Step 5: Chạy → PASS. Commit** (`feat(hr): field ma cham cong tren Leave Application (fixture)`).

---

### Task 3: Hook ghi đè `custom_attendance_code` lên Attendance của đơn (thuần hiển thị)

**Files:**
- Create: `hrms/hr/doctype/leave_application/leave_single_pool.py` (hàm hook)
- Modify: `hrms/hooks.py` (`doc_events["Leave Application"]["on_submit"]`)
- Test: `hrms/hr/doctype/leave_application/test_leave_single_pool.py`

**Interfaces:**
- Produces: `set_leave_attendance_code(doc, method=None)` — sau khi đơn duyệt sinh Attendance, gán mã lý do.

- [ ] **Step 1: Viết test** — đơn `leave_type="Nghỉ phép năm"`, `custom_attendance_code="Ô"`, 1 ngày → Attendance có `custom_attendance_code="Ô"` (không phải "P"), `leave_type` vẫn `"Nghỉ phép năm"`, `status="On Leave"` (payroll-neutral); và report `get_sheet_rows` xếp ngày đó vào nhóm **Ốm**, số dư quỹ "Nghỉ phép năm" giảm 1.

```python
	def test_sick_leave_from_annual_pool_shows_O_but_deducts_pool(self):
		alloc = self._alloc("Nghỉ phép năm", 12)
		la = self._leave_app("Nghỉ phép năm", "2099-03-06", "2099-03-06", code="Ô")
		att = frappe.db.get_value("Attendance", {"leave_application": la.name},
			["status", "leave_type", "custom_attendance_code"], as_dict=True)
		self.assertEqual(att.custom_attendance_code, "Ô")   # hien rieng
		self.assertEqual(att.leave_type, "Nghỉ phép năm")   # rut mot quy
		self.assertEqual(att.status, "On Leave")            # payroll khong doi
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import get_sheet_rows
		row = next(r for r in get_sheet_rows({"month": 3, "year": 2099}) if r["employee"] == self.emp)
		self.assertEqual(row["days"][6], "Ô")
		self.assertGreaterEqual(row["totals"].get("Ốm", 0), 1.0)
```

- [ ] **Step 2: Chạy → FAIL** (Attendance còn "P").

- [ ] **Step 3: Viết hook** `hrms/hr/doctype/leave_application/leave_single_pool.py`:

```python
import frappe

def set_leave_attendance_code(doc, method=None):
	"""Sau khi Đơn xin nghỉ duyệt sinh Attendance, ghi mã lý do (Ô/Cô/P) lên Attendance để bảng
	công hiện đúng — THUẦN HIỂN THỊ (db_set, không đổi status/leave_type/half_day_status)."""
	code = doc.get("custom_attendance_code")
	if not code:
		return
	for name in frappe.get_all(
		"Attendance",
		filters={"leave_application": doc.name, "docstatus": ["<", 2]},
		pluck="name",
	):
		frappe.db.set_value("Attendance", name, "custom_attendance_code", code, update_modified=False)
```

Wire trong `hooks.py`:
```python
	"Leave Application": {
		"on_submit": "hrms.hr.doctype.leave_application.leave_single_pool.set_leave_attendance_code",
	},
```

- [ ] **Step 4: Chạy → PASS. Commit** (`feat(hr): hook gan ma ly do len Attendance cua don nghi`).

---

### Task 4: Validate — đơn rút quỹ phải chọn mã hợp lệ

**Files:**
- Modify: `hrms/hr/doctype/leave_application/leave_single_pool.py` (thêm `validate_pool_code`)
- Modify: `hrms/hooks.py` (`doc_events["Leave Application"]["validate"]`)
- Test: cùng file test.

- [ ] **Step 1: Test** — đơn `leave_type="Nghỉ phép năm"` không chọn `custom_attendance_code` → `ValidationError`; chọn mã ngoài `DEDUCTING_CODES` (vd "TS") → `ValidationError`.

```python
	def test_annual_pool_requires_valid_reason_code(self):
		self._alloc("Nghỉ phép năm", 12)
		with self.assertRaises(frappe.ValidationError):
			self._leave_app("Nghỉ phép năm", "2099-03-07", "2099-03-07")  # thieu code
		with self.assertRaises(frappe.ValidationError):
			self._leave_app("Nghỉ phép năm", "2099-03-08", "2099-03-08", code="TS")  # sai nhom
```

- [ ] **Step 2: FAIL** (chưa validate).

- [ ] **Step 3: Thêm** vào `leave_single_pool.py`:
```python
DEDUCTING_CODES = {"P", "1/2P", "Ô", "Cô"}
POOL_LEAVE_TYPE = "Nghỉ phép năm"

def validate_pool_code(doc, method=None):
	if doc.leave_type != POOL_LEAVE_TYPE:
		return
	code = doc.get("custom_attendance_code")
	if code not in DEDUCTING_CODES:
		frappe.throw(frappe._(
			"Nghỉ rút quỹ phép năm phải chọn Mã chấm công hợp lệ ({0}).").format(", ".join(sorted(DEDUCTING_CODES))))
```
Wire `validate` trong hooks.

- [ ] **Step 4: PASS. Commit** (`feat(hr): validate don rut quy phai chon ma hop le`).

---

### Task 5: Chặn khi hết quỹ (native) + gate lương bất biến

**Files:**
- Test: cùng file.

- [ ] **Step 1: Test chặn** — allocation 1 ngày, nộp đơn 2 ngày phép năm → `ValidationError` (số dư âm, `allow_negative=0`). Và test **lương bất biến**: dựng Salary Slip trước/sau 1 ngày Ô-rút-quỹ → `payment_days`/`absent_days`/LWP y hệt native 1 ngày On Leave (mã P).

```python
	def test_blocks_when_pool_empty(self):
		self._alloc("Nghỉ phép năm", 1)
		with self.assertRaises(frappe.ValidationError):
			self._leave_app("Nghỉ phép năm", "2099-03-10", "2099-03-11", code="P")  # 2 ngay > 1
```

- [ ] **Step 2: Chạy** — chặn có thể đã đạt sẵn (native). Nếu PASS ngay → ghi rõ "native block, no code". Gate lương: tái dùng suite `test_attendance_code_payroll_invariance` (nếu chạy được trên harness) hoặc so `get_working_days_details`.

- [ ] **Step 3: Commit** (`test(hr): chan het quy + gate luong bat bien cho don rut quy`).

---

### Task 6: Cấu hình miễn trừ (TS/N/T) + không lương (K) — không đụng quỹ

**Files:**
- Test: cùng file.
- (Có thể) Modify fixture Leave Type miễn trừ nếu cần allocation-độc-lập — **ask-first**, chỉ nếu test chứng minh cần.

- [ ] **Step 1: Test** — đơn `leave_type="Nghỉ thai sản"` (miễn trừ) submit được **không cần** số dư quỹ phép năm và **không** giảm quỹ phép năm; đơn `leave_type="Nghỉ không lương"` submit được, is_lwp, không giảm quỹ.

```python
	def test_exempt_and_unpaid_do_not_touch_annual_pool(self):
		self._alloc("Nghỉ phép năm", 12)
		before = _pool_balance(self.emp)  # helper doc so du "Nghỉ phép năm"
		# thai san mien tru: can allocation rieng hoac cau hinh cho phep
		self._alloc("Nghỉ thai sản", 180)
		self._leave_app("Nghỉ thai sản", "2099-03-12", "2099-03-12")
		self.assertEqual(_pool_balance(self.emp), before)  # quy phep nam khong doi
```

- [ ] **Step 2: Chạy → nếu FAIL vì loại miễn trừ đòi allocation** → quyết ở đây: cấp allocation chế độ (test tự cấp) HOẶC chỉnh Leave Type (ask-first). Ghi rõ quyết định.

- [ ] **Step 3: Commit** (`test(hr): mien tru + khong luong khong dung quy phep nam`).

---

### Task 7: Docs + tick plan + tổng kết gate deploy

**Files:**
- Modify: `tasks/plan-leave-single-pool.md` (tick), `spec/leave-single-pool-vn.md` (Status → BUILT on branch).

- [ ] Tick checkbox; ghi rõ **các bước deploy còn treo (ask-first):** (a) chạy `assign_annual_leave` + hoà giải 7 allocation tay; (b) migrate fixture (field + Attendance Code Ô/Cô leave_type); (c) restart prod; (d) PWA (bậc 3). Commit docs.

## Self-review (đã rà)

- **Spec coverage:** field (T2), hook hiện-riêng (T3), validate (T4), chặn hết quỹ (T5), miễn trừ/không lương (T6), lương bất biến (T5), bảng công không đổi (T3 kiểm get_sheet_rows). WS3 (bậc 1) = tiền đề, không lặp ở đây.
- **Rủi ro chính:** tương tác bridge×leave-app tinh vi → T1 đặc tả trước; mọi thay đổi thuần hiển thị (db_set) nên payroll-neutral; T5 gate lương.
- **Chưa chắc (giải ở build):** tên field Leave Allocation theo version (T1 sửa khớp); loại miễn trừ có đòi allocation không (T6 quyết); block native có sẵn chưa (T5).
