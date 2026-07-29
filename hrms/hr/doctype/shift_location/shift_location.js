// Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Shift Location", {
	refresh: async (frm) => {
		const allow_geolocation_tracking = await frappe.db.get_single_value(
			"HR Settings",
			"allow_geolocation_tracking",
		);

		if (!allow_geolocation_tracking) {
			hide_field([
				"checkin_radius",
				"fetch_geolocation",
				"latitude",
				"longitude",
				"geolocation",
			]);
		} else {
			// Let the admin click the map to place the location; the geofence circle is drawn
			// server-side (set_geolocation emits a circle feature for the checkin_radius).
			bind_map_click(frm);
		}

		if (!frm.doc.__islocal)
			hrms.add_shift_tools_button_to_form(frm, {
				action: "Assign Shift",
				shift_location: frm.doc.name,
			});
	},

	fetch_geolocation: (frm) => {
		hrms.fetch_geolocation(frm);
	},

	checkin_radius: (frm) => regenerate_geofence(frm),
	latitude: (frm) => regenerate_geofence(frm),
	longitude: (frm) => regenerate_geofence(frm),
});

// Rebuild the geolocation (point + radius circle) from the current latitude/longitude/checkin_radius
// and re-render the map. Guarded against re-entrancy from the field change handlers.
async function regenerate_geofence(frm) {
	if (frm._regenerating_geofence) return;
	if (!(frm.doc.latitude && frm.doc.longitude)) return;

	frm._regenerating_geofence = true;
	try {
		await frm.call("set_geolocation");
		frm.refresh_field("geolocation");
		bind_map_click(frm); // the control recreates its map on refresh — rebind the click
	} finally {
		frm._regenerating_geofence = false;
	}
}

// Poll for the Leaflet map instance the Geolocation control creates on render, then bind a click
// handler that sets latitude/longitude and redraws the circle. Degrades gracefully if unavailable.
function bind_map_click(frm, attempts = 0) {
	const field = frm.get_field("geolocation");
	const map = field && field.map;

	if (!map) {
		if (attempts < 20) setTimeout(() => bind_map_click(frm, attempts + 1), 250);
		return;
	}
	if (map._shift_location_click_bound) return;
	map._shift_location_click_bound = true;

	map.on("click", async (e) => {
		frm._regenerating_geofence = true;
		await frm.set_value({
			latitude: flt(e.latlng.lat, 5),
			longitude: flt(e.latlng.lng, 5),
		});
		frm._regenerating_geofence = false;
		await regenerate_geofence(frm);
	});
}
