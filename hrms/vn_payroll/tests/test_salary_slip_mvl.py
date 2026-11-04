# Copyright (c) 2026, Miyano Việt Nam.
"""Tích hợp: Salary Slip dùng structure MVL → engine gán component + net_pay đúng.

Tự dựng NV + SSA + chấm công đủ tháng, chạy qua harness rollback. Mẫu số lương lấy theo LỊCH TUẦN
(`salary_slip_hook.set_working_days`): tháng 6/2099 có 22 ngày thứ Hai-Sáu, không lễ → total_working_days
= 22; chấm đủ 22 ngày đó → payment_days = 22 → I = base (đi làm đủ công).
"""

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings

from erpnext.setup.doctype.employee.test_employee import make_employee

from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import default_company
from hrms.vn_payroll.setup_mvl import ensure_mvl_defaults, structure_for_type


def ensure_fiscal_year_2099():
	# Salary Slip.compute_year_to_date cần Fiscal Year phủ kỳ; 2099 chưa có trên site.
	if not frappe.db.exists("Fiscal Year", "2099"):
		frappe.get_doc(
			{
				"doctype": "Fiscal Year",
				"year": "2099",
				"year_start_date": "2099-01-01",
				"year_end_date": "2099-12-31",
			}
		).insert(ignore_permissions=True)


def make_ssa(employee, **kw):
	# mỗi loại lương một cấu trúc → cấu trúc suy từ custom_salary_type (mặc định Chính thức)
	doc = frappe.get_doc(
		{
			"doctype": "Salary Structure Assignment",
			"employee": employee,
			"company": default_company(),
			"salary_structure": structure_for_type(kw.get("custom_salary_type", "Chính thức")),
			"from_date": "2099-06-01",
			**kw,
		}
	)
	doc.submit()
	return doc


def working_days_june_2099(employee) -> list[str]:
	"""Ngày đi làm theo lịch tuần của nhân viên — đúng tập ngày mà mẫu số lương đếm."""
	from hrms.hr.work_schedule import scheduled_days_between

	return [str(d) for d in sorted(scheduled_days_between(employee, "2099-06-01", "2099-06-30"))]


def mark_full_month(employee):
	# Chỉ ngày làm việc: chấm cả T7/CN thì ngày ăn trưa và công thử việc đếm cả ngày nghỉ tuần, trong
	# khi mẫu số lương (lịch tuần) thì không — số liệu không bao giờ xảy ra khi chấm công thật.
	for day in working_days_june_2099(employee):
		# checkin phủ cả buổi → ngày ăn trưa (số ngày ăn suy từ checkin, không phải số công).
		# Phải tạo TRƯỚC Attendance: cờ custom_lunch được chốt trong validate của Attendance từ
		# checkin của chính ngày đó (attendance.py: set_lunch_flag), tạo checkin sau thì cờ đã
		# bằng 0 và phụ cấp ăn trưa trên phiếu lương ra 0. Ngoài đời checkin cũng có trước.
		for hm in ("08:00:00", "17:30:00"):
			frappe.get_doc(
				{"doctype": "Employee Checkin", "employee": employee, "time": f"{day} {hm}"}
			).insert()
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": employee,
				"attendance_date": day,
				"custom_attendance_code": "X",
			}
		)
		att.insert()
		att.submit()


def make_slip(employee, salary_type="Chính thức"):
	ss = frappe.new_doc("Salary Slip")
	ss.employee = employee
	ss.salary_structure = structure_for_type(salary_type)
	ss.start_date = "2099-06-01"
	ss.end_date = "2099-06-30"
	ss.insert()  # validate → apply_mvl
	return ss


def make_additional_salary(employee, component, amount, overwrite=0, **kw):
	"""Khoản HR nhập theo kỳ (Lễ/Tết, KPI, điện thoại, xăng xe) — đường native Payroll Entry tự nhận."""
	doc = frappe.get_doc(
		{
			"doctype": "Additional Salary",
			"employee": employee,
			"company": default_company(),
			"salary_component": component,
			"amount": amount,
			"payroll_date": "2099-06-15",
			"overwrite_salary_structure_amount": overwrite,
			**kw,
		}
	)
	doc.submit()
	return doc


