// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// For license information, please see license.txt

frappe.ui.form.on("Monthly Attendance Sheet", {
	refresh(frm) {
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Lấy dữ liệu chấm công"), () => {
				frm.call({
					doc: frm.doc,
					method: "populate_from_attendance",
					freeze: true,
					freeze_message: __("Đang lấy dữ liệu chấm công..."),
				}).then((r) => {
					frm.refresh_field("employees");
					frappe.show_alert({
						message: __("Đã lấy {0} nhân viên vào bảng công.", [r.message || 0]),
						indicator: "green",
					});
				});
			});
		}
	},
});
