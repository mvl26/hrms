# Copyright (c) 2026, Miyano Việt Nam.
import frappe
from frappe import _
from frappe.utils.dashboard import cache_source

from hrms.hr.working_hours import get_hours_by_department, prepare_filters


@frappe.whitelist()
@cache_source
def get_data(
	chart_name: str | None = None,
	chart: str | dict | None = None,
	no_cache: bool | int | None = None,
	filters: str | dict | None = None,
	from_date: str | None = None,
	to_date: str | None = None,
	timespan: str | None = None,
	time_interval: str | None = None,
	heatmap_year: str | int | None = None,
) -> dict[str, list]:
	filters = frappe.parse_json(filters) if filters else {}
	filters = prepare_filters(filters)
	data = get_hours_by_department(filters)
	return {
		"labels": data["labels"],
		"datasets": [{"name": _("Working Hours"), "values": data["values"]}],
	}