def slip_amounts(ss) -> dict:
	"""{component: tổng amount} — cộng dồn vì một component có thể có nhiều row (Additional Salary)."""
	out = {}
	for r in list(ss.earnings) + list(ss.deductions):
		out[r.salary_component] = out.get(r.salary_component, 0) + r.amount
	return out


class TestSalarySlipMVL(PerTestRollback, FrappeTestCase):
	def setUp(self):
		super().setUp()
		# Bộ test này kiểm CÔNG THỨC lương, không kiểm tuyến chấm công. Cổng "phải chốt công trước
		# khi tính lương" (`vn_payroll.sheet_gate`) sẽ chặn mọi phiếu ở đây vì các kỳ 2099 dựng riêng
		# cho test không có Bảng Công Tháng nào. Tắt cổng đúng trong phạm vi test, bằng cửa thoát
		# `skip_sheet_gate` — dựng sẵn cho chính tình huống này; cổng vẫn được kiểm ở test_sheet_gate.
		frappe.flags.skip_sheet_gate = True
		self.addCleanup(lambda: frappe.flags.pop("skip_sheet_gate", None))

	@change_settings("Payroll Settings", {"payroll_based_on": "Attendance"})
	def test_chinh_thuc_full_month(self):
		ensure_fiscal_year_2099()
		ensure_mvl_defaults()
		emp = make_employee("mvl_ft@codes.com", company=default_company())
		make_ssa(
			emp,
			base=25_000_000,
			custom_salary_type="Chính thức",
			custom_bhxh_salary=25_000_000,
			custom_dependents=1,
			custom_register_personal_deduction=1,
		)
		mark_full_month(emp)
		ss = make_slip(emp)

		comp = {r.salary_component: r.amount for r in list(ss.earnings) + list(ss.deductions)}
		self.assertEqual(comp["Lương theo công"], 25_000_000)  # đi làm đủ 22/22 → I = base
		self.assertEqual(comp["Phụ cấp ăn trưa"], ss.payment_days * 35_000)
		# O = K - 21.7tr - J = 25tr - 21.7tr = 3.3tr (J triệt tiêu) → Q = 173.684 bất kể J
		self.assertEqual(comp["Thuế TNCN (nộp thay)"], 173_684)
		self.assertEqual(comp["BHXH - NLĐ (nộp thay)"], 2_625_000)  # 25tr x 10.5%
		self.assertEqual(comp["BHXH - Công ty"], 5_375_000)  # R = 25tr x 21.5%
		self.assertEqual(comp["KPCĐ - Công ty"], 500_000)  # X = 25tr x 2%
		# gương chi phí (hạch toán) = Q + S + R + X → Nợ 6421 của bút toán accrual; KHÔNG cộng net
		self.assertEqual(comp["Chi phí thuế & BHXH DN nộp thay"], 173_684 + 2_625_000 + 5_375_000 + 500_000)
		# NET: thuế + BHXH + gương KHÔNG trừ/cộng vào net → net = K = I + J
		self.assertEqual(ss.net_pay, 25_000_000 + ss.payment_days * 35_000)
		# mọi cột tiền là Salary Component trong lưới (không phải field): F, G, K, N, O, R, U…
		self.assertEqual(comp["Lương ngày công"], 25_000_000)  # F
		self.assertEqual(comp["Lương đóng BHXH"], 25_000_000)  # G
		self.assertEqual(comp["Tổng thu nhập"], ss.net_pay)  # K = T (NET)
		self.assertEqual(comp["Tổng giảm trừ gia cảnh"], 21_700_000)  # N
		self.assertEqual(comp["Thu nhập quy đổi"], 3_300_000)  # O
		self.assertEqual(comp["Thu nhập chịu thuế kê khai"], 25_000_000 + 173_684 + 2_625_000)  # U = 25tr+Q+S
		# các cột do_not_include KHÔNG làm sai net
		self.assertEqual(ss.gross_pay, ss.net_pay)

	@change_settings("Payroll Settings", {"payroll_based_on": "Attendance"})
	def test_net_tracks_payment_days(self):
		# nghỉ không lương vài ngày → I giảm theo payment_days, net theo I
		ensure_fiscal_year_2099()
		ensure_mvl_defaults()
		emp = make_employee("mvl_lwp@codes.com", company=default_company())
		make_ssa(emp, base=22_000_000, custom_salary_type="Chính thức")
		for i, day in enumerate(working_days_june_2099(emp)):
			code = "K" if i < 3 else "X"  # 3 ngày nghỉ không lương
			att = frappe.get_doc(
				{
					"doctype": "Attendance",
					"employee": emp,
					"attendance_date": day,
					"custom_attendance_code": code,
				}
			)
			att.insert()
			att.submit()
		ss = make_slip(emp)

		comp = {r.salary_component: r.amount for r in ss.earnings}
		# I = ROUND(22tr / 22 x 19) = 19.000.000
		self.assertEqual(ss.payment_days, 19)
		self.assertEqual(comp["Lương theo công"], 19_000_000)

	@change_settings("Payroll Settings", {"payroll_based_on": "Attendance"})
	def test_probation_to_official_mid_month_blends_salary(self):
		# NV hết thử việc ngày 16 (Ngày chính thức = 2099-06-16) → hệ số blend theo công mỗi giai đoạn.
		# NV giữ MỘT cấu trúc chính thức từ đầu kỳ (thoả ERPNext); phần thử việc suy từ ngày chính thức.
		ensure_fiscal_year_2099()
		ensure_mvl_defaults()
		emp = make_employee("mvl_prob@codes.com", company=default_company())
		frappe.db.set_value("Employee", emp, "final_confirmation_date", "2099-06-16")
		make_ssa(emp, base=18_000_000, custom_salary_type="Chính thức")  # from 2099-06-01
		mark_full_month(emp)  # chấm đủ 22 ngày làm việc (11 trước ngày chính thức, 11 từ ngày đó)
		ss = make_slip(emp, salary_type="Chính thức")
		comp = {r.salary_component: r.amount for r in ss.earnings}
		# I blend = 18tr/22 x (0.85x11 công thử việc + 1.0x11 công chính thức) = 16.650.000
		# KHÔNG phải 18tr (toàn chính thức) và KHÔNG phải 15.3tr (toàn thử việc)
		self.assertEqual(comp["Lương theo công"], 16_650_000)
		# hệ số E hiện trên phiếu là blend có trọng số: (0.85x11 + 1.0x11)/22 = 0.925
		self.assertEqual(ss.custom_coefficient, 0.925)

	@change_settings("Payroll Settings", {"payroll_based_on": "Attendance"})
	def test_bonus_and_lunch_days_on_slip(self):
		ensure_fiscal_year_2099()
		ensure_mvl_defaults()
		emp = make_employee("mvl_bonus@codes.com", company=default_company())
		make_ssa(
			emp,
			base=25_000_000,
			custom_salary_type="Chính thức",
			custom_bhxh_salary=25_000_000,
			custom_register_personal_deduction=1,
		)
		mark_full_month(emp)  # checkin 08:00-17:30 mỗi ngày → phủ trưa
		ss = make_slip(emp)
		base_net = ss.net_pay
		# dữ liệu ăn trưa hiện trên phiếu (checkin phủ trưa mỗi ngày công)
		self.assertEqual(ss.custom_lunch_days, ss.payment_days)

		# HR điền Tiền thưởng → engine đọc, không ghi đè
		for row in ss.earnings:
			if row.salary_component == "Tiền thưởng":
				row.amount = 5_000_000
		ss.save()
		comp = {r.salary_component: r.amount for r in ss.earnings + ss.deductions}
		self.assertEqual(comp["Tiền thưởng"], 5_000_000)  # giữ nguyên số HR nhập
		self.assertEqual(ss.net_pay, base_net + 5_000_000)  # thưởng cộng vào thực lĩnh
		self.assertEqual(comp["Tổng thu nhập"], base_net + 5_000_000)  # K gồm thưởng
		self.assertGreater(comp["Thuế TNCN (nộp thay)"], 0)  # thưởng chịu thuế

	@change_settings("Payroll Settings", {"payroll_based_on": "Attendance"})
	def test_probation_slip_has_no_insurance_even_with_bhxh_salary(self):
		# Mẫu 09/2026 dòng 4: thử việc có nhập Lương đóng BHXH vẫn KHÔNG đóng BH. Trước đây engine
		# tính R/S rồi cấu trúc giấu đi, nhưng S vẫn lọt vào U và R+S vào gương chi phí (bút toán lệch).
		ensure_fiscal_year_2099()
		ensure_mvl_defaults()
		emp = make_employee("mvl_prob_bhxh@codes.com", company=default_company())
		make_ssa(
			emp,
			base=10_000_000,
			custom_salary_type="Thử việc",
			custom_bhxh_salary=10_000_000,
			custom_register_personal_deduction=1,
			custom_lunch_days_override=20,
		)
		mark_full_month(emp)
		ss = make_slip(emp, salary_type="Thử việc")
		comp = {r.salary_component: r.amount for r in list(ss.earnings) + list(ss.deductions)}
		tax = comp["Thuế TNCN (nộp thay)"]
		self.assertEqual(comp["Chi phí thuế & BHXH DN nộp thay"], tax)  # chỉ thuế, không BH
		self.assertEqual(comp["Thu nhập chịu thuế kê khai"], comp["Tổng thu nhập"] + tax - 700_000)

	@change_settings("Payroll Settings", {"payroll_based_on": "Attendance"})
	def test_template_row6_parttime_holiday_bonus(self):
		# Mẫu 09/2026 dòng 6: part time cư trú có đăng ký giảm trừ, 1 NPT, Lễ/Tết 500k → thuế 0
		ensure_fiscal_year_2099()
		ensure_mvl_defaults()
		emp = make_employee("mvl_pt_row6@codes.com", company=default_company())
		make_ssa(
			emp,
			base=5_000_000,
			custom_salary_type="Bán thời gian",
			custom_dependents=1,
			custom_register_personal_deduction=1,
			custom_is_resident=1,
		)
		mark_full_month(emp)
		make_additional_salary(emp, "Tiền thưởng", 500_000)
		ss = make_slip(emp, salary_type="Bán thời gian")
		comp = slip_amounts(ss)
		self.assertEqual(ss.payment_days, ss.total_working_days)  # đủ công → I = F
		self.assertEqual(comp["Tiền thưởng"], 500_000)
		self.assertEqual(ss.net_pay, 5_500_000)
		self.assertEqual(comp["Tổng giảm trừ gia cảnh"], 21_700_000)
		self.assertEqual(comp["Thuế TNCN (nộp thay)"], 0)
		self.assertEqual(comp["Thu nhập chịu thuế kê khai"], 5_500_000)

	@change_settings("Payroll Settings", {"payroll_based_on": "Attendance"})
	def test_khoan_holiday_bonus_untaxed(self):
		ensure_fiscal_year_2099()
		ensure_mvl_defaults()
		emp = make_employee("mvl_khoan_bonus@codes.com", company=default_company())
		make_ssa(emp, base=20_000_000, custom_salary_type="Khoán")
		mark_full_month(emp)
		make_additional_salary(emp, "Tiền thưởng", 5_000_000)
		ss = make_slip(emp, salary_type="Khoán")
		comp = slip_amounts(ss)
		self.assertEqual(ss.net_pay, 25_000_000)
		self.assertEqual(comp["Thuế TNCN (nộp thay)"], 0)

	@change_settings("Payroll Settings", {"payroll_based_on": "Attendance"})
	def test_bonus_rows_are_summed(self):
		# một row gõ tay trên phiếu + một row từ Additional Salary cùng component → cộng cả hai
		ensure_fiscal_year_2099()
		ensure_mvl_defaults()
		emp = make_employee("mvl_bonus_rows@codes.com", company=default_company())
		make_ssa(emp, base=20_000_000, custom_salary_type="Chính thức", custom_lunch_days_override=1)
		mark_full_month(emp)
		ss = make_slip(emp)
		base_k = slip_amounts(ss)["Tổng thu nhập"]
		make_additional_salary(emp, "Tiền thưởng", 1_000_000)
		for row in ss.earnings:
			if row.salary_component == "Tiền thưởng" and not row.additional_salary:
				row.amount = 2_000_000
		ss.save()
		comp = slip_amounts(ss)
		self.assertEqual(comp["Tiền thưởng"], 3_000_000)
		self.assertEqual(comp["Tổng thu nhập"], base_k + 3_000_000)
		self.assertEqual(ss.net_pay, base_k + 3_000_000)

	@change_settings("Payroll Settings", {"payroll_based_on": "Attendance"})
	def test_template_row1_allowances_via_recurring_additional_salary(self):
		# Mẫu 09/2026 dòng 1: F = G = 30tr, 2 NPT, điện thoại 500k + xăng xe 2tr (định kỳ), Lễ/Tết 1tr.
		# Mẫu ghi ăn trưa 1tr cố định; hệ thống chỉ tính buổi x 35k nên dùng 20 buổi (700k). J triệt
		# tiêu trong O và U → thuế / U vẫn đúng như mẫu, chỉ K và net thấp hơn mẫu đúng 300k.
		ensure_fiscal_year_2099()
		ensure_mvl_defaults()
		emp = make_employee("mvl_row1@codes.com", company=default_company())
		make_ssa(
			emp,
			base=30_000_000,
			custom_salary_type="Chính thức",
			custom_bhxh_salary=30_000_000,
			custom_dependents=2,
			custom_register_personal_deduction=1,
			custom_lunch_days_override=20,
		)
		mark_full_month(emp)
		recurring = {"is_recurring": 1, "from_date": "2099-06-01", "to_date": "2099-12-31"}
		make_additional_salary(emp, "Hỗ trợ điện thoại", 500_000, **recurring)
		make_additional_salary(emp, "Hỗ trợ xăng xe", 2_000_000, **recurring)
		make_additional_salary(emp, "Tiền thưởng", 1_000_000)
		ss = make_slip(emp)
		comp = slip_amounts(ss)
		self.assertEqual((comp["Hỗ trợ điện thoại"], comp["Hỗ trợ xăng xe"]), (500_000, 2_000_000))
		self.assertEqual(ss.net_pay, 34_200_000)
		self.assertEqual(comp["Thu nhập quy đổi"], 5_600_000)
		self.assertEqual(comp["Thuế TNCN (nộp thay)"], 294_737)
		self.assertEqual(comp["Thu nhập chịu thuế kê khai"], 36_944_737)

	@change_settings("Payroll Settings", {"payroll_based_on": "Attendance"})
	def test_template_row3_kpi(self):
		# Mẫu 09/2026 dòng 3: F = G = 10tr, 18 buổi ăn, KPI 500k, Lễ/Tết 1tr → thuế 0
		ensure_fiscal_year_2099()
		ensure_mvl_defaults()
		emp = make_employee("mvl_row3@codes.com", company=default_company())
		make_ssa(
			emp,
			base=10_000_000,
			custom_salary_type="Chính thức",
			custom_bhxh_salary=10_000_000,
			custom_register_personal_deduction=1,
			custom_lunch_days_override=18,
		)
		mark_full_month(emp)
		make_additional_salary(emp, "Thưởng KPI", 500_000)
		make_additional_salary(emp, "Tiền thưởng", 1_000_000)
		ss = make_slip(emp)
		comp = slip_amounts(ss)
		self.assertEqual(comp["Thưởng KPI"], 500_000)
		self.assertEqual(ss.net_pay, 12_130_000)
		self.assertEqual(comp["Thuế TNCN (nộp thay)"], 0)
		self.assertEqual(comp["Thu nhập chịu thuế kê khai"], 12_550_000)

	@change_settings("Payroll Settings", {"payroll_based_on": "Attendance"})
	def test_union_fee_on_official_slip(self):
		# KPCĐ công ty chịu: hiện trên phiếu, vào gương chi phí (Nợ 6421), KHÔNG trừ net, KHÔNG vào U
		ensure_fiscal_year_2099()
		ensure_mvl_defaults()
		emp = make_employee("mvl_kpcd@codes.com", company=default_company())
		make_ssa(
			emp,
			base=10_000_000,
			custom_salary_type="Chính thức",
			custom_bhxh_salary=8_000_000,
			custom_dependents=1,
			custom_register_personal_deduction=1,
			custom_lunch_days_override=18,
		)
		mark_full_month(emp)
		ss = make_slip(emp)
		comp = slip_amounts(ss)
		self.assertEqual(comp["KPCĐ - Công ty"], 160_000)  # mẫu dòng 5: G = 8tr
		self.assertEqual(comp["Chi phí thuế & BHXH DN nộp thay"], 0 + 840_000 + 1_720_000 + 160_000)
		self.assertEqual(ss.net_pay, 10_630_000)
		self.assertEqual(comp["Thu nhập chịu thuế kê khai"], 10_630_000 - 630_000 + 840_000)

	@change_settings("Payroll Settings", {"payroll_based_on": "Attendance"})
	def test_union_fee_not_in_mirror_when_slip_has_no_union_fee_row(self):
		# Deploy lệch (code mới chạy trước migrate → cấu trúc chưa có row KPCĐ): gương chi phí KHÔNG được
		# cộng X, nếu không bút toán Nợ 6421 / Có 334 dư X mà không có dòng Có 3382 nào đối ứng.
		ensure_fiscal_year_2099()
		ensure_mvl_defaults()
		frappe.db.delete(
			"Salary Detail",
			{"parent": "Chính thức", "parenttype": "Salary Structure", "salary_component": "KPCĐ - Công ty"},
		)
		emp = make_employee("mvl_kpcd_premigrate@codes.com", company=default_company())
		make_ssa(emp, base=10_000_000, custom_salary_type="Chính thức", custom_bhxh_salary=10_000_000)
		mark_full_month(emp)
		ss = make_slip(emp)
		comp = slip_amounts(ss)
		self.assertNotIn("KPCĐ - Công ty", comp)
		self.assertEqual(
			comp["Chi phí thuế & BHXH DN nộp thay"],
			comp["Thuế TNCN (nộp thay)"] + comp["BHXH - NLĐ (nộp thay)"] + comp["BHXH - Công ty"],
		)


