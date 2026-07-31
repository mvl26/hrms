import frappe

from hrms.overrides.company import make_salary_components


def execute():
	if frappe.get_all("Company", limit=1):
		make_salary_components()
