frappe.views.calendar["Training Event"] = {
	field_map: {
		start: "start_time",
		end: "end_time",
		id: "name",
		title: "event_name",
		allDay: "allDay",
	},
	gantt: true,
	get_events_method: "frappe.desk.calendar.get_events",
};
