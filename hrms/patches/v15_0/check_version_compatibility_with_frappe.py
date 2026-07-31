import click

import frappe


def execute():
	frappe_v = frappe.get_attr("frappe" + ".__version__")
	hrms_v = frappe.get_attr("hrms" + ".__version__")

	if frappe_v.startswith("14") and hrms_v.startswith("15"):
		message = """
			Miyano HR v15 không tương thích với Frappe & ERPNext `version-14`.
			Bạn đang dùng ERPNext/Frappe `version-14` - hãy nâng Frappe & ERPNext lên `version-15` rồi chạy lại bản cập nhật.\n\t
			Liên hệ bộ phận CNTT (info@miyano.com.vn) nếu cần hỗ trợ.
		"""
		click.secho(message, fg="red")

		frappe.throw(message)  # nosemgrep
