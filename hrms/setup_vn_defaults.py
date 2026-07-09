"""Idempotent default setup for this VN HRMS fork.

Single entry point `ensure_defaults()`, wired to `after_install` and `after_migrate` (see hooks.py).
It is intentionally narrow and safe to run on every migrate:

  - Self-heals the Công Tác approval workflow + `COO` role by delegating to the existing idempotent
    `ensure_workflow()` (previously only ran once via the patch log, so a deleted workflow/role stayed
    gone until re-patched; now it is re-ensured on every migrate).
  - Verifies the fixture-backed master data (VN leave types, attendance codes, custom fields) is
    present and logs a warning if any is missing. It does NOT recreate fixture data — the `fixtures`
    mechanism owns that (and re-syncs it every migrate); recreating here would risk partial/dup rows.

It never mutates HR Settings (geolocation tracking stays off by default), seeds no sample master data,
and touches no payroll/attendance transactional data.
"""

import json

import frappe

from hrms.patches.v15_0.setup_cong_tac_workflow import ensure_workflow

# doctype -> fixture file basename (under hrms/fixtures/), both keyed by "name"
FIXTURE_DOCTYPES = {
	"Leave Type": "leave_type",
	"Attendance Code": "attendance_code",
	"Custom Field": "custom_field",
}


def ensure_defaults():
	"""Idempotent post-install / post-migrate setup. Returns a small summary dict for testability."""
	ensure_workflow()

	missing = check_fixture_master_data()
	if missing:
		frappe.logger("hrms").warning(
			f"hrms.setup_vn_defaults.ensure_defaults: fixture master data missing "
			f"(fixtures may not have synced): {missing}"
		)

	return {
		"workflow": bool(frappe.db.exists("Workflow", "Cong Tac Approval")),
		"coo_role": bool(frappe.db.exists("Role", "COO")),
		"missing": missing,
	}


def check_fixture_master_data() -> dict:
	"""Return {doctype: [absent names]} for fixture-backed master data not present on the site."""
	missing = {}
	for doctype, fixture in FIXTURE_DOCTYPES.items():
		absent = [name for name in _fixture_names(fixture) if not frappe.db.exists(doctype, name)]
		if absent:
			missing[doctype] = absent
	return missing


def _fixture_names(fixture: str) -> list[str]:
	path = frappe.get_app_path("hrms", "fixtures", f"{fixture}.json")
	with open(path) as f:
		return [record["name"] for record in json.load(f) if record.get("name")]
