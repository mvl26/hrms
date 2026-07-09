// Copyright (c) 2019, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Employee Checkin", {
	refresh: async (frm) => {
		if (frm.doc.offshift) {
			frm.dashboard.clear_headline();
			frm.dashboard.set_headline(
				__(
					"This check-in is outside assigned shift hours and will not be considered for attendance. If a shift is assigned, adjust its time window and Fetch Shift again.",
				),
			);
		}
		if (!frm.doc.__islocal) frm.trigger("add_fetch_shift_button");

		const allow_geolocation_tracking = await frappe.db.get_single_value(
			"HR Settings",
			"allow_geolocation_tracking",
		);

		if (!allow_geolocation_tracking) {
			hide_field(["fetch_geolocation", "latitude", "longitude", "geolocation"]);
			return;
		}

		// Overlay the applicable geofence circle so HR sees the check-in point in/out of the allowed area.
		overlay_geofence(frm);
	},

	fetch_geolocation: (frm) => {
		hrms.fetch_geolocation(frm);
	},

	add_fetch_shift_button(frm) {
		if (frm.doc.attendace) return;
		frm.add_custom_button(__("Fetch Shift"), function () {
			frappe.call({
				method: "fetch_shift",
				doc: frm.doc,
				freeze: true,
				freeze_message: __("Fetching Shift"),
				callback: function () {
					if (frm.doc.shift) {
						frappe.show_alert({
							message: __("Shift has been successfully updated to {0}.", [
								frm.doc.shift,
							]),
							indicator: "green",
						});
						frm.dirty();
						frm.save();
					} else {
						frappe.show_alert({
							message: __("No valid shift found for log time"),
							indicator: "orange",
						});
					}
				},
			});
		});
	},
});

// Fetch the employee's current geofence and draw a read-only circle on the check-in map.
// Polls briefly for the Leaflet map instance created by the Geolocation control.
async function overlay_geofence(frm, attempts = 0) {
	if (frm.doc.__islocal || !frm.doc.employee) return;

	const field = frm.get_field("geolocation");
	const map = field && field.map;
	if (!map) {
		if (attempts < 20) setTimeout(() => overlay_geofence(frm, attempts + 1), 250);
		return;
	}
	if (map._geofence_overlaid) return;
	map._geofence_overlaid = true;

	const geofence = await frappe.xcall(
		"hrms.hr.doctype.employee_checkin.employee_checkin.get_checkin_geofence",
		{ employee: frm.doc.employee },
	);
	if (!(geofence && geofence.latitude && geofence.longitude && geofence.checkin_radius)) return;

	const center = [geofence.latitude, geofence.longitude];
	const circle = L.circle(center, {
		radius: geofence.checkin_radius,
		color: frappe.ui.color.get("blue"),
		weight: 1,
		fillOpacity: 0.08,
	}).addTo(map);
	circle.bindTooltip(
		__("Allowed area: {0} ({1} m)", [geofence.location_name, geofence.checkin_radius]),
	);

	// Show both the geofence and the check-in point.
	const bounds = circle.getBounds();
	if (frm.doc.latitude && frm.doc.longitude) bounds.extend([frm.doc.latitude, frm.doc.longitude]);
	try {
		map.fitBounds(bounds, { padding: [30, 30], maxZoom: 17 });
	} catch (e) {
		// ignore fit errors on degenerate bounds
	}
}