class TestLunchKeptDays(PerTestRollback, FrappeTestCase):
	"""Buổi ăn "giữ lại" (công ty không nấu / nhân viên ăn ở ngoài) — theo mẫu Excel 09/2026: phụ cấp
	ăn trưa VẪN trả đủ số buổi, chỉ phần nộp quỹ canteen giảm (HR chốt 2026-11-04)."""

	def setUp(self):
		super().setUp()
		frappe.flags.skip_sheet_gate = True
		self.addCleanup(lambda: frappe.flags.pop("skip_sheet_gate", None))

	def keep(self, emp, days, reason="Công ty không nấu"):
		for day in days:
			name = frappe.db.get_value(
				"Attendance", {"employee": emp, "attendance_date": day, "docstatus": 1}
			)
			att = frappe.get_doc("Attendance", name)
			att.custom_lunch_kept = reason
			att.save()  # field sửa được sau submit (allow_on_submit)

	@change_settings("Payroll Settings", {"payroll_based_on": "Attendance"})
	def test_kept_lunches_are_counted_but_the_allowance_stays_whole(self):
		ensure_fiscal_year_2099()
		ensure_mvl_defaults()
		emp = make_employee("mvl_lunch_kept@codes.com", company=default_company())
		make_ssa(emp, base=25_000_000, custom_salary_type="Chính thức", custom_bhxh_salary=25_000_000)
		mark_full_month(emp)
		before = make_slip(emp)
		lunch_before, net_before = slip_amounts(before)["Phụ cấp ăn trưa"], before.net_pay
		before.delete()

		days = working_days_june_2099(emp)
		self.keep(emp, days[:1], "Công ty không nấu")
		self.keep(emp, days[1:2], "Ăn ở ngoài")
		ss = make_slip(emp)

		self.assertEqual(ss.custom_lunch_kept_days, 2)
		self.assertEqual(ss.custom_lunch_days, len(days), "số buổi ăn vẫn đủ")
		self.assertEqual(slip_amounts(ss)["Phụ cấp ăn trưa"], lunch_before, "phụ cấp ăn trưa không đổi")
		self.assertEqual(ss.net_pay, net_before, "thực lĩnh không đổi")

	@change_settings("Payroll Settings", {"payroll_based_on": "Attendance"})
	def test_keeping_a_day_without_lunch_counts_nothing(self):
		ensure_fiscal_year_2099()
		ensure_mvl_defaults()
		emp = make_employee("mvl_lunch_kept_none@codes.com", company=default_company())
		make_ssa(emp, base=25_000_000, custom_salary_type="Chính thức", custom_bhxh_salary=25_000_000)
		mark_full_month(emp)
		day = working_days_june_2099(emp)[0]
		name = frappe.db.get_value("Attendance", {"employee": emp, "attendance_date": day, "docstatus": 1})
		att = frappe.get_doc("Attendance", name)
		att.custom_lunch_override = "Không"
		att.custom_lunch_kept = "Ăn ở ngoài"
		att.save()
		ss = make_slip(emp)
		self.assertEqual(ss.custom_lunch_kept_days, 0, "ngày không tính ăn trưa thì không có gì để giữ lại")


