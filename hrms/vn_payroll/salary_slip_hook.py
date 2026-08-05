# Copyright (c) 2026, Miyano Việt Nam.
"""Cầu nối engine MVL vào Salary Slip.

Chạy ở `doc_events["Salary Slip"]["validate"]` — SAU khi controller đã tính payment_days /
total_working_days và dựng các component từ Salary Structure. Ta đọc cấu hình NV (Salary Structure
Assignment) + số công, chạy engine, rồi ghi đè amount từng component và tổng gross/net. Chỉ tác động
lên slip dùng MỘT trong các cấu trúc MVL (mỗi loại lương một cấu trúc — xem setup_mvl.STRUCTURES);
LOẠI lương suy TỪ cấu trúc của slip. Slip khác đi đường Frappe gốc.
"""

import frappe
from frappe.utils import add_days, cint, flt, getdate, rounded

from hrms.vn_payroll.lunch import lunch_days_for_period
from hrms.vn_payroll.mvl import MVLInput, compute_mvl
from hrms.vn_payroll.settings import config_from_settings
from hrms.vn_payroll.setup_mvl import BONUS_COMPONENT, REAL_EARNINGS, salary_type_of

# Khoản THẬT cộng vào net (NET). GROSS thêm thuế + BHXH NLĐ vào deduction.
GROSS_DEDUCTIONS = ("Thuế TNCN (nộp thay)", "BHXH - NLĐ (nộp thay)")


def component_values(inp, cfg, r) -> dict:
	"""Số tiền cho MỖI component MVL (mọi cột tiền của bảng lương)."""
	return {
		"Lương ngày công": inp.base,  # F
		"Lương đóng BHXH": inp.bhxh_salary,  # G
		"Lương theo công": r.I,
		"Phụ cấp ăn trưa": r.J,
		# gương chi phí (hạch toán): thuế + BHXH (NLĐ+DN) công ty nộp thay → Nợ 6421; KHÔNG cộng net
		"Chi phí thuế & BHXH DN nộp thay": r.Q + r.S + r.R,
		"Tổng thu nhập": r.K,
		"Thu nhập quy đổi": r.O,
		"Thu nhập tính thuế": r.P,
		"Thu nhập chịu thuế kê khai": r.U,
		"Giảm trừ bản thân": cfg.personal_deduction if inp.register_personal_deduction else 0.0,  # L
		"Tổng giảm trừ gia cảnh": r.N,
		"Thuế TNCN (nộp thay)": r.Q,
		"BHXH - NLĐ (nộp thay)": r.S,
		"BHXH - Công ty": r.R,
	}


def get_mvl_assignment(doc) -> frappe._dict | None:
	"""Salary Structure Assignment hiệu lực của NV cho kỳ này (đúng cấu trúc của slip, mới nhất, đã submit)."""
	period_end = doc.end_date or doc.start_date
	fields = [
		"base",
		"custom_bhxh_salary",
		"custom_dependents",
		"custom_register_personal_deduction",
		"custom_lunch_days_override",
	]
	# custom_is_resident có thể chưa migrate → chỉ query khi field đã tồn tại (tránh lỗi cột không có)
	if frappe.get_meta("Salary Structure Assignment").has_field("custom_is_resident"):
		fields.append("custom_is_resident")
	rows = frappe.get_all(
		"Salary Structure Assignment",
		filters={
			"employee": doc.employee,
			"salary_structure": doc.salary_structure,
			"docstatus": 1,
			"from_date": ["<=", period_end],
		},
		fields=fields,
		order_by="from_date desc",
		limit=1,
	)
	return rows[0] if rows else None


