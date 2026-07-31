/* eslint-disable */

frappe.query_reports["Salary Payments via ECS"] = $.extend(
	{},
	hrms.salary_slip_deductions_report_filters,
);

frappe.query_reports["Salary Payments via ECS"]["filters"].push({
	fieldname: "type",
	label: __("Type"),
	fieldtype: "Select",
	options: ["", "Bank", "Cash", "Cheque"],
});
