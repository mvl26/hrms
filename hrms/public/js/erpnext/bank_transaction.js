frappe.ui.form.on("Bank Transaction", {
	get_payment_doctypes: function () {
		return [
			"Payment Entry",
			"Journal Entry",
			"Sales Invoice",
			"Purchase Invoice",
			"Expense Claim",
		];
	},
});
