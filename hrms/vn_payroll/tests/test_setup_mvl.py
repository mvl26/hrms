# Copyright (c) 2026, Miyano Việt Nam.
import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.tests.isolation import PerTestRollback
from hrms.vn_payroll.setup_mvl import (
	COMPONENT_ACCOUNT_NUMBERS,
	COMPONENTS,
	FIELD_DESCRIPTIONS,
	HR_ENTERED_COMPONENTS,
	REAL_EARNINGS,
	SALARY_TYPES,
	STRUCTURES,
	ensure_mvl_defaults,
)


class TestSetupMVL(PerTestRollback, FrappeTestCase):
	def setUp(self):
		super().setUp()
		# tham số MVL ở Payroll Settings (gộp 2026-11-04) — nạp meta trong transaction (Single → DML)
		frappe.reload_doc("payroll", "doctype", "payroll_settings")

	def tearDown(self):
		super().tearDown()
		frappe.clear_cache(doctype="Payroll Settings")

	def test_gross_not_offered_until_implemented(self):
		# GROSS chưa hiện thực → không được cho HR chọn (tránh ra phiếu sai âm thầm)
		self.assertNotIn("GROSS", SALARY_TYPES.split("\n"))
		self.assertIn("Chính thức", SALARY_TYPES.split("\n"))

	def test_every_money_column_is_a_component(self):
		ensure_mvl_defaults()
		# mọi cột tiền của bảng lương là 1 Salary Component (master dùng chung cho mọi cấu trúc)
		for name, *_ in COMPONENTS:
			self.assertTrue(frappe.db.exists("Salary Component", name), name)

	def test_each_type_has_its_own_structure_with_the_right_components(self):
		ensure_mvl_defaults()
		# mỗi loại lương một Salary Structure riêng, chứa ĐÚNG tập component của loại đó (khớp Excel)
		for name, (_stype, earnings, deductions) in STRUCTURES.items():
			doc = frappe.get_doc("Salary Structure", name)
			self.assertEqual({r.salary_component for r in doc.earnings}, set(earnings), name)
			self.assertEqual({r.salary_component for r in doc.deductions}, set(deductions), name)
			self.assertEqual(doc.docstatus, 1, name)  # submit để gán được vào SSA
		# bán thời gian / khoán / chuyên gia KHÔNG có ăn trưa / BHXH / giảm trừ (đúng Excel)
		for lean in ("Bán thời gian", "Khoán", "Chuyên gia"):
			comps = {r.salary_component for r in frappe.get_doc("Salary Structure", lean).earnings}
			self.assertNotIn("Phụ cấp ăn trưa", comps, lean)
			self.assertNotIn("Lương đóng BHXH", comps, lean)
		# thử việc không có BHXH ở deductions
		tv = {r.salary_component for r in frappe.get_doc("Salary Structure", "Thử việc").deductions}
		self.assertNotIn("BHXH - NLĐ (nộp thay)", tv)

	def test_parttime_structure_shows_family_deduction(self):
		# part time có đăng ký giảm trừ được trừ gia cảnh (chốt 2026-10-30) → phiếu/báo cáo phải hiện được;
		# khoán / chuyên gia thì không bao giờ
		comps = lambda name: set(STRUCTURES[name][2])  # noqa: E731
		for c in ("Giảm trừ bản thân", "Tổng giảm trừ gia cảnh"):
			self.assertIn(c, comps("Bán thời gian"))
			self.assertNotIn(c, comps("Khoán"))
			self.assertNotIn(c, comps("Chuyên gia"))

	def test_every_type_declares_taxable_income(self):
		# cột Thu nhập chịu thuế có ở MỌI loại, kể cả khoán không khấu trừ (bảng lương 10/2026 dòng 22)
		for name, (_stype, earnings, _deductions) in STRUCTURES.items():
			self.assertIn("Thu nhập chịu thuế kê khai", earnings, name)

	def test_every_type_can_receive_holiday_bonus(self):
		# mẫu 09/2026: cả part time (dòng 6) cũng có Thưởng (Lễ/Tết)
		for name, (_stype, earnings, _deductions) in STRUCTURES.items():
			self.assertIn("Tiền thưởng", earnings, name)

	def test_allowances_and_kpi_are_taxable_hr_entered_and_accounted(self):
		# mẫu 09/2026 cột K, L, M: chịu thuế (S chỉ loại J), cộng thực lĩnh, HR nhập theo kỳ, Nợ 6421.
		# Thiếu TK GL thì Payroll Entry không dựng được bút toán ("Please set account").
		spec = {c[0]: c for c in COMPONENTS}
		for comp in ("Hỗ trợ điện thoại", "Hỗ trợ xăng xe", "Thưởng KPI"):
			self.assertEqual(spec[comp][1:], ("Earning", 1, 0), comp)
			self.assertIn(comp, REAL_EARNINGS)
			self.assertIn(comp, HR_ENTERED_COMPONENTS)
			self.assertEqual(COMPONENT_ACCOUNT_NUMBERS.get(comp), "6421", comp)
			for structure in ("Chính thức", "Thử việc"):
				self.assertIn(comp, STRUCTURES[structure][1], f"{structure}:{comp}")

	def test_union_fee_posts_to_3382_and_stays_out_of_net(self):
		spec = {c[0]: c for c in COMPONENTS}
		self.assertEqual(spec["KPCĐ - Công ty"][1:], ("Deduction", 0, 1))  # không trừ net
		self.assertEqual(COMPONENT_ACCOUNT_NUMBERS.get("KPCĐ - Công ty"), "3382")  # Có 3382, vào JV
		self.assertIn("KPCĐ - Công ty", STRUCTURES["Chính thức"][2])

	def test_only_nonmoney_params_are_slip_fields(self):
		ensure_mvl_defaults()
		self.assertTrue(frappe.db.exists("Custom Field", "Salary Slip-custom_coefficient"))  # E
		self.assertTrue(frappe.db.exists("Custom Field", "Salary Slip-custom_dependents_slip"))  # M
		# các cột tiền cũ KHÔNG còn là field (đã thành component)
		for fn in ("custom_base_salary", "custom_gross_income", "custom_ins_company"):
			self.assertFalse(frappe.db.exists("Custom Field", f"Salary Slip-{fn}"), fn)

	def test_lunch_component_is_tax_exempt(self):
		ensure_mvl_defaults()
		self.assertEqual(frappe.db.get_value("Salary Component", "Phụ cấp ăn trưa", "is_tax_applicable"), 0)

	def test_tax_and_insurance_do_not_reduce_net(self):
		ensure_mvl_defaults()
		for c in ("Thuế TNCN (nộp thay)", "BHXH - NLĐ (nộp thay)"):
			self.assertEqual(frappe.db.get_value("Salary Component", c, "do_not_include_in_total"), 1, c)

	def test_accounting_excludes_display_components_from_jv(self):
		ensure_mvl_defaults()
		# chỉ component hạch toán (COMPONENT_ACCOUNT_NUMBERS) vào bút toán accrual; cột hiển thị bị loại
		accounted = set(COMPONENT_ACCOUNT_NUMBERS)
		for name, *_ in COMPONENTS:
			expected = 0 if name in accounted else 1
			self.assertEqual(
				frappe.db.get_value("Salary Component", name, "do_not_include_in_accounts"), expected, name
			)
		# cờ cũng phải xuống tới detail row của cấu trúc (slip copy cờ TỪ đó, không từ component master)
		for sname in STRUCTURES:
			for r in frappe.get_all(
				"Salary Detail",
				filters={"parent": sname, "parenttype": "Salary Structure"},
				fields=["salary_component", "do_not_include_in_accounts"],
			):
				self.assertEqual(
					r.do_not_include_in_accounts,
					0 if r.salary_component in accounted else 1,
					f"{sname}:{r.salary_component}",
				)

	def test_accounting_components_mapped_to_gl_account(self):
		ensure_mvl_defaults()
		# component hạch toán có Salary Component Account cho company (chỉ kiểm khi CoA có TK đó — CI có thể không)
		company = frappe.defaults.get_defaults().get("company") or frappe.db.get_value("Company", {}, "name")
		for comp, num in COMPONENT_ACCOUNT_NUMBERS.items():
			if frappe.db.exists("Account", {"account_number": num, "company": company, "is_group": 0}):
				self.assertTrue(
					frappe.db.exists("Salary Component Account", {"parent": comp, "company": company}), comp
				)

	def test_idempotent_and_non_destructive(self):
		ensure_mvl_defaults()
		frappe.db.set_single_value("Payroll Settings", "lunch_rate_per_day", 40_000)
		ensure_mvl_defaults()  # chạy lại không được ghi đè giá trị đã sửa
		self.assertEqual(frappe.db.get_single_value("Payroll Settings", "lunch_rate_per_day"), 40_000)
		# không nhân đôi bậc thuế
		s = frappe.get_single("Payroll Settings")
		self.assertEqual(len(s.tax_brackets), 5)

	def test_field_help_follows_current_tax_rules_on_installed_site(self):
		# Site đã cài thì guard của ensure_custom_fields bỏ qua create_custom_fields — mô tả cũ (luật
		# part time trước 30/10) kẹt lại mãi. Mô tả là metadata, phải tự đồng bộ mỗi lần migrate.
		ensure_mvl_defaults()
		name = "Salary Structure Assignment-custom_is_resident"
		frappe.db.set_value("Custom Field", name, "description", "mô tả cũ")
		ensure_mvl_defaults()
		for (doctype, fieldname), text in FIELD_DESCRIPTIONS.items():
			self.assertEqual(
				frappe.db.get_value("Custom Field", f"{doctype}-{fieldname}", "description"), text, fieldname
			)
		self.assertIn("lũy tiến", FIELD_DESCRIPTIONS[("Salary Structure Assignment", "custom_is_resident")])
