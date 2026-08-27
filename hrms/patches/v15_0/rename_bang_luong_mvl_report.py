import frappe


def execute():
	"""Report `Bảng Lương MVL` -> `MVL Salary Register`.

	Tên cũ có DẤU TIẾNG VIỆT nên Frappe suy đường dẫn bằng `scrub(name)` ra
	`hrms/payroll/report/bảng_lương_mvl/`, trong khi thư mục trên đĩa là ASCII → báo cáo KHÔNG
	import được (`ModuleNotFoundError`) và file .js cũng không nạp: mở trên Desk là lỗi, chưa
	từng chạy được. Đổi sang tên ASCII khớp thư mục `mvl_salary_register`; nhãn tiếng Việt giữ
	qua `translations/vi.csv`, đúng lối đã dùng cho `Monthly Attendance Report`.

	pre_model_sync để bản ghi được đổi tên TRƯỚC khi thư mục report sync ra một bản ghi mới.
	"""
	if frappe.db.exists("Report", "Bảng Lương MVL") and not frappe.db.exists("Report", "MVL Salary Register"):
		frappe.rename_doc("Report", "Bảng Lương MVL", "MVL Salary Register", force=True)
