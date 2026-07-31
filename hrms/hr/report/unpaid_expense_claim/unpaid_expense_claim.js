frappe.query_reports["Unpaid Expense Claim"] = {
	filters: [
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
	],
};
