# Plan — Sinh công miễn chấm công: xem trước rồi mới ghi

> Thực thi tuần tự T1 → T4, mỗi task kết thúc bằng **một commit**. Bước dùng checkbox `- [ ]`.

**Spec:** `docs/spec/attendance-exempt-employees.md` §3.6 (đọc trước khi bắt đầu).
Nhánh: `feat/skip-attendance-diag`. Duyệt thiết kế: 2026-08-21.

**Goal:** nút chạy bù công cho người miễn chấm công **nói ra nó sẽ làm gì** trước khi ghi, và nằm ở
đúng chỗ HR soát công cuối tháng.

**Vấn đề đang sửa:** nút hiện tại chạy đúng nhưng câm. Bằng chứng 2026-08-21: cú bấm lúc 11:12 đã
lật ngày 12/08 của HR-EMP-00005 từ `V` sang `X` (bình luận "Sửa về đủ công (mã cũ V)", và không có
lượt scheduler nào sau 10:00) — nhưng màn hình chỉ hiện "Đã sinh N ngày công", bấm lần hai ra "0
ngày", nên người dùng kết luận nút vô dụng. Không có gì cho biết ngày P/CT/W/K bị **cố ý** chừa ra.

**Architecture:** tách phần *quyết định* (`plan_day`, hàm thuần, không ghi) khỏi phần *thực thi*.
Preview và apply gọi chung `plan_day` nên không thể lệch nhau. UI chuyển về trang Soát công tháng.

**Tech Stack:** Frappe v15 whitelisted methods + desk Page JS; test qua harness rollback.

## Global Constraints

- **KHÔNG** `bench --site miyano run-tests`. Chạy qua harness rollback (`$SCRATCH/run_test.sh`;
  nếu scratchpad bị dọn thì dựng lại theo `docs/tasks/plan-attendance-exempt.md`).
- `preview_month` **không được ghi một dòng nào** — có test đếm bản ghi trước/sau.
- Payroll chỉ đọc `status` / `leave_type` / `half_day_status`; task này không đổi luật ngày công nào,
  chỉ đổi cách trình bày và điểm vào.
- Lint ruff: tab, nháy kép, dòng ≤ 110. Commit theo Conventional Commits, scope `(hr)`.
- Chỉ `git add` đúng file mình đụng.
- Helper trên `Document` không đặt tên bắt đầu bằng `_`.

---

## T1: `plan_day` — tách quyết định khỏi thực thi

**Files:**
- Modify: `hrms/hr/attendance_exempt.py`
- Test: `hrms/hr/tests/test_attendance_exempt.py`

**Interfaces:**
- Produces: `plan_day(employee, date) -> frappe._dict(action, reason, code_cu, attendance)`
  với `action ∈ {"create", "repair", "attach", "skip"}` và `reason ∈ {None, "leave", "trip_wfh",
  "request", "locked", "rest_day", "not_exempt", "ok"}`.
- `ensure_full_day` giữ nguyên chữ ký `-> str | None`, nay cài đặt bằng `plan_day` + thực thi.

- [ ] **Bước 1: Viết test đỏ**

```python
class TestPlanDay(PerTestRollback, FrappeTestCase):
	"""E16 — quyết định (không ghi) tách khỏi thực thi."""

	def setUp(self):
		self.emp = make_exempt_employee(email="plan@miyano.test")

	def mark(self, code, **kwargs):
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": ANCHOR,
				"custom_attendance_code": code,
				**kwargs,
			}
		)
		att.insert()
		att.submit()
		return att

	def plan(self):
		from hrms.hr.attendance_exempt import plan_day

		return plan_day(self.emp, ANCHOR)

	def test_empty_day_plans_create(self):
		p = self.plan()
		self.assertEqual(p.action, "create")

	def test_absent_day_plans_repair_with_old_code(self):
		self.mark("V")
		p = self.plan()
		self.assertEqual(p.action, "repair")
		self.assertEqual(p.code_cu, "V")

	def test_leave_day_plans_skip_leave(self):
		self.mark("P")
		p = self.plan()
		self.assertEqual((p.action, p.reason), ("skip", "leave"))

	def test_trip_day_plans_skip_trip_wfh(self):
		self.mark("CT")
		self.assertEqual(self.plan().reason, "trip_wfh")

	def test_correct_day_plans_skip_ok(self):
		self.mark("X")
		self.assertEqual(self.plan().reason, "ok")

	def test_plain_employee_plans_skip_not_exempt(self):
		from hrms.hr.attendance_exempt import plan_day

		plain = make_plain_employee("plan_plain@miyano.test")
		self.assertEqual(plan_day(plain, ANCHOR).reason, "not_exempt")

	def test_locked_period_plans_skip_locked(self):
		from unittest.mock import patch

		with patch("hrms.hr.period_lock.is_period_locked", return_value=True):
			self.assertEqual(self.plan().reason, "locked")

	def test_plan_day_writes_nothing(self):
		before = frappe.db.count("Attendance", {"employee": self.emp})
		self.plan()
		self.assertEqual(frappe.db.count("Attendance", {"employee": self.emp}), before)
```

