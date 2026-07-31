// Copyright (c) 2026, Miyano Việt Nam.
//
// Chặng 3-4 của luồng chấm công: CHỐT CÔNG -> LƯƠNG.
// Nháp thì lấy dữ liệu + quay lại soát; đã chốt thì đi tiếp sang phiếu lương.

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

			// còn nháp thì vẫn sửa được — cho quay lại bước soát cho nhanh
			frm.add_custom_button(__("Soát công"), () => {
				frappe.route_options = {
					month: frm.doc.month,
					year: frm.doc.year,
					company: frm.doc.company,
					department: frm.doc.department,
				};
				frappe.set_route("attendance-review");
			});
		}

		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Tính lương"), () => run_payroll(frm), __("Lương"));
			frm.add_custom_button(
				__("Xem phiếu lương"),
				() => {
					frappe.set_route("List", "Salary Slip", {
						start_date: frm.doc.from_date,
						end_date: frm.doc.to_date,
					});
				},
				__("Lương"),
			);
			frm.page.set_inner_btn_group_as_primary(__("Lương"));
		}

		frm.add_custom_button(__("Bảng công tháng"), () => {
			frappe.route_options = {
				month: frm.doc.month,
				year: frm.doc.year,
				company: frm.doc.company,
				department: frm.doc.department,
			};
			frappe.set_route("query-report", "Monthly Attendance Report");
		});
	},
});

function run_payroll(frm) {
	frm.call({
		doc: frm.doc,
		method: "create_salary_slips",
		freeze: true,
		freeze_message: __("Đang tính lương theo bảng công đã chốt..."),
	}).then((r) => {
		const m = r.message || {};
		const lines = [];
		if (m.created?.length) lines.push(__("Đã tạo mới: <b>{0}</b> phiếu", [m.created.length]));
		if (m.refreshed?.length)
			lines.push(__("Đã lấy lại số công cho: <b>{0}</b> phiếu nháp", [m.refreshed.length]));
		if (m.submitted?.length)
			lines.push(
				__(
					"Bỏ qua <b>{0}</b> phiếu ĐÃ SUBMIT (muốn đổi số đã trả thì phải huỷ phiếu trước): {1}",
					[m.submitted.length, m.submitted.join(", ")],
				),
			);
		if (m.failed?.length)
			lines.push(
				__("<span class='text-danger'>Không tính được {0} phiếu:</span><br>{1}", [
					m.failed.length,
					m.failed.join("<br>"),
				]),
			);

		frappe.msgprint({
			title: __("Kết quả tính lương"),
			message: lines.join("<br>") || __("Không có gì để tính."),
			indicator: m.failed?.length ? "red" : "green",
		});
	});
}
