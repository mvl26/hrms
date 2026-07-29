// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["Bảng Lương MVL"] = {
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
	],
};
