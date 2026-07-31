import frappe
from frappe.tests.utils import FrappeTestCase

from erpnext.setup.doctype.employee.test_employee import make_employee

from hrms.payroll.doctype.employee_tax_exemption_declaration.test_employee_tax_exemption_declaration import (
	PAYROLL_PERIOD_END,
	PAYROLL_PERIOD_NAME,
	PAYROLL_PERIOD_START,
	create_exemption_category,
	create_payroll_period,
)


class TestEmployeeTaxExemptionProofSubmission(FrappeTestCase):
	def setUp(self):
		frappe.db.delete("Employee Tax Exemption Proof Submission")
		frappe.db.delete("Salary Structure Assignment")

		make_employee("employee@proofsubmission.com", company="_Test Company")
		create_payroll_period(
			company="_Test Company",
			name=PAYROLL_PERIOD_NAME,
			start_date=PAYROLL_PERIOD_START,
			end_date=PAYROLL_PERIOD_END,
		)

		create_exemption_category()

	def test_exemption_amount_lesser_than_category_max(self):
		proof = frappe.get_doc(
			{
				"doctype": "Employee Tax Exemption Proof Submission",
				"employee": frappe.get_value("Employee", {"user_id": "employee@proofsubmission.com"}, "name"),
				"payroll_period": "Test Payroll Period",
				"tax_exemption_proofs": [
					dict(
						exemption_sub_category="_Test Sub Category",
						type_of_proof="Test Proof",
						exemption_category="_Test Category",
						amount=150000,
					)
				],
			}
		)
		self.assertRaises(frappe.ValidationError, proof.save)
		proof = frappe.get_doc(
			{
				"doctype": "Employee Tax Exemption Proof Submission",
				"payroll_period": "Test Payroll Period",
				"employee": frappe.get_value("Employee", {"user_id": "employee@proofsubmission.com"}, "name"),
				"tax_exemption_proofs": [
					dict(
						exemption_sub_category="_Test Sub Category",
						type_of_proof="Test Proof",
						exemption_category="_Test Category",
						amount=100000,
					)
				],
			}
		)
		self.assertTrue(proof.save)
		self.assertTrue(proof.submit)

	def test_duplicate_category_in_proof_submission(self):
		proof = frappe.get_doc(
			{
				"doctype": "Employee Tax Exemption Proof Submission",
				"employee": frappe.get_value("Employee", {"user_id": "employee@proofsubmission.com"}, "name"),
				"payroll_period": "Test Payroll Period",
				"tax_exemption_proofs": [
					dict(
						exemption_sub_category="_Test Sub Category",
						exemption_category="_Test Category",
						type_of_proof="Test Proof",
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
		self.assertRaises(frappe.ValidationError, proof.save)