- [ ] **Bước 2: Chạy để thấy ĐỎ**

Run: `bash $SCRATCH/run_test.sh "hrms.hr.tests.test_attendance_exempt.TestPlanDay"`
Kỳ vọng: FAIL — `cannot import name 'plan_day'`.

- [ ] **Bước 3: Cài `plan_day` và viết lại `ensure_full_day` dựa trên nó**

```python
def plan_day(employee: str, date) -> frappe._dict:
	"""QUYẾT ĐỊNH sẽ làm gì với một ngày — thuần đọc, không ghi. Nguồn luật duy nhất cho cả
	xem trước lẫn lúc ghi, nên hai bên không thể lệch nhau."""
	from hrms.hr.period_lock import is_period_locked

	date = getdate(date)
	out = frappe._dict(action="skip", reason=None, code_cu=None, attendance=None, date=date, employee=employee)
	if not is_exempt(employee, date):
		out.reason = "not_exempt"
		return out
	if is_holiday(employee, date, raise_exception=False):
		out.reason = "rest_day"
		return out
	if is_period_locked(employee, date):
		out.reason = "locked"
		return out

	row = existing_day(employee, date)
	if row:
		out.attendance = row.name
		out.code_cu = row.custom_attendance_code
		if is_protected_day(row):
			out.reason = "request" if row.get("attendance_request") else (
				"trip_wfh" if row.get("status") == "Work From Home" else "leave"
			)
			return out
		if row.custom_attendance_code == EXEMPT_CODE and row.status == "Present":
			out.action = "attach" if pending_checkins(employee, date, row) else "skip"
			out.reason = None if out.action == "attach" else "ok"
			return out
		out.action = "repair"
		return out

	if approved_request_for(employee, date):
		out.reason = "request"
		return out
	out.action = "create"
	return out
```

Thêm helper đọc lượt chấm chưa gắn (tách ra từ `attach_late_checkins` để `plan_day` không ghi gì):

```python
def pending_checkins(employee: str, date, row) -> list:
	"""Lượt chấm của ngày này chưa gắn vào ngày công nào — chỉ đọc."""
	if row.get("in_time") or row.get("out_time"):
		return []
	return frappe.get_all(
		"Employee Checkin",
		filters={
			"employee": employee,
			"attendance": ("is", "not set"),
			"time": ("between", [f"{getdate(date)} 00:00:00", f"{getdate(date)} 23:59:59"]),
		},
		fields=["name", "time"],
		order_by="time",
	)
```

`ensure_full_day` viết lại thành `plan_day` + thực thi, giữ nguyên hành vi và chữ ký trả về:

```python
def ensure_full_day(employee: str, date) -> str | None:
	plan = plan_day(employee, date)
	if plan.action == "skip":
		return None
	if plan.action == "attach":
		row = existing_day(employee, date)
		return row.name if attach_late_checkins(row, employee, date) else None
	if plan.action == "repair":
		row = existing_day(employee, date)
		attach_late_checkins(row, employee, date)
		return repair_day(row)
	return create_full_day(employee, getdate(date))
```

Phần tạo bản ghi mới trong `ensure_full_day` cũ tách thành `create_full_day(employee, date) -> str`
(nguyên văn, chỉ đổi tên). `approved_request_for` import từ
`hrms.hr.doctype.attendance_request.attendance_request_miyano`; nhánh `create` vẫn gọi
`reapply_attendance_request` trước khi tạo để dựng lại ngày công theo đơn.

Sửa luôn `attach_late_checkins` dùng lại `pending_checkins` — chỉ được có MỘT chỗ truy vấn lượt chấm
chưa gắn, nếu không xem trước và lúc ghi lại đếm theo hai luật khác nhau.

- [ ] **Bước 4: Chạy lại → XANH**

