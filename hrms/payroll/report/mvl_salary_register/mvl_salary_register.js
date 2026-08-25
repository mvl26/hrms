// Copyright (c) 2026, Miyano Việt Nam.
frappe.query_reports["MVL Salary Register"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Công ty"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "month",
			label: __("Tháng"),
			fieldtype: "Select",
			options: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map((m) => ({
				value: m,
				label: String(m),
			})),
			default: new Date().getMonth() + 1,
			reqd: 1,
		},
		{
			fieldname: "year",
			label: __("Năm"),
			fieldtype: "Int",
			default: new Date().getFullYear(),
			reqd: 1,
		},
		{
			fieldname: "department",
			label: __("Phòng ban"),
			fieldtype: "Link",
			options: "Department",
		},
		{
			// Mặc định TẮT: bảng lương là chứng từ trình ký, không trộn phiếu chưa chốt vào.
			// Bật để soát số trước khi duyệt — bản Excel xuất ra sẽ tự ghi rõ là có phiếu nháp.
			fieldname: "include_drafts",
			label: __("Gồm cả phiếu nháp"),
			fieldtype: "Check",
			default: 0,
		},
	],

	onload: function (report) {
		// Export mặc định của Frappe dựng file qua `make_xlsx()`: ra lưới trần, không tiêu đề công
		// ty, không dòng tổng in đậm, không chỗ ký. Bảng lương phải KÝ được nên đi đường riêng.
		//
		// CẨN THẬN: `frappe.query_report` là MỘT instance dùng chung cho MỌI query report —
		// `load_report()` chỉ đổi `report_name` chứ không dựng lại object. Ghi đè thẳng
		// `export_report` vì thế rò sang mọi báo cáo khác trong cùng phiên. Nên phải bọc MỘT LẦN
		// và luôn kiểm tên báo cáo lúc bấm (đúng bẫy đã dính với bảng chấm công, 2026-08-03).
		if (!report._mvl_export_patched) {
			report._mvl_export_patched = true;
			const fallback = report.export_report.bind(report); // bản gốc trên prototype
			report.export_report = function () {
				if (this.report_name === "MVL Salary Register")
					return mvl_salary_export_dialog(this);
				return fallback();
			};
		}
	},
};

// Tên hàm ĐẶT RIÊNG, không trùng `vn_export_dialog` của bảng chấm công: cả hai file đều được
// `frappe.dom.eval` chèn vào phạm vi TOÀN CỤC, trùng tên là file nạp sau đè file nạp trước và một
// trong hai báo cáo xuất nhầm biểu mẫu của báo cáo kia.
function mvl_salary_export_dialog(report) {
	const d = new frappe.ui.Dialog({
		title: __("Xuất bảng lương"),
		fields: [
			{
				fieldname: "file_format",
				label: __("Định dạng"),
				fieldtype: "Select",
				options: [
					{ value: "Excel", label: __("Excel — mẫu Miyano, có khối ký") },
					{ value: "CSV", label: __("CSV — dữ liệu thô") },
				],
				default: "Excel",
				reqd: 1,
			},
			{
				fieldtype: "Section Break",
				label: __("Khối trình ký"),
				depends_on: "eval:doc.file_format=='Excel'",
			},
			{
				fieldname: "prepared_by",
				label: __("Người lập"),
				fieldtype: "Data",
				description: __("Để trống = tên người đang đăng nhập"),
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "approved_by",
				label: __("Người duyệt"),
				fieldtype: "Data",
				description: __("Để trống = chỉ in chức danh, ký tên tay"),
			},
		],
		primary_action_label: __("Tải về"),
		primary_action: ({ file_format, prepared_by, approved_by }) => {
			d.hide();
			report.make_access_log("Export", file_format);

			const filters = report.get_filter_values(true);
			const visible_idx = report.datatable?.bodyRenderer.visibleRowIndices || [];

			if (file_format === "Excel") {
				open_url_post(frappe.request.url, {
					cmd: "hrms.vn_payroll.salary_xlsx.download",
					filters,
					visible_idx,
					prepared_by: prepared_by || "",
					approved_by: approved_by || "",
				});
			} else {
				open_url_post(frappe.request.url, {
					cmd: "frappe.desk.query_report.export_query",
					report_name: report.report_name,
					file_format_type: "CSV",
					filters,
					visible_idx,
				});
			}
		},
	});
	d.show();
}
