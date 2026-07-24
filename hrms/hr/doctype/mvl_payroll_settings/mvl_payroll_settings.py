# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt
"""Tham số chuẩn tính lương MVL (Single). Nguồn giá trị khi chạy engine.

Đóng gói mặc định qua `hrms.vn_payroll.setup_mvl.ensure_mvl_defaults` (self-heal mỗi migrate, không
ghi đè giá trị HR đã sửa). `hrms.vn_payroll.settings.config_from_settings` đọc doctype này thành MVLConfig.
"""

from frappe.model.document import Document


class MVLPayrollSettings(Document):
	pass