Run: `bash $SCRATCH/run_test.sh "hrms.hr.tests.test_attendance_exempt"` → OK (toàn bộ, kể cả 50 test
cũ — `ensure_full_day` không được đổi hành vi), `HARNESS_NO_LEAK`.

- [ ] **Bước 5: Commit**

```bash
git add hrms/hr/attendance_exempt.py hrms/hr/tests/test_attendance_exempt.py
git commit -m "refactor(hr): tach plan_day khoi ensure_full_day de xem truoc duoc"
```

---

## T2: `preview_month` + `generate_for_month` trả cùng cấu trúc

**Files:**
- Modify: `hrms/hr/attendance_exempt.py`
- Test: `hrms/hr/tests/test_attendance_exempt.py`

**Interfaces:**
- Produces (cả hai whitelisted, quyền HR Manager / System Manager):
  - `preview_month(month, year, employee=None) -> dict`
  - `generate_for_month(month, year, employee=None) -> dict`
  - Cùng shape: `{"rows": [{employee, employee_name, date, action, reason, code_cu}],
    "summary": {"create": int, "repair": int, "attach": int, "skip": int}}`
  - `rows` **chỉ chứa việc phải làm** (`action != "skip"`) cộng những ngày `skip` có lý do đáng nói
    (`leave`, `trip_wfh`, `request`, `locked`) — không nhồi ngày `ok` / `rest_day` / `not_exempt`
    vào bảng, người đọc chỉ cần biết cái gì đổi và cái gì bị chừa **có chủ ý**.

⚠ **Đổi kiểu trả về của `generate_for_month`** từ `int` sang `dict`. Chỉ nút JS gọi nó; sửa cả hai
nơi trong cùng task này (T3). Test cũ `TestGenerateForMonth` phải cập nhật theo — sửa trong task này.

- [ ] **Bước 1: Viết test đỏ**

```python
class TestPreviewMonth(PerTestRollback, FrappeTestCase):
	"""E17 — xem trước không ghi, và hứa gì thì apply làm đúng thế."""

	def setUp(self):
		from frappe.utils import get_first_day

		self.start = get_first_day(add_days(get_first_day(getdate()), -1))
		self.emp = make_exempt_employee(email="preview@miyano.test", from_date=self.start)

	def test_preview_writes_nothing(self):
		from hrms.hr.attendance_exempt import preview_month

		before = frappe.db.count("Attendance")
		res = preview_month(self.start.month, self.start.year, employee=self.emp)
		self.assertEqual(frappe.db.count("Attendance"), before, "xem trước KHÔNG được ghi gì")
		self.assertGreater(res["summary"]["create"], 0)

	def test_apply_matches_preview(self):
		from hrms.hr.attendance_exempt import generate_for_month, preview_month

		planned = preview_month(self.start.month, self.start.year, employee=self.emp)
		done = generate_for_month(self.start.month, self.start.year, employee=self.emp)
		self.assertEqual(done["summary"]["create"], planned["summary"]["create"])
		self.assertEqual(len(done["rows"]), len(planned["rows"]))

	def test_protected_days_are_reported_not_hidden(self):
		from hrms.hr.attendance_exempt import preview_month

		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": self.start,
				"custom_attendance_code": "P",
			}
		)
		att.insert()
		att.submit()
		res = preview_month(self.start.month, self.start.year, employee=self.emp)
		giu = [r for r in res["rows"] if r["reason"] == "leave"]
		self.assertTrue(giu, "ngày nghỉ phép bị chừa ra phải được BÁO, không im lặng")

	def test_second_run_has_nothing_to_do(self):
		from hrms.hr.attendance_exempt import generate_for_month, preview_month

		generate_for_month(self.start.month, self.start.year, employee=self.emp)
		res = preview_month(self.start.month, self.start.year, employee=self.emp)
		self.assertEqual(res["summary"]["create"], 0)
		self.assertEqual(res["summary"]["repair"], 0)
```

- [ ] **Bước 2: Chạy để thấy ĐỎ** — `cannot import name 'preview_month'`.

- [ ] **Bước 3: Cài đặt**

