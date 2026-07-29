# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
"""Cổng lương: chặn phiếu khi kỳ chưa chốt, và đối soát phiếu với bảng đã chốt."""

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import ensure_short_hours_code
from hrms.vn_payroll.sheet_gate import (
	gate,
	gate_enabled,
	paid_days_in_sheet,
	reconcile_with_sheet,
	require_submitted_sheet,
	sheet_row_for,
	submitted_sheet_for,
)


class TestGateSwitch(FrappeTestCase):
	def test_the_gate_is_off_unless_the_site_turns_it_on(self):
		"""Bật cổng khi còn phiếu lệch thì không ai lập được lương → mặc định phải TẮT."""
		frappe.conf.pop("hrms_enforce_sheet_gate", None)
		self.assertFalse(gate_enabled())

	def test_the_site_config_flag_turns_it_on(self):
		frappe.conf["hrms_enforce_sheet_gate"] = 1
		try:
			self.assertTrue(gate_enabled())
		finally:
			frappe.conf.pop("hrms_enforce_sheet_gate", None)


class TestSheetGate(PerTestRollback, FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_short_hours_code()
		cls.emp = frappe.db.get_value("Employee", {"status": "Active"}, "name")
		cls.company = frappe.db.get_value("Employee", cls.emp, "company")

	def setUp(self):
		frappe.conf["hrms_enforce_sheet_gate"] = 1
		self.addCleanup(lambda: frappe.conf.pop("hrms_enforce_sheet_gate", None))

	def slip(self, month=8, year=2099):
		from calendar import monthrange

		doc = frappe.new_doc("Salary Slip")
		doc.employee = self.emp
		doc.company = self.company
		doc.start_date = f"{year}-{month:02d}-01"
		doc.end_date = f"{year}-{month:02d}-{monthrange(year, month)[1]:02d}"
		return doc

	def mk_sheet(self, month=8, year=2099):
		sheet = frappe.get_doc(
			{
				"doctype": "Monthly Attendance Sheet",
				"company": self.company,
				"month": str(month),
				"year": year,
			}
		).insert()
		sheet.populate_from_attendance()
		sheet.save()
		sheet.submit()
		return sheet

	def test_a_period_with_no_submitted_sheet_blocks_the_slip(self):
		with self.assertRaises(frappe.exceptions.ValidationError) as cm:
			require_submitted_sheet(self.slip())
		self.assertIn("chưa có Bảng Công Tháng", str(cm.exception))

	def test_a_draft_sheet_does_not_count_as_closed(self):
		frappe.get_doc(
			{"doctype": "Monthly Attendance Sheet", "company": self.company, "month": "8", "year": 2099}
		).insert()
		self.assertIsNone(submitted_sheet_for(self.emp, "2099-08-01", "2099-08-31"))

	def test_a_submitted_sheet_lets_the_slip_through(self):
		self.mk_sheet()
		require_submitted_sheet(self.slip())  # không throw là đạt

	def test_reconcile_passes_when_the_slip_matches_the_sheet(self):
		sheet = self.mk_sheet()
		row = sheet_row_for(self.emp, "2099-08-01")
		self.assertIsNotNone(row, f"bảng {sheet.name} phải có hàng của nhân viên")

		doc = self.slip()
		doc.payment_days = paid_days_in_sheet(row)
		reconcile_with_sheet(doc)  # không throw là đạt

	def test_reconcile_blocks_a_slip_that_drifted_from_the_sheet(self):
		self.mk_sheet()
		row = sheet_row_for(self.emp, "2099-08-01")

		doc = self.slip()
		doc.payment_days = paid_days_in_sheet(row) + 0.5  # ai đó sửa công sau khi chốt
		with self.assertRaises(frappe.exceptions.ValidationError) as cm:
			reconcile_with_sheet(doc)
		self.assertIn("không khớp", str(cm.exception))

	def test_the_gate_is_a_no_op_while_the_flag_is_off(self):
		frappe.conf.pop("hrms_enforce_sheet_gate", None)
		gate(self.slip())  # kỳ chưa chốt mà vẫn không throw, vì cổng đang tắt


class TestGateAgainstLiveData(PerTestRollback, FrappeTestCase):
	"""Chạy cổng trên phiếu lương THẬT của site — đây là thứ quyết định khi nào được bật cờ."""

	def test_report_which_live_slips_the_gate_would_block(self):
		slips = frappe.get_all(
			"Salary Slip",
			filters={"docstatus": 1},
			fields=["name", "employee", "start_date", "end_date", "payment_days", "company"],
			order_by="start_date",
		)
		self.assertTrue(slips, "site không có phiếu lương đã submit để đối soát")

		blocked = []
		for s in slips:
			doc = frappe.new_doc("Salary Slip")
			doc.update(s)
			try:
				reconcile_with_sheet(doc)
			except frappe.exceptions.ValidationError:
				row = sheet_row_for(s.employee, s.start_date)
				blocked.append(
					f"{s.name}: phiếu {s.payment_days} vs bảng {paid_days_in_sheet(row) if row else '?'}"
				)

		# Sau khi dọn dữ liệu seed và chấm lại từ lượt chấm (2026-07-29), toàn bộ phiếu lương phải
		# khớp bảng đã chốt. Test này là chốt chặn: bất kỳ lệch nào xuất hiện lại đều phải nổ ở đây
		# trước khi ai đó phát hiện qua bảng lương.
		self.assertEqual(blocked, [], f"có phiếu lương lệch khỏi bảng đã chốt: {blocked}")
