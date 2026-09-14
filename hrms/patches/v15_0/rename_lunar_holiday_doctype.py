# Copyright (c) 2026, Miyano Việt Nam.
import frappe


def execute():
	"""`Lunar Holiday` -> `Work Calendar Day`.

	`pre_model_sync` để bảng được đổi tên TRƯỚC khi JSON mới sync; chạy sau thì Frappe tạo một
	doctype rỗng mang tên mới và 6 dòng lễ âm đang có nằm lại ở bảng cũ, mất khỏi form.

	Tên cũ đã sai từ lúc bảng nhận thêm lễ riêng của công ty, và sai hẳn khi nó nhận cả ngày làm bù
	— một ngày *làm việc* mà lại nằm trong thứ tên là "Holiday".
	"""
	if frappe.db.exists("DocType", "Lunar Holiday") and not frappe.db.exists("DocType", "Work Calendar Day"):
		frappe.rename_doc("DocType", "Lunar Holiday", "Work Calendar Day", force=True)

	if not frappe.db.table_exists("Work Calendar Day"):
		return

	# rename_doc không đụng tới nội dung dòng con: parenttype/parentfield vẫn trỏ tên cũ, và
	# `Work Calendar Settings.calendar_days` sẽ không thấy dòng nào.
	frappe.db.sql(
		"""
		UPDATE `tabWork Calendar Day`
		SET parenttype = 'Work Calendar Settings', parentfield = 'calendar_days'
		WHERE parentfield = 'lunar_holidays'
		"""
	)
