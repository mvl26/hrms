# Copyright (c) 2026, Miyano Việt Nam.
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

from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import (
	BUCKET_MARRIAGE,
	TOTAL_PAID,
)

# Nhóm của mã công → cột tổng trên bảng. Bảng chỉ mang MỘT con số công: "Tổng công" = số ngày công
# ty trả lương, lấy đúng cột của báo cáo → một kỳ không thể có hai con số công. Phần đi làm thực tế
# không có cột riêng ở đây; cần tách bạch thì xem mã công từng ngày, hoặc cột Công của báo cáo.
#
# Ở module level (không phải biến cục bộ trong `populate_from_attendance`) để
# `hrms/hr/tests/test_attendance_category.py` soi được: nhóm nào thiếu cột ở đây là số ngày của
# nhóm đó rơi khỏi bảng đã chốt, im lặng.
CATEGORY_FIELD = {
	TOTAL_PAID: "total_paid_days",
	"Phép": "annual_leave",
	# KH (nghỉ kết hôn) tách khỏi "Việc riêng" — HR chốt 2026-08-04. Phải có mặt ở ĐÂY nữa,
	# không thì ngày KH rơi khỏi bảng: bảng chỉ ghi những loại có trong bảng ánh xạ này.
	BUCKET_MARRIAGE: "marriage_leave",
	"Việc riêng": "personal_leave",
	"Ốm": "sick_leave",
	"Thai sản": "maternity_leave",
	"Tai nạn LĐ": "work_accident_leave",
	"Nghỉ bù": "comp_off",
	"Không lương": "unpaid_leave",
	"Vắng": "absent",
	"Nghỉ lễ": "public_holiday",
}


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
		from hrms.hr.attendance_review import flag_labels, get_review_grid

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

		labels = flag_labels()
		detail = ", ".join(f"{labels.get(f, f)}: {n}" for f, n in sorted(counts.items()))
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
	def create_salary_slips(self) -> dict:
		"""Chặng cuối của luồng: từ bảng đã chốt sang phiếu lương.

		Lấy đúng danh sách nhân viên trong bảng (không quét lại DB — bảng đã chốt mới là bản quyền
		lực), rồi với từng người:

		- chưa có phiếu → tạo mới (cổng `sheet_gate` sẽ đối soát ngay lúc validate);
		- có phiếu NHÁP → lưu lại để nó lấy lại số công mới nhất ("fetch data nếu có thay đổi");
		- có phiếu ĐÃ SUBMIT → không đụng, chỉ báo lại. Sửa số đã trả là việc phải làm có chủ đích,
		  không thể là tác dụng phụ của một nút bấm.
		"""
		if self.docstatus != 1:
			frappe.throw(_("Phải chốt công (submit) trước khi tính lương."))

		created, refreshed, submitted, failed = [], [], [], []
		for row in self.employees:
			existing = frappe.db.get_value(
				"Salary Slip",
				{
					"employee": row.employee,
					"start_date": self.from_date,
					"end_date": self.to_date,
					"docstatus": ["<", 2],
				},
				["name", "docstatus"],
				as_dict=True,
			)
			try:
				if existing and existing.docstatus == 1:
					submitted.append(existing.name)
					continue
				if existing:
					doc = frappe.get_doc("Salary Slip", existing.name)
					doc.save()  # validate chạy lại → số công cập nhật theo bảng vừa chốt
					refreshed.append(doc.name)
					continue
				doc = frappe.new_doc("Salary Slip")
				doc.employee = row.employee
				doc.company = self.company
				doc.start_date = self.from_date
				doc.end_date = self.to_date
				doc.insert()
				created.append(doc.name)
			except Exception as e:
				failed.append(f"{row.employee_name or row.employee}: {str(e)[:200]}")

		return {
			"created": created,
			"refreshed": refreshed,
			"submitted": submitted,
			"failed": failed,
		}

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
				if cat in CATEGORY_FIELD:
					row[CATEGORY_FIELD[cat]] = val
			self.append("employees", row)
		return len(self.employees)


@frappe.whitelist()
def get_or_create_sheet(
	month: int | str, year: int | str, company: str, department: str | None = None
) -> str:
	"""Mở bảng chốt công của kỳ này, tạo mới nếu chưa có — dùng cho nút "Chốt công" trên báo cáo.

	Không tự submit: chốt công là hành động khoá kỳ, phải do người dùng bấm sau khi nhìn dữ liệu."""
	filters = {
		"company": company,
		"month": str(month),
		"year": cint(year),
		"docstatus": ["<", 2],
		"department": department if department else ["is", "not set"],
	}
	existing = frappe.db.get_value("Monthly Attendance Sheet", filters, "name")
	if existing:
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "Monthly Attendance Sheet",
			"company": company,
			"month": str(month),
			"year": cint(year),
			"department": department or None,
		}
	)
	doc.insert()
	doc.populate_from_attendance()
	doc.save()
	return doc.name