def unpaid_leave_types() -> set:
	"""Loại nghỉ mà DOANH NGHIỆP không trả lương — payroll trừ trọn ngày cho những loại này.

	Hai nhóm, không chỉ `is_lwp`:

	- `is_lwp = 1` — nghỉ không lương thông thường.
	- `is_ppl = 1` với phần công ty trả = 0 — nghỉ do **BHXH chi trả** (ốm, chăm con ốm, thai sản).
	  Phải dùng `is_ppl` chứ không phải `is_lwp` vì `LeaveType.validate_lwp` chặn đặt `is_lwp` cho
	  loại nghỉ đã có cấp phép, mà ba loại này đều có (quyết định 2026-07-30).

	Bỏ sót nhóm thứ hai thì engine MVL và cổng đối soát sẽ tính ngày BHXH là có lương trong khi
	controller payroll đã trừ — hai bên lệch nhau mà không ai báo.
	"""
	rows = frappe.get_all(
		"Leave Type",
		or_filters={"is_lwp": 1, "is_ppl": 1},
		fields=["name", "is_lwp", "is_ppl", "fraction_of_daily_salary_per_leave"],
	)
	return {
		r.name
		for r in rows
		if cint(r.is_lwp) or (cint(r.is_ppl) and not flt(r.fraction_of_daily_salary_per_leave))
	}


def _day_paid_fraction(status, half_day_status, leave_type, lwp: set) -> float:
	"""Số công CÓ LƯƠNG của một ngày Attendance (khớp cách payroll tính payment_days theo ngày):
	đi làm/nghỉ có lương = 1; vắng/nghỉ công ty không trả = 0; nửa ngày = 0.5 (nửa làm) + 0.5 nếu
	nửa kia Present và KHÔNG thuộc nhóm công ty không trả.

	`lwp` phải là kết quả của `unpaid_leave_types()` — gồm cả nghỉ BHXH, không chỉ `is_lwp`."""
	if status in ("Present", "Work From Home"):
		return 1.0
	if status == "On Leave":
		return 0.0 if leave_type in lwp else 1.0
	if status == "Half Day":
		other = 0.5 if (half_day_status == "Present" and leave_type not in lwp) else 0.0
		return 0.5 + other
	return 0.0  # Absent / trạng thái khác → không công


def paid_work_days_between(employee: str, start, end) -> float:
	"""Σ công CÓ LƯƠNG của Attendance đã submit trong [start, end] — để tách công theo giai đoạn khi
	chuyển thử việc → chính thức. Giả định các ngày công đã có Attendance (miyano chấm đủ qua scheduler)."""
	rows = frappe.get_all(
		"Attendance",
		filters={"employee": employee, "attendance_date": ["between", [start, end]], "docstatus": 1},
		fields=["status", "half_day_status", "leave_type"],
	)
	if not rows:
		return 0.0
	lwp = unpaid_leave_types()
	return sum(_day_paid_fraction(r.status, r.half_day_status, r.leave_type, lwp) for r in rows)


def probation_worked_days(doc, salary_type: str) -> float:
	"""Công thuộc giai đoạn THỬ VIỆC (hệ số 0.85) khi NV chuyển thử việc → chính thức GIỮA kỳ này.

	Ngày chuyển = ``Employee.final_confirmation_date`` (Ngày chính thức); mọi ngày TRƯỚC đó là thử việc.
	Chỉ áp cho slip loại Chính thức. NV giữ MỘT cấu trúc "Lương chính thức" từ đầu kỳ (thoả ràng buộc
	ERPNext: slip cần SSA hiệu lực ≤ đầu kỳ) — phần thử việc chỉ là hệ số, suy từ ngày chính thức."""
	if salary_type != "Chính thức":
		return 0.0
	conf = frappe.db.get_value("Employee", doc.employee, "final_confirmation_date")
	if not conf:
		return 0.0
	conf = getdate(conf)
	start, end = getdate(doc.start_date), getdate(doc.end_date)
	if conf <= start:
		return 0.0  # đã chính thức từ trước/đầu kỳ → cả kỳ hệ số 1.0
	prob_end = min(add_days(conf, -1), end)  # ngày thử việc CUỐI trong kỳ (trước ngày chính thức)
	return paid_work_days_between(doc.employee, start, prob_end)


