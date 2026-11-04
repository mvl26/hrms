# Copyright (c) 2026, Miyano Việt Nam.
"""Gửi email phiếu lương hàng loạt (nút trên danh sách Salary Slip) không được sót phiếu im lặng.

HR báo 2026-11-04: tích 10 phiếu, chỉ 6 email được tạo. Hai đường rơi không ai thấy:
- nhân viên chưa có Email ưu tiên → `email_salary_slip` chỉ `msgprint` TRONG job nền;
- một phiếu lỗi (PDF / email template) → cả job dừng, các phiếu sau không bao giờ được gửi.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from erpnext.setup.doctype.employee.test_employee import make_employee

from hrms.payroll.doctype.salary_slip import salary_slip as module
from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import default_company


def bare_slip(employee) -> str:
	"""Phiếu tối thiểu chỉ để có tên + nhân viên (bỏ qua validate — test không tính lương)."""
	doc = frappe.get_doc(
		{
			"doctype": "Salary Slip",
			"employee": employee,
			"employee_name": frappe.db.get_value("Employee", employee, "employee_name"),
			"company": default_company(),
			"start_date": "2099-06-01",
			"end_date": "2099-06-30",
			"posting_date": "2099-06-30",
		}
	)
	doc.set_new_name()
	doc.db_insert()
	return doc.name


def employee_with_email(user: str, preferred: bool) -> str:
	emp = make_employee(user, company=default_company())
	frappe.db.set_value("Employee", emp, "prefered_email", user if preferred else None)
	return emp


class TestEmailSalarySlips(PerTestRollback, FrappeTestCase):
	def test_slips_without_preferred_email_are_reported_not_silently_dropped(self):
		ok = bare_slip(employee_with_email("ss_mail_ok@codes.com", preferred=True))
		missing_emp = employee_with_email("ss_mail_missing@codes.com", preferred=False)
		missing = bare_slip(missing_emp)

		with patch.object(frappe, "enqueue") as enqueue, patch.object(frappe, "msgprint") as msgprint:
			module.enqueue_email_salary_slips([ok, missing])

		self.assertEqual(enqueue.call_args.kwargs["names"], [ok], "chỉ xếp hàng phiếu có người nhận")
		shown = " ".join(str(c.args[0]) for c in msgprint.call_args_list)
		self.assertIn(frappe.db.get_value("Employee", missing_emp, "employee_name"), shown)
		self.assertIn("1", shown)  # số phiếu đã xếp hàng

	def test_nothing_sendable_enqueues_nothing(self):
		missing = bare_slip(employee_with_email("ss_mail_none@codes.com", preferred=False))
		with patch.object(frappe, "enqueue") as enqueue, patch.object(frappe, "msgprint"):
			module.enqueue_email_salary_slips([missing])
		enqueue.assert_not_called()

	def test_one_failing_slip_does_not_stop_the_rest(self):
		names = [
			bare_slip(employee_with_email(f"ss_mail_loop{i}@codes.com", preferred=True)) for i in range(3)
		]
		sent = []

		def fake_email(self):
			if self.name == names[0]:
				raise frappe.ValidationError("PDF hỏng")
			sent.append(self.name)

		before = frappe.db.count("Error Log")
		with patch.object(module.SalarySlip, "email_salary_slip", fake_email):
			module.email_salary_slips(names)

		self.assertEqual(sent, names[1:], "phiếu lỗi không chặn các phiếu sau")
		self.assertEqual(frappe.db.count("Error Log"), before + 1, "phiếu lỗi được ghi Error Log")
