import frappe
from frappe import _
from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from frappe.model.document import Document
from frappe.utils import cint

# Tab "Lương Miyano (VN)" (gộp từ MVL Payroll Settings 2026-11-04): lưu dạng TỶ LỆ (0,215 = 21,5%)
# dù nhãn ghi "(%)" — gõ nhầm 2 thay vì 0,02 là KPCĐ = 200% lương đóng BHXH.
MVL_RATE_FIELDS = ("insurance_company_rate", "insurance_employee_rate", "union_fee_rate")


class PayrollSettings(Document):
	def validate(self):
		self.validate_password_policy()
		self.validate_mvl_rates()

		if not self.daily_wages_fraction_for_half_day:
			self.daily_wages_fraction_for_half_day = 0.5

	def validate_mvl_rates(self):
		for field in MVL_RATE_FIELDS:
			value = self.get(field)
			if value is not None and not 0 <= value < 1:
				frappe.throw(
					_("{0} phải là tỷ lệ từ 0 đến dưới 1 (ví dụ 0,02 cho 2%), không phải {1}.").format(
						_(self.meta.get_label(field)), value
					)
				)

	def validate_password_policy(self):
		if self.email_salary_slip_to_employee and self.encrypt_salary_slips_in_emails:
			if not self.password_policy:
				frappe.throw(_("Password policy for Salary Slips is not set"))

	def on_update(self):
		self.toggle_rounded_total()
		frappe.clear_cache()

	def toggle_rounded_total(self):
		self.disable_rounded_total = cint(self.disable_rounded_total)
		make_property_setter(
			"Salary Slip",
			"rounded_total",
			"hidden",
			self.disable_rounded_total,
			"Check",
			validate_fields_for_doctype=False,
		)
		make_property_setter(
			"Salary Slip",
			"rounded_total",
			"print_hide",
			self.disable_rounded_total,
			"Check",
			validate_fields_for_doctype=False,
		)