def paid_holidays_in_period(doc) -> float:
	"""Số NGÀY NGHỈ LỄ (không phải nghỉ hàng tuần) trong kỳ, theo Holiday List của nhân viên.

	Chỉ đếm ngày lễ nằm trong thời gian nhân viên còn thuộc biên chế — vào làm giữa kỳ hay nghỉ
	việc giữa kỳ thì ngày lễ ngoài khoảng đó không phải công của họ."""
	from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee

	holiday_list = get_holiday_list_for_employee(doc.employee, raise_exception=False)
	if not holiday_list:
		return 0.0

	start, end = getdate(doc.start_date), getdate(doc.end_date)
	joining, relieving = frappe.db.get_value("Employee", doc.employee, ["date_of_joining", "relieving_date"])
	if joining:
		start = max(start, getdate(joining))
	if relieving:
		end = min(end, getdate(relieving))
	if start > end:
		return 0.0

	return flt(
		frappe.db.count(
			"Holiday",
			{
				"parent": holiday_list,
				"parenttype": "Holiday List",
				"holiday_date": ["between", [start, end]],
				"weekly_off": 0,
			},
		)
	)


def add_paid_holidays(doc, method=None) -> None:
	"""Cộng ngày nghỉ lễ vào CẢ `total_working_days` lẫn `payment_days` của phiếu.

	**Hook RIÊNG, xếp TRƯỚC `sheet_gate.gate` trong `hooks.py` — thứ tự là bắt buộc.** Cổng đối
	soát so `payment_days` của phiếu với "Tổng công" của bảng đã chốt, mà bảng đã đếm ngày lễ; để
	việc cộng này nằm trong `apply_mvl` (chạy SAU cổng) thì cổng so số chưa cộng với số đã cộng và
	chặn sạch mọi phiếu của tháng có lễ ("Lệch -1.0 ngày" — đã dính 2026-08-04).

	Gọi ĐÚNG MỘT LẦN mỗi lượt validate: controller tính lại `total_working_days`/`payment_days` từ
	đầu ở mỗi lần lưu, nên cộng lại mỗi lượt là đúng, nhưng gọi hai lần trong CÙNG một lượt sẽ cộng
	đôi. Vì thế `apply_mvl` không được gọi lại hàm này.

	Quyết định 2026-08-04 (HR chốt): ngày công chuẩn = ngày đi làm + nghỉ lễ + nghỉ có lương.
	ERPNext loại mọi ngày trong Holiday List khỏi `total_working_days`, mà nghỉ hàng tuần cũng nằm
	trong danh sách đó — cờ `include_holidays_in_total_working_days` sẵn có bật lên thì đếm cả thứ
	Bảy/Chủ nhật (22 → 31 ngày), KHÔNG phải thứ ta cần. Vì vậy cộng bù ở đây: chỉ ngày lễ, không
	đụng ngày nghỉ tuần.

	Cộng vào cả hai vế nên người đi làm đủ vẫn nhận đủ lương; khác biệt chỉ xuất hiện khi có ngày
	vắng — lúc đó mẫu số lớn hơn đúng bằng số ngày lễ, khớp cách HR tính tay.

	Ghi thẳng lên `doc` để `payment_days` trên phiếu và cột "Tổng công" của bảng chấm công là CÙNG
	một con số — cổng đối soát `sheet_gate.reconcile_with_sheet` so hai vế này với nhau."""
	# Chỉ phiếu dùng cấu trúc MVL — giữ đúng phạm vi cũ hồi hàm này còn nằm trong `apply_mvl`.
	# Là hook riêng thì nó chạy cho MỌI Salary Slip, kể cả phiếu đi đường Frappe gốc.
	if not salary_type_of(doc.salary_structure):
		return

	holidays = paid_holidays_in_period(doc)
	if not holidays:
		return
	doc.total_working_days = flt(doc.total_working_days) + holidays
	doc.payment_days = flt(doc.payment_days) + holidays


