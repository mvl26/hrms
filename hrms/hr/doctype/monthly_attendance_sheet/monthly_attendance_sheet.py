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

	def before_submit(self):
		self.warn_about_unreviewed_days()

	def warn_about_unreviewed_days(self):
		"""Chốt công là hành động KHOÁ kỳ — sau đó không sửa được nữa nếu không huỷ bảng. Nên trước
		khi khoá, nói thẳng còn bao nhiêu ô đang mang cờ bất thường (vắng, thiếu giờ, ngày trống,
		chỉ 1 lượt chấm, chấm vào ngày nghỉ). Chỉ CẢNH BÁO, không chặn: có những ngày vắng là đúng
		thật, và người chốt mới là người quyết."""
		from hrms.hr.attendance_review import FLAG_LABEL, get_review_grid

		grid = get_review_grid(
			{
				"month": self.month,
				"year": self.year,
				"company": self.company,
				"include_company_descendants": self.include_company_descendants,
				**({"department": self.department} if self.department else {}),
			}
		)
		counts = {}
		for day_flags in grid["flags"].values():
			for flags in day_flags.values():
				for f in flags:
					counts[f] = counts.get(f, 0) + 1
		if not counts:
			return

		detail = ", ".join(f"{FLAG_LABEL.get(f, f)}: {n}" for f, n in sorted(counts.items()))
		frappe.msgprint(
			_(
				"Bảng công còn {0} ô chưa xử lý ({1}). Chốt xong sẽ KHOÁ kỳ, muốn sửa phải huỷ bảng này."
			).format(sum(counts.values()), detail),
			title=_("Còn ô bất thường"),
			indicator="orange",
		)

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
			row = {
				"employee": r["employee"],
				"employee_name": r["employee_name"],
				"lunch_days": r.get("lunch_days", 0),  # số buổi ăn trưa (nguồn duy nhất: get_sheet_rows)
			}
			for day, sym in r["days"].items():
				row[f"d{int(day):02d}"] = sym
			for cat, val in r["totals"].items():
				if cat in category_field:
					row[category_field[cat]] = val
			self.append("employees", row)
		return len(self.employees)
