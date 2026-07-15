// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// For license information, please see license.txt

frappe.ui.form.on("Business Trip", {
	refresh(frm) {
		if (["Đã ra QĐ", "Hoàn tất"].includes(frm.doc.workflow_state)) {
			frm.add_custom_button(__("Tạo đề nghị thanh toán"), () => {
				frm.call({ doc: frm.doc, method: "make_expense_claim", freeze: true }).then((r) => {
					if (r.message) {
						const doc = frappe.model.sync(r.message)[0];
						frappe.set_route("Form", doc.doctype, doc.name);
					}
				});
			});
		}
	},
});
