# Copyright (c) 2026, Miyano Việt Nam.
"""Tham số chuẩn tính lương MVL (Single). Nguồn giá trị khi chạy engine.

Đóng gói mặc định qua `hrms.vn_payroll.setup_mvl.ensure_mvl_defaults` (self-heal mỗi migrate, không
ghi đè giá trị HR đã sửa). `hrms.vn_payroll.settings.config_from_settings` đọc doctype này thành MVLConfig.
"""

import frappe
from frappe import _
from frappe.model.document import Document

# Lưu dạng TỶ LỆ (0,215 = 21,5%) dù nhãn ghi "(%)": gõ nhầm 2 thay vì 0,02 là KPCĐ = 200% lương đóng BHXH.
RATE_FIELDS = ("insurance_company_rate", "insurance_employee_rate", "union_fee_rate")


class MVLPayrollSettings(Document):
	def validate(self):
		for field in RATE_FIELDS:
			value = self.get(field)
			if value is not None and not 0 <= value < 1:
				frappe.throw(
					_("{0} phải là tỷ lệ từ 0 đến dưới 1 (ví dụ 0,02 cho 2%), không phải {1}.").format(
						_(self.meta.get_label(field)), value
					)
				)
