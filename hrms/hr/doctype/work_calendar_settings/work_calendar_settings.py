# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt
"""Nguồn sự thật cho lịch làm việc — Holiday List chỉ là kết quả sinh ra từ đây.

Vì sao cần: ngày nghỉ hàng tuần BẮT BUỘC phải nằm trong Holiday List (payroll, auto-attendance và
cách tính ngày phép đều chỉ đọc Holiday List). Nhưng nếu chính sách chỉ tồn tại dưới dạng tham số
truyền tay lúc chạy generator thì chạy lại mà quên tham số là lịch âm thầm đổi → lương đổi theo mà
không ai biết. Doctype này giữ chính sách lại một chỗ, có version, HR sửa được trên Desk.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class WorkCalendarSettings(Document):
	def validate(self):
		self.validate_lunar_years()

	def validate_lunar_years(self):
		"""Ngày lễ âm phải nằm đúng trong năm đã khai — sai năm thì sinh lịch sẽ hụt ngày."""
		for row in self.lunar_holidays:
			if row.holiday_date and row.year and frappe.utils.getdate(row.holiday_date).year != int(row.year):
				frappe.throw(
					_("Dòng {0}: ngày {1} không thuộc năm {2}.").format(
						row.idx, frappe.utils.formatdate(row.holiday_date), row.year
					)
				)

	def get_weekly_off_days(self) -> tuple[str, ...]:
		"""Các thứ trong tuần công ty nghỉ, vd ('Saturday', 'Sunday')."""
		return tuple(row.day for row in self.weekly_off_days if row.day)

	def get_lunar_holidays(self, year: int) -> dict[str, str]:
		"""{"YYYY-MM-DD": "Tên lễ"} của riêng `year` — dạng generator nhận."""
		return {
			str(frappe.utils.getdate(row.holiday_date)): row.description
			for row in self.lunar_holidays
			if row.holiday_date and int(row.year) == int(year)
		}


@frappe.whitelist()
def generate_holiday_list(year=None, company=None) -> str:
	"""Sinh / cập nhật Holiday List của `year` theo đúng chính sách đang lưu. Trả tên list.

	Idempotent: chạy lại không nhân đôi ngày. Đây là con đường DUY NHẤT nên dùng để tạo lịch,
	vì nó luôn kéo chính sách từ một chỗ.
	"""
	settings = frappe.get_single("Work Calendar Settings")
	year = int(year or settings.generate_for_year or frappe.utils.now_datetime().year)
	company = company or settings.company
	if not company:
		frappe.throw(_("Hãy chọn Công ty trong Cấu hình lịch làm việc trước."))

	# import tại chỗ: generator là module cấp app, tránh vòng import khi doctype được nạp sớm
	from hrms.setup_vn_holiday import create_vn_holiday_list

	name = create_vn_holiday_list(
		year,
		company,
		weekly_off_days=settings.get_weekly_off_days(),
		extra_holidays=settings.get_lunar_holidays(year),
	)
	frappe.msgprint(_("Đã sinh / cập nhật {0}.").format(name), alert=True)
	return name