def apply_mvl(doc, method=None):
	# LOẠI lương suy TỪ cấu trúc của slip (mỗi loại một cấu trúc); cấu trúc không thuộc MVL → bỏ qua.
	salary_type = salary_type_of(doc.salary_structure)
	if not salary_type:
		return
	ssa = get_mvl_assignment(doc)
	if not ssa:
		return

	standard_days = flt(doc.total_working_days)
	if not standard_days:
		return  # tránh chia 0 khi kỳ toàn ngày nghỉ

	lunch_days = flt(ssa.custom_lunch_days_override) or lunch_days_for_period(
		doc.employee, doc.start_date, doc.end_date
	)
	inp = MVLInput(
		salary_type=salary_type,
		base=flt(ssa.base),
		bhxh_salary=flt(ssa.custom_bhxh_salary),
		dependents=int(ssa.custom_dependents or 0),
		register_personal_deduction=bool(ssa.custom_register_personal_deduction),
		lunch_days=lunch_days,
		standard_days=standard_days,
		worked_days=flt(doc.payment_days),
		bonus=_bonus_amount(doc),  # HR tự điền, engine đọc chứ không ghi đè
		# chuyển thử việc → chính thức giữa kỳ: công giai đoạn thử việc tính hệ số 0.85
		probation_worked_days=probation_worked_days(doc, salary_type),
		# Bán thời gian: cư trú (10%) hay không cư trú/nước ngoài (20%) — mặc định cư trú nếu chưa migrate field
		is_resident=bool(ssa.get("custom_is_resident", 1))
		if ssa.get("custom_is_resident") is not None
		else True,
	)
	cfg = config_from_settings()
	r = compute_mvl(inp, cfg)
	_set_component_amounts(doc, inp, component_values(inp, cfg, r))
	_set_totals(doc)
	_set_breakdown_fields(doc, inp, cfg, lunch_days)


def _bonus_amount(doc) -> float:
	"""Tiền thưởng HR tự điền trên phiếu — engine đọc để tính thuế, KHÔNG bị ghi đè."""
	return next((flt(row.amount) for row in doc.earnings if row.salary_component == BONUS_COMPONENT), 0.0)


def _set_component_amounts(doc, inp, values):
	"""Gán amount cho MỖI component MVL + ép cờ do_not_include_in_total.

	NET: chỉ Lương theo công + Phụ cấp ăn cộng vào net; mọi component khác do_not_include (hiện trên
	lưới nhưng không làm sai tổng — thuế/BHXH do công ty nộp thay). GROSS thêm thuế + BHXH NLĐ vào trừ.
	"""
	is_gross = inp.salary_type == "GROSS"
	for row in list(doc.earnings) + list(doc.deductions):
		if row.salary_component not in values:
			continue
		row.amount = values[row.salary_component]
		row.default_amount = values[row.salary_component]
		real = row.salary_component in REAL_EARNINGS or (
			is_gross and row.salary_component in GROSS_DEDUCTIONS
		)
		row.do_not_include_in_total = 0 if real else 1


def _set_totals(doc):
	"""Tính lại gross/net theo amount vừa gán — cả earnings lẫn deductions đều bỏ qua do_not_include."""
	gross = sum(flt(row.amount) for row in doc.earnings if not row.do_not_include_in_total)
	deduction = sum(flt(row.amount) for row in doc.deductions if not row.do_not_include_in_total)
	rate = flt(doc.exchange_rate) or 1.0
	doc.gross_pay = gross
	doc.total_deduction = deduction
	doc.net_pay = gross - deduction
	doc.rounded_total = rounded(doc.net_pay)
	doc.base_gross_pay = gross * rate
	doc.base_total_deduction = deduction * rate
	doc.base_net_pay = doc.net_pay * rate
	doc.base_rounded_total = rounded(doc.base_net_pay)


def _set_breakdown_fields(doc, inp, cfg, lunch_days):
	"""Tham số KHÔNG phải tiền (không làm component được); mọi cột tiền đã là Salary Component."""
	doc.custom_salary_type = inp.salary_type
	doc.custom_coefficient = _effective_coefficient(inp, cfg)  # E — hệ số BLEND nếu chuyển giữa kỳ
	doc.custom_dependents_slip = inp.dependents  # M
	doc.custom_lunch_days = int(lunch_days)  # số ngày ăn trưa (dữ liệu ăn trưa trên phiếu)


def _effective_coefficient(inp, cfg) -> float:
	"""Hệ số E hiển thị trên phiếu. Chuyển thử việc → chính thức giữa kỳ → trung bình có trọng số theo
	công (0.85 phần thử việc, 1.0 phần chính thức); không chuyển → hệ số đơn của loại."""
	base_e = cfg.probation_coef if inp.salary_type == "Thử việc" else 1.0
	prob = min(max(inp.probation_worked_days, 0.0), inp.worked_days)
	if prob and inp.worked_days:
		return round((cfg.probation_coef * prob + base_e * (inp.worked_days - prob)) / inp.worked_days, 4)
	return base_e
