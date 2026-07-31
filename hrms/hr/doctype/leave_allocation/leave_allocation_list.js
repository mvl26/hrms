// render
frappe.listview_settings["Leave Allocation"] = {
	get_indicator: function (doc) {
		if (doc.status === "Expired") {
			return [__("Expired"), "gray", "expired, =, 1"];
		}
	},
};
