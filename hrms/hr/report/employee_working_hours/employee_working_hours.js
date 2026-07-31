// Copyright (c) 2026, Miyano Việt Nam.
frappe.query_reports["Employee Working Hours"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.month_start(),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.month_end(),
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "view",
			label: __("View"),
			fieldtype: "Select",
			options: [
				{ value: "Summary", label: __("Summary") },
				{ value: "Detail", label: __("Detail") },
			],
			default: "Summary",
			reqd: 1,
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
		},
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
		{
			fieldname: "shift",
			label: __("Shift Type"),
			fieldtype: "Link",
			options: "Shift Type",
		},
		{
			fieldname: "include_inactive",
			label: __("Include Employees Who Left"),
			fieldtype: "Check",
			default: 0,
		},
	],
	formatter: (value, row, column, data, default_formatter) => {
		value = default_formatter(value, row, column, data);
		// nhân viên không có giờ nào trong kỳ — tô xám để lọt vào mắt ngay
		if (column.fieldname === "employee_name" && data && data.days_counted === 0) {
			value = `<span style='color: var(--text-muted)'>${value}</span>`;
		}
		return value;
	},
};
