frappe.ui.form.on("Attendance Request", {
	refresh(frm) {
		frm.trigger("show_attendance_warnings");
	},

	// Miyano: nửa ngày chỉ dành cho yêu cầu ĐÚNG MỘT ngày; ngày nửa buổi chính là ngày đó (ô Half
	// Day Date đã ẩn, server tự điền). Đổi sang nhiều ngày thì bỏ tick, để ô Half Day đang ẩn không
	// mang theo một lựa chọn người dùng không còn nhìn thấy.
	from_date(frm) {
		frm.trigger("sync_half_day");
	},

	to_date(frm) {
		frm.trigger("sync_half_day");
	},

	half_day(frm) {
		frm.trigger("sync_half_day");
	},

	sync_half_day(frm) {
		const one_day = frm.doc.from_date && frm.doc.from_date === frm.doc.to_date;
		if (frm.doc.half_day && !one_day) {
			frm.set_value("half_day", 0);
			return;
		}
		frm.set_value("half_day_date", frm.doc.half_day ? frm.doc.from_date : null);
	},

	show_attendance_warnings(frm) {
		if (!frm.is_new() && frm.doc.docstatus === 0) {
			frm.dashboard.clear_headline();

			frm.call("get_attendance_warnings").then((r) => {
				if (r.message?.length) {
					frm.dashboard.reset();
					frm.dashboard.add_section(
						frappe.render_template("attendance_warnings", {
							warnings: r.message || [],
						}),
						__("Attendance Warnings"),
					);
					frm.dashboard.show();
				}
			});
		}
	},
});
