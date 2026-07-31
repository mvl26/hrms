# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
"""Ai được lập phiếu lương: chỉ người ĐANG làm việc, cộng người nghỉ việc giữa kỳ.

Bản gốc của `get_filtered_employees` chỉ loại trạng thái `Inactive`, nên nhân viên đã `Left`
(nghỉ việc) hay `Suspended` (đình chỉ) mà chưa điền ngày nghỉ việc vẫn được lập phiếu lương —
đúng thứ cần chặn.

Nhưng không được loại thẳng mọi người không `Active`: nghỉ việc ngày 15 thì 15 ngày đã làm vẫn
phải được trả. Hai test cuối khoá đúng ranh giới đó.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import default_company


class TestPayrollRoster(PerTestRollback, FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = default_company()
		cls.structure = frappe.db.get_value(
			"Salary Structure Assignment", {"docstatus": 1}, ["salary_structure", "payroll_payable_account"]
		)

	def setUp(self):
		if not self.structure:
			self.skipTest("site chưa có Salary Structure Assignment nào để dựng bộ lọc")

	def mk_employee(self, ten, status, relieving=None):
		"""Nhân viên có gán cấu trúc lương — điều kiện cần để lọt vào danh sách lập phiếu."""
		from erpnext.setup.doctype.employee.test_employee import make_employee

		emp = make_employee(f"{ten}@roster.test", company=self.company, date_of_joining="2098-01-01")
		frappe.get_doc(
			{
				"doctype": "Salary Structure Assignment",
				"employee": emp,
				"salary_structure": self.structure[0],
				"from_date": "2098-01-01",
				"company": self.company,
				"payroll_payable_account": self.structure[1],
				"base": 10_000_000,
			}
		).insert().submit()
		# đặt trạng thái SAU khi gán lương: Frappe chặn gán cho người đã nghỉ việc
		frappe.db.set_value("Employee", emp, {"status": status, "relieving_date": relieving})
		return emp

	def roster(self, start="2098-05-01", end="2098-05-31") -> set:
		from hrms.payroll.doctype.payroll_entry.payroll_entry import get_filtered_employees

		rows = get_filtered_employees(
			[self.structure[0]],
			frappe._dict(
				company=self.company,
				start_date=start,
				end_date=end,
				payroll_payable_account=self.structure[1],
			),
			as_dict=True,
			ignore_match_conditions=True,
		)
		return {r.employee if "employee" in r else r.name for r in rows}

	def test_an_active_employee_gets_a_slip(self):
		self.assertIn(self.mk_employee("pr_active", "Active"), self.roster())

	def test_an_inactive_employee_does_not(self):
		self.assertNotIn(self.mk_employee("pr_inactive", "Inactive"), self.roster())

	def test_someone_who_left_without_a_relieving_date_does_not(self):
		self.assertNotIn(self.mk_employee("pr_left", "Left"), self.roster())

	def test_a_suspended_employee_does_not(self):
		self.assertNotIn(self.mk_employee("pr_susp", "Suspended"), self.roster())

	def test_someone_who_left_mid_period_is_still_paid(self):
		"""Ranh giới quan trọng: loại thẳng mọi người không Active là quỵt lương ngày đã làm."""
		emp = self.mk_employee("pr_left_mid", "Left", relieving="2098-05-15")
		self.assertIn(emp, self.roster())

	def test_someone_who_left_before_the_period_is_not_paid_again(self):
		emp = self.mk_employee("pr_left_before", "Left", relieving="2098-03-31")
		self.assertNotIn(emp, self.roster())
