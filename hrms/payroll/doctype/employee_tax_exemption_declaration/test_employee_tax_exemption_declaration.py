import frappe
from frappe.tests.utils import FrappeTestCase

import erpnext
from erpnext.setup.doctype.employee.test_employee import make_employee

from hrms.hr.utils import DuplicateDeclarationError

PAYROLL_PERIOD_NAME = "_Test Exemption Period"
PAYROLL_PERIOD_START = "2022-01-01"
PAYROLL_PERIOD_END = "2022-12-31"


class TestEmployeeTaxExemptionDeclaration(FrappeTestCase):
	def setUp(self):
		frappe.db.delete("Employee Tax Exemption Declaration")
		frappe.db.delete("Salary Structure Assignment")
		frappe.db.delete("Salary Slip")

		make_employee("employee@taxexemption.com", company="_Test Company")
		make_employee("employee1@taxexemption.com", company="_Test Company")

		create_payroll_period(
			company="_Test Company",
			name=PAYROLL_PERIOD_NAME,
			start_date=PAYROLL_PERIOD_START,
			end_date=PAYROLL_PERIOD_END,
		)
		create_exemption_category()

	def test_duplicate_category_in_declaration(self):
		declaration = frappe.get_doc(
			{
				"doctype": "Employee Tax Exemption Declaration",
				"employee": frappe.get_value("Employee", {"user_id": "employee@taxexemption.com"}, "name"),
				"company": erpnext.get_default_company(),
				"payroll_period": PAYROLL_PERIOD_NAME,
				"currency": erpnext.get_default_currency(),
				"declarations": [
					dict(
						exemption_sub_category="_Test Sub Category",
						exemption_category="_Test Category",
						amount=100000,
					),
					dict(
						exemption_sub_category="_Test Sub Category",
						exemption_category="_Test Category",
						amount=50000,
					),
				],
			}
		)
		self.assertRaises(frappe.ValidationError, declaration.save)

	def test_duplicate_entry_for_payroll_period(self):
		frappe.get_doc(
			{
				"doctype": "Employee Tax Exemption Declaration",
				"employee": frappe.get_value("Employee", {"user_id": "employee@taxexemption.com"}, "name"),
				"company": erpnext.get_default_company(),
				"payroll_period": PAYROLL_PERIOD_NAME,
				"currency": erpnext.get_default_currency(),
				"declarations": [
					dict(
						exemption_sub_category="_Test Sub Category",
						exemption_category="_Test Category",
						amount=100000,
					),
					dict(
						exemption_sub_category="_Test1 Sub Category",
						exemption_category="_Test Category",
						amount=50000,
					),
				],
			}
		).insert()

		duplicate_declaration = frappe.get_doc(
			{
				"doctype": "Employee Tax Exemption Declaration",
				"employee": frappe.get_value("Employee", {"user_id": "employee@taxexemption.com"}, "name"),
				"company": erpnext.get_default_company(),
				"payroll_period": PAYROLL_PERIOD_NAME,
				"currency": erpnext.get_default_currency(),
				"declarations": [
					dict(
						exemption_sub_category="_Test Sub Category",
						exemption_category="_Test Category",
						amount=100000,
					)
				],
			}
		)
		self.assertRaises(DuplicateDeclarationError, duplicate_declaration.insert)
		duplicate_declaration.employee = frappe.get_value(
			"Employee", {"user_id": "employee1@taxexemption.com"}, "name"
		)
		self.assertTrue(duplicate_declaration.insert)

	def test_exemption_amount(self):
		declaration = frappe.get_doc(
			{
				"doctype": "Employee Tax Exemption Declaration",
				"employee": frappe.get_value("Employee", {"user_id": "employee@taxexemption.com"}, "name"),
				"company": erpnext.get_default_company(),
				"payroll_period": PAYROLL_PERIOD_NAME,
				"currency": erpnext.get_default_currency(),
				"declarations": [
					dict(
						exemption_sub_category="_Test Sub Category",
						exemption_category="_Test Category",
						amount=80000,
					),
					dict(
						exemption_sub_category="_Test1 Sub Category",
						exemption_category="_Test Category",
						amount=60000,
					),
				],
			}
		).insert()

		self.assertEqual(declaration.total_exemption_amount, 100000)


def create_payroll_period(**args):
	args = frappe._dict(args)
	name = args.name or "_Test Payroll Period"
	if not frappe.db.exists("Payroll Period", name):
		from datetime import date

		payroll_period = frappe.get_doc(
			dict(
				doctype="Payroll Period",
				name=name,
				company=args.company or erpnext.get_default_company(),
				start_date=args.start_date or date(date.today().year, 1, 1),
				end_date=args.end_date or date(date.today().year, 12, 31),
			)
		).insert()
		return payroll_period
	else:
		return frappe.get_doc("Payroll Period", name)


def create_exemption_category():
	if not frappe.db.exists("Employee Tax Exemption Category", "_Test Category"):
		frappe.get_doc(
			{
				"doctype": "Employee Tax Exemption Category",
				"name": "_Test Category",
				"deduction_component": "Income Tax",
				"max_amount": 100000,
			}
		).insert()
	if not frappe.db.exists("Employee Tax Exemption Sub Category", "_Test Sub Category"):
		frappe.get_doc(
			{
				"doctype": "Employee Tax Exemption Sub Category",
				"name": "_Test Sub Category",
				"exemption_category": "_Test Category",
				"max_amount": 100000,
				"is_active": 1,
			}
		).insert()
	if not frappe.db.exists("Employee Tax Exemption Sub Category", "_Test1 Sub Category"):
		frappe.get_doc(
			{
				"doctype": "Employee Tax Exemption Sub Category",
				"name": "_Test1 Sub Category",
				"exemption_category": "_Test Category",
				"max_amount": 50000,
				"is_active": 1,
			}
		).insert()
