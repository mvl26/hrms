// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Work Calendar Settings", {
	refresh(frm) {
		if (!frm.doc.generate_for_year) {
			frm.set_value("generate_for_year", new Date().getFullYear());
		}
	},

	// Sinh lịch phải đi qua server để chính sách và Holiday List không bao giờ lệch nhau.
	generate_button(frm) {
		frm.save().then(() => {
			frappe.call({
				method: "hrms.hr.doctype.work_calendar_settings.work_calendar_settings.generate_holiday_list",
				args: { year: frm.doc.generate_for_year, company: frm.doc.company },
				freeze: true,
				freeze_message: __("Đang sinh Holiday List..."),
				callback(r) {
					if (!r.message) return;
					frappe.msgprint({
						title: __("Xong"),
						indicator: "green",
						message: __("Đã sinh {0}. Mở để kiểm tra ngày nghỉ tuần và ngày lễ.", [
							`<a href="/app/holiday-list/${encodeURIComponent(
								r.message,
							)}">${frappe.utils.escape_html(r.message)}</a>`,
						]),
					});
				},
			});
		});
	},
});
