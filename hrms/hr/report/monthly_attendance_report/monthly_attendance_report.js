// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// For license information, please see license.txt

frappe.query_reports["Monthly Attendance Report"] = {
	filters: [
		{
			fieldname: "month",
			label: __("Tháng"),
			fieldtype: "Select",
			options: [
				{ value: 1, label: __("Jan") },
				{ value: 2, label: __("Feb") },
				{ value: 3, label: __("Mar") },
				{ value: 4, label: __("Apr") },
				{ value: 5, label: __("May") },
				{ value: 6, label: __("Jun") },
				{ value: 7, label: __("Jul") },
				{ value: 8, label: __("Aug") },
				{ value: 9, label: __("Sep") },
				{ value: 10, label: __("Oct") },
				{ value: 11, label: __("Nov") },
				{ value: 12, label: __("Dec") },
			],
			default: frappe.datetime.str_to_obj(frappe.datetime.get_today()).getMonth() + 1,
			reqd: 1,
		},
		{
			fieldname: "year",
			label: __("Năm"),
			fieldtype: "Select",
			reqd: 1,
		},
		{
			fieldname: "company",
			label: __("Công ty"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "include_company_descendants",
			label: __("Gồm công ty con"),
			fieldtype: "Check",
			default: 1,
		},
	],

	onload: function (report) {
		// bảng màu do server định nghĩa (một nguồn duy nhất) — formatter chỉ tra, không tự phân loại
		frappe.call({
			method: "hrms.hr.report.monthly_attendance_report.monthly_attendance_report.get_color_map",
			callback: function (r) {
				frappe.query_reports["Monthly Attendance Report"]._state_styles = r.message || {};
			},
		});
		return frappe.call({
			method: "hrms.hr.report.monthly_attendance_sheet.monthly_attendance_sheet.get_attendance_years",
			callback: function (r) {
				const year_filter = report.get_filter("year");
				year_filter.df.options = r.message;
				year_filter.df.default = r.message.split("\n")[0];
				year_filter.refresh();
				year_filter.set_input(year_filter.df.default);
			},
		});
	},

	// Tô nền mỗi ô mã công theo state màu server đã tính sẵn (`_state_<day>`). Thuần hiển thị.
	formatter: function (value, row, column, data, default_formatter) {
		const html = default_formatter(value, row, column, data);
		const fieldname = (column && column.fieldname) || "";
		if (!fieldname.startsWith("day_")) return html;

		const day = fieldname.slice(4);
		const state = data && data["_state_" + day];
		const styles = frappe.query_reports["Monthly Attendance Report"]._state_styles;
		if (!state || !styles || !styles[state]) return html;

		const s = styles[state];
		const dark = is_dark_theme();
		const bg = dark ? s.bg_dark : s.bg;
		const fg = dark ? s.fg_dark : s.fg;
		const text = value == null ? "" : frappe.utils.escape_html(String(value));
		// negative margin để nền phủ kín ô (bù padding mặc định của datatable)
		return `<div style="background:${bg};color:${fg};font-weight:600;margin:-5px -8px;padding:5px 8px;text-align:center;">${text}</div>`;
	},
};

function is_dark_theme() {
	const t = document.documentElement.getAttribute("data-theme");
	if (t === "dark") return true;
	if (t === "light") return false;
	// "automatic" hoặc không đặt → theo thiết lập hệ điều hành
	return !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
}