```python
REPORTED_SKIPS = ("leave", "trip_wfh", "request", "locked")


def plan_month(month, year, employee: str | None = None) -> list:
	"""Kế hoạch cho cả tháng — thuần đọc. Không sinh ngày hôm nay và tương lai."""
	start = getdate(f"{cint(year)}-{cint(month):02d}-01")
	end = min(get_last_day(start), add_days(getdate(), -1))
	rows = [frappe._dict(name=employee)] if employee else exempt_employees()
	plans = []
	for emp in rows:
		day = start
		while day <= end:
			plans.append(plan_day(emp.name, day))
			day = add_days(day, 1)
	return plans


def as_result(plans: list) -> dict:
	summary = {"create": 0, "repair": 0, "attach": 0, "skip": 0}
	rows = []
	for p in plans:
		summary[p.action] += 1
		if p.action != "skip" or p.reason in REPORTED_SKIPS:
			rows.append(
				{
					"employee": p.employee,
					"employee_name": frappe.db.get_value("Employee", p.employee, "employee_name"),
					"date": str(p.date),
					"action": p.action,
					"reason": p.reason,
					"code_cu": p.code_cu,
				}
			)
	return {"rows": rows, "summary": summary}


@frappe.whitelist()
def preview_month(month, year, employee: str | None = None) -> dict:
	"""Xem trước — KHÔNG ghi gì."""
	frappe.only_for(("HR Manager", "System Manager"))
	return as_result(plan_month(month, year, employee))


@frappe.whitelist()
def generate_for_month(month, year, employee: str | None = None) -> dict:
	"""Chạy bù cả tháng. Trả cùng cấu trúc với `preview_month` để đối chiếu."""
	frappe.only_for(("HR Manager", "System Manager"))
	plans = plan_month(month, year, employee)
	for p in plans:
		if p.action != "skip":
			ensure_full_day(p.employee, p.date)
	return as_result(plans)
```

- [ ] **Bước 4: Cập nhật `TestGenerateForMonth` cũ** — ba test đang so `int`, đổi sang đọc
  `["summary"]["create"]` / `len(res["rows"])`. Giữ nguyên ý nghĩa từng test.

- [ ] **Bước 5: Chạy lại → XANH**

Run: `bash $SCRATCH/run_test.sh "hrms.hr.tests.test_attendance_exempt"` → OK, `HARNESS_NO_LEAK`.

- [ ] **Bước 6: Commit**

```bash
git add hrms/hr/attendance_exempt.py hrms/hr/tests/test_attendance_exempt.py
git commit -m "feat(hr): xem truoc ke hoach sinh cong mien cham cong truoc khi ghi"
```

---

## T3: Nút trên màn Soát công tháng, gỡ nút cũ

**Files:**
- Modify: `hrms/hr/page/attendance_review/attendance_review.js` (`make_actions` + hàm mới)
- Modify: `hrms/hr/doctype/attendance/attendance_list.js` (gỡ nút cũ)

- [ ] **Bước 1: Thêm nút vào `make_actions`** (sau "Chốt công tháng"):

```javascript
		this.page.add_inner_button(__("Sinh công miễn chấm công"), () => this.preview_exempt());
```

- [ ] **Bước 2: Thêm hai hàm vào class `AttendanceReview`**