class TestPaidHolidaysRunBeforeTheGate(PerTestRollback, FrappeTestCase):
	"""Đặt mẫu số lương (gồm ngày lễ) phải xảy ra TRƯỚC cổng đối soát bảng công.

	Lỗi 2026-08-04: cộng ngày lễ nằm trong `apply_mvl`, mà `hooks.py` xếp `sheet_gate.gate` chạy
	trước `apply_mvl`. Cổng vì thế so `payment_days` CHƯA cộng lễ (21,5) với "Tổng công" của bảng ĐÃ
	cộng lễ (22,5) → chặn toàn bộ 6 phiếu với "Lệch -1.0 ngày". Từ 2026-08-30 việc đó do
	`set_working_days` làm (đặt theo lịch tuần, thay `add_paid_holidays`); số học của nó — lễ trong mẫu
	số, vào làm / nghỉ việc giữa kỳ — kiểm ở `payroll/doctype/salary_slip/test_working_days_invariance`."""

	def validate_hooks(self):
		from hrms import hooks

		return hooks.doc_events["Salary Slip"]["validate"]

	def test_holidays_are_added_before_the_reconciliation_gate(self):
		hooks = self.validate_hooks()
		add = "hrms.vn_payroll.salary_slip_hook.set_working_days"
		gate = "hrms.vn_payroll.sheet_gate.gate"
		self.assertIn(add, hooks, "cộng ngày lễ phải là một hook riêng, không nấp trong apply_mvl")
		self.assertLess(
			hooks.index(add),
			hooks.index(gate),
			"cộng ngày lễ phải chạy TRƯỚC cổng đối soát, nếu không cổng so số chưa cộng với bảng đã cộng",
		)

	def test_apply_mvl_does_not_set_working_days_a_second_time(self):
		"""apply_mvl chạy SAU cổng; đặt lại mẫu số ở đó là cổng đã so một con số khác với phiếu."""
		import inspect

		from hrms.vn_payroll import salary_slip_hook

		self.assertNotIn(
			"set_working_days(",
			inspect.getsource(salary_slip_hook.apply_mvl),
			"apply_mvl không được gọi lại — hook đã chạy nó trước cổng rồi",
		)
