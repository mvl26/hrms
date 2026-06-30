# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

import frappe
from frappe import _
from frappe.utils.dashboard import cache_source

from hrms.hr.working_hours import get_hours_by_week, prepare_filters


@frappe.whitelist()
@cache_source
def get_data(
	chart_name=None,
	chart=None,
	no_cache=None,
	filters=None,
	from_date=None,
	to_date=None,
	timespan=None,
	time_interval=None,
	heatmap_year=None,
) -> dict[str, list]:
	filters = frappe.parse_json(filters) if filters else {}
	filters = prepare_filters(filters)
	data = get_hours_by_week(filters)
	return {
		"labels": data["labels"],
		"datasets": [{"name": _("Working Hours"), "values": data["values"]}],
	}