```javascript
	preview_exempt() {
		frappe.call({
			method: "hrms.hr.attendance_exempt.preview_month",
			args: this.filters(),
			freeze: true,
			freeze_message: __("Đang kiểm tra ngày công..."),
			callback: (r) => this.show_exempt_plan(r.message),
		});
	}

	show_exempt_plan(plan) {
		if (!plan) return;
		const s = plan.summary || {};
		const viec = (s.create || 0) + (s.repair || 0) + (s.attach || 0);
		if (!viec && !(plan.rows || []).length) {
			frappe.msgprint({
				title: __("Không có gì để sửa"),
				message: __("Mọi ngày công của nhân viên miễn chấm công trong tháng này đã đúng."),
				indicator: "green",
			});
			return;
		}

		const NHAN = {
			create: __("Tạo mới (X)"),
			repair: __("Sửa về đủ công"),
			attach: __("Ghi giờ vào/ra"),
			leave: __("Giữ nguyên — nghỉ phép"),
			trip_wfh: __("Giữ nguyên — công tác / làm ở nhà"),
			request: __("Giữ nguyên — có đơn chấm công"),
			locked: __("Bỏ qua — kỳ đã chốt"),
		};
		const hang = (plan.rows || [])
			.map(
				(r) => `<tr>
					<td>${frappe.utils.escape_html(r.employee_name || r.employee)}</td>
					<td>${frappe.datetime.str_to_user(r.date)}</td>
					<td>${NHAN[r.action] || NHAN[r.reason] || r.action}</td>
					<td>${r.code_cu ? frappe.utils.escape_html(r.code_cu) : ""}</td>
				</tr>`,
			)
			.join("");

		const d = new frappe.ui.Dialog({
			title: __("Sinh công cho nhân viên miễn chấm công"),
			size: "large",
			fields: [
				{
					fieldtype: "HTML",
					options: `<p>${__("Sẽ tạo {0} ngày, sửa {1} ngày, ghi giờ {2} ngày.", [
						s.create || 0,
						s.repair || 0,
						s.attach || 0,
					])}</p>
					<div style="max-height:50vh;overflow:auto">
					<table class="table table-bordered">
						<thead><tr>
							<th>${__("Nhân viên")}</th><th>${__("Ngày")}</th>
							<th>${__("Việc sẽ làm")}</th><th>${__("Mã cũ")}</th>
						</tr></thead>
						<tbody>${hang}</tbody>
					</table></div>`,
				},
			],
			primary_action_label: __("Ghi {0} thay đổi", [viec]),
			primary_action: () => {
				d.hide();
				frappe.call({
					method: "hrms.hr.attendance_exempt.generate_for_month",
					args: this.filters(),
					freeze: true,
					freeze_message: __("Đang ghi ngày công..."),
					callback: (r) => {
						const done = (r.message && r.message.summary) || {};
						frappe.show_alert({
							message: __("Đã tạo {0}, sửa {1}, ghi giờ {2} ngày.", [
								done.create || 0,
								done.repair || 0,
								done.attach || 0,
							]),
							indicator: "green",
						});
						this.refresh();
					},
				});
			},
		});
		if (!viec) d.get_primary_btn().hide();
		d.show();
	}
```

- [ ] **Bước 3: Gỡ nút cũ khỏi `attendance_list.js`** — xoá trọn khối
  `add_inner_button(__("Sinh công tháng (miễn chấm công)") …)` cùng comment của nó.

- [ ] **Bước 4: Kiểm tay trên desk**

```bash
cd /home/miyano/frappe-bench && bench --site miyano clear-cache
```

Mở `http://miyano/app/attendance-review`, chọn tháng 8/2026 → bấm **Sinh công miễn chấm công**:
bảng phải liệt kê ngày sẽ tạo/sửa và các ngày P/CT/W/K bị chừa. Bấm Ghi → thông báo số thật, lưới
tải lại. Bấm lần hai → "Không có gì để sửa". Danh sách Ngày công không còn nút cũ.

- [ ] **Bước 5: Commit**

```bash
git add hrms/hr/page/attendance_review/attendance_review.js hrms/hr/doctype/attendance/attendance_list.js
git commit -m "feat(hr): nut sinh cong mien cham cong ve man soat cong, co xem truoc"
```

---

## T4: Chốt tài liệu + chạy trọn bộ

**Files:**
- Modify: `docs/tasks/plan-attendance-exempt-preview.md` (ghi STATUS)
- Modify: `CLAUDE.md` nếu câu mô tả tính năng còn nhắc nút cũ

- [ ] **Bước 1: Chạy trọn bộ, đối chiếu baseline**

```bash
for m in hrms.hr.tests.test_attendance_exempt \
         hrms.hr.tests.test_attendance_review \
         hrms.payroll.doctype.salary_slip.test_exempt_payroll \
         hrms.tests.test_timekeeping_e2e; do
  echo "== $m"; bash $SCRATCH/run_test.sh "$m" | grep -E "^(Ran|RESULT|HARNESS_LEAK)"
done
```

Mọi module phải `RESULT: OK` và `HARNESS_NO_LEAK`.

- [ ] **Bước 2: Ghi STATUS đầu plan** — số task xong, số test xanh, còn treo gì.

- [ ] **Bước 3: Commit**

```bash
git add docs/tasks/plan-attendance-exempt-preview.md CLAUDE.md
git commit -m "docs(hr): chot ket qua nut sinh cong co xem truoc"
```

---

## Ngoài phạm vi (đã bàn, cố ý không gói vào)

- **16 ngày V tháng 6 của Giám đốc.** Nút này bù được sau khi lùi `custom_exempt_from_checkin_from`
  về ngày vào làm, nhưng lùi ngày hiệu lực là quyết định của chủ site — tách bạch, hỏi riêng.
- Chọn khoảng ngày tuỳ ý (đã chốt: đúng một tháng như hiện nay).
- Đổi cửa sổ 31 ngày của lượt quét tự động.
