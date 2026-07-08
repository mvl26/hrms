# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import frappe
from frappe.model.workflow import apply_workflow
from frappe.tests.utils import FrappeTestCase

from hrms.patches.v15_0.setup_cong_tac_workflow import ensure_workflow


class TestCongTac(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_workflow()  # idempotent — role COO + workflow
		cls.emp = frappe.db.get_value("Employee", {}, "name")
		cls.user = frappe.session.user

	def setUp(self):
		# grant the workflow roles to the running user so transitions are permitted (rolled back per test)
		user = frappe.get_doc("User", frappe.session.user)
		have = {r.role for r in user.roles}
		for r in ("COO", "HR User", "HR Manager"):
			if r not in have:
				user.append("roles", {"role": r})
		user.save(ignore_permissions=True)

	def _trip(self, travelers=True, approver=None, from_d="2097-06-01", to_d="2097-06-03"):
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

	# --- schema / validate ---
	def test_requires_at_least_one_traveler(self):
		self.assertRaises(frappe.ValidationError, self._trip(travelers=False).insert)

	def test_rejects_reversed_dates(self):
		self.assertRaises(frappe.ValidationError, self._trip(from_d="2097-06-03", to_d="2097-06-01").insert)

	def test_multiple_travelers_on_one_trip(self):
		emp2 = frappe.db.get_value("Employee", {"name": ["!=", self.emp]}, "name")
		doc = self._trip()
		if emp2:
			doc.append("travelers", {"employee": emp2})
		doc.insert()
		self.assertGreaterEqual(len(doc.travelers), 1)
		self.assertEqual(doc.workflow_state, "Nháp")

	# --- workflow ---
	def test_send_for_approval_requires_approver(self):
		doc = self._trip(approver=None)
		doc.insert()
		self.assertRaises(frappe.ValidationError, apply_workflow, doc, "Gửi duyệt")

	def test_workflow_full_path_states_and_docstatus(self):
		doc = self._trip(approver=self.user)
		doc.insert()
		self.assertEqual(doc.workflow_state, "Nháp")

		apply_workflow(doc, "Gửi duyệt")
		self.assertEqual(doc.workflow_state, "Chờ COO duyệt")
		self.assertEqual(doc.docstatus, 0)

		apply_workflow(doc, "Duyệt")
		self.assertEqual(doc.workflow_state, "COO đã duyệt")
		self.assertEqual(doc.docstatus, 1)  # COO duyệt submits the doc

		apply_workflow(doc, "Ra QĐ")
		self.assertEqual(doc.workflow_state, "Đã ra QĐ")

		apply_workflow(doc, "Hoàn tất")
		self.assertEqual(doc.workflow_state, "Hoàn tất")

	def test_reject_path(self):
		doc = self._trip(approver=self.user)
		doc.insert()
		apply_workflow(doc, "Gửi duyệt")
		apply_workflow(doc, "Từ chối")
		self.assertEqual(doc.workflow_state, "Từ chối")
		self.assertEqual(doc.docstatus, 0)

	def test_assigns_todo_to_coo_on_send_for_approval(self):
		doc = self._trip(approver=self.user)
		doc.insert()
		apply_workflow(doc, "Gửi duyệt")
		todos = frappe.get_all(
			"ToDo",
			filters={"reference_type": "Cong Tac", "reference_name": doc.name, "allocated_to": self.user},
		)
		self.assertTrue(todos, "COO phải nhận ToDo khi chuyến được gửi duyệt")

	def test_transitions_are_role_scoped(self):
		# the workflow defines COO-only approval and HR Manager-only decision steps
		wf = frappe.get_doc("Workflow", "Cong Tac Approval")
		by_action = {t.action: t.allowed for t in wf.transitions}
		self.assertEqual(by_action["Duyệt"], "COO")
		self.assertEqual(by_action["Từ chối"], "COO")
		self.assertEqual(by_action["Ra QĐ"], "HR Manager")
