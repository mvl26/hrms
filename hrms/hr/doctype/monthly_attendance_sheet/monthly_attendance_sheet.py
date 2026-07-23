# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# For license information, please see license.txt
"""Bảng Công Tháng — submittable monthly timekeeping sheet, one per đơn vị / tháng.

A READ-ONLY snapshot: `populate_from_attendance` fills the child rows from the shared
timekeeping derivation (get_sheet_rows). This document NEVER writes to Attendance, so it is
provably payroll-neutral.
"""

from calendar import monthrange

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, getdate


class MonthlyAttendanceSheet(Document):
	def validate(self):
		self.set_period_dates()
		self.check_duplicate()

	def set_period_dates(self):
		year, month = cint(self.year), cint(self.month)
		if not (year and month):
			frappe.throw(_("Vui lòng chọn tháng và năm."))
		days = monthrange(year, month)[1]
		self.from_date = getdate(f"{year}-{month:02d}-01")
		self.to_date = getdate(f"{year}-{month:02d}-{days:02d}")

	def check_duplicate(self):
		filters = {
			"company": self.company,
			"month": self.month,
			"year": self.year,
			"docstatus": ["<", 2],
			"name": ["!=", self.name or ""],
		}
		filters["department"] = self.department if self.department else ["is", "not set"]
		existing = frappe.db.get_value("Monthly Attendance Sheet", filters, "name")
		if existing:
			frappe.throw(_("Đã có Bảng công tháng {0} cho đơn vị/tháng này.").format(existing))

	@frappe.whitelist()
	def populate_from_attendance(self):
		"""Fill the employee rows from the month's Attendance (read-only snapshot). Draft only."""
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import get_sheet_rows

		if self.docstatus != 0:
			frappe.throw(_("Chỉ lấy dữ liệu được khi bảng còn ở trạng thái nháp."))
		self.set_period_dates()

		filters = frappe._dict(
			month=self.month,
			year=self.year,
			company=self.company,
			include_company_descendants=self.include_company_descendants,
		)
		if self.department:
			filters.department = self.department

		category_field = {
			"Công": "work_days",
			"Phép": "annual_leave",
			"Việc riêng": "personal_leave",
			"Ốm": "sick_leave",
			"Thai sản": "maternity_leave",
			"Tai nạn LĐ": "work_accident_leave",
			"Nghỉ bù": "comp_off",
			"Không lương": "unpaid_leave",
			"Vắng": "absent",
			"Nghỉ lễ": "public_holiday",
		}

		self.set("employees", [])
		for r in get_sheet_rows(filters):
			row = {"employee": r["employee"], "employee_name": r["employee_name"]}
			for day, sym in r["days"].items():
				row[f"d{int(day):02d}"] = sym
			for cat, val in r["totals"].items():
				if cat in category_field:
					row[category_field[cat]] = val
			self.append("employees", row)
		return len(self.employees)
