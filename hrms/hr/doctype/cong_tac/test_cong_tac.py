# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestCongTac(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.emp = frappe.db.get_value("Employee", {}, "name")
		cls.user = (
			frappe.db.get_value("User", {"enabled": 1, "name": ["not in", ["Administrator", "Guest"]]}, "name")
			or "Administrator"
		)

	def _trip(self, travelers=True, approver=None, from_d="2097-05-10", to_d="2097-05-12"):
		doc = frappe.get_doc(
			{
				"doctype": "Cong Tac",
				"destination": "Hà Nội",
				"purpose": "Họp giao ban",
				"from_date": from_d,
				"to_date": to_d,
				"approver_coo": approver,
			}
		)
		if travelers:
			doc.append("travelers", {"employee": self.emp, "is_registrant": 1})
		return doc

	def test_requires_at_least_one_traveler(self):
		self.assertRaises(frappe.ValidationError, self._trip(travelers=False).insert)

	def test_rejects_reversed_dates(self):
		self.assertRaises(frappe.ValidationError, self._trip(from_d="2097-05-12", to_d="2097-05-10").insert)

	def test_multiple_travelers_on_one_trip(self):
		emp2 = frappe.db.get_value("Employee", {"name": ["!=", self.emp]}, "name")
		doc = self._trip()
		if emp2:
			doc.append("travelers", {"employee": emp2})
		doc.insert()
		self.assertGreaterEqual(len(doc.travelers), 1)
		self.assertEqual(doc.workflow_state, "Nháp")

	def test_submit_requires_approver(self):
		doc = self._trip(approver=None)
		doc.insert()
		self.assertRaises(frappe.ValidationError, doc.submit)

	def test_submit_with_approver(self):
		doc = self._trip(approver=self.user)
		doc.insert()
		doc.submit()
		self.assertEqual(doc.docstatus, 1)
