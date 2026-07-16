# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
"""On-demand VN annual-leave entitlement helpers (spec/leave-entitlement-vn.md).

Grants every active employee an annual-leave balance per Điều 113/114 BLLĐ 2019:
12 days/year accrued monthly (stock earned-leave scheduler) plus 1 extra day per
5 full years of seniority, implemented with tiered Leave Policies — no new doctype,
no upstream override.

Deliberately NOT wired to migrate/install hooks: creating Leave Periods, Policies and
Assignments is transactional HR data — run once per year, ask-first on production:

    bench --site <site> execute hrms.setup_vn_leave.create_leave_period --kwargs "{'year': 2026, 'company': 'Miyano'}"
    bench --site <site> execute hrms.setup_vn_leave.assign_annual_leave --kwargs "{'year': 2026, 'company': 'Miyano'}"
"""

from dateutil.relativedelta import relativedelta

import frappe
from frappe.utils import getdate

ANNUAL_LEAVE_TYPE = "Nghỉ phép năm"
BASE_DAYS = 12  # Điều 113 khoản 1(a) — điều kiện làm việc bình thường
SENIORITY_YEARS_PER_EXTRA_DAY = 5  # Điều 114 — +1 ngày cho mỗi đủ 5 năm làm việc


def entitlement_for(employee: str, on_date) -> int:
	"""Annual-leave days for one employee at `on_date`: 12 + floor(full service years / 5)."""
	doj = frappe.db.get_value("Employee", employee, "date_of_joining")
	if not doj:
		return BASE_DAYS
	years = relativedelta(getdate(on_date), getdate(doj)).years
	if years < 0:
		years = 0
	return BASE_DAYS + years // SENIORITY_YEARS_PER_EXTRA_DAY


def create_leave_period(year: int, company: str) -> str:
	"""Create (or return) the calendar-year Leave Period for `company`. Idempotent."""
	year = int(year)
	from_date, to_date = f"{year}-01-01", f"{year}-12-31"
	existing = frappe.db.get_value(
		"Leave Period", {"company": company, "from_date": from_date, "to_date": to_date}, "name"
	)
	if existing:
		return existing
	period = frappe.get_doc(
		{
			"doctype": "Leave Period",
			"from_date": from_date,
			"to_date": to_date,
			"company": company,
			"is_active": 1,
		}
	).insert(ignore_permissions=True)
	return period.name
