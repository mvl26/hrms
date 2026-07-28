# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import frappe
from frappe.model.workflow import apply_workflow
from frappe.tests.utils import FrappeTestCase

from hrms.patches.v15_0.setup_cong_tac_workflow import ensure_workflow
from hrms.tests.isolation import PerTestRollback


class TestBusinessTrip(PerTestRollback, FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_workflow()  # idempotent — role COO + workflow
		cls.emp = frappe.db.get_value("Employee", {"status": "Active"}, "name")
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
				"doctype": "Business Trip",
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
			filters={
				"reference_type": "Business Trip",
				"reference_name": doc.name,
				"allocated_to": self.user,
			},
		)
		self.assertTrue(todos, "COO phải nhận ToDo khi chuyến được gửi duyệt")

	def test_transitions_are_role_scoped(self):
		# the workflow defines COO-only approval and HR Manager-only decision steps
		wf = frappe.get_doc("Workflow", "Cong Tac Approval")
		# roles-by-action as a set: other installed apps may inject extra roles (e.g. System Manager)
		# into every transition, so assert our intended role is AMONG the allowed, not the sole one.
		roles = {}
		for t in wf.transitions:
			roles.setdefault(t.action, set()).add(t.allowed)
		self.assertIn("COO", roles["Duyệt"])
		self.assertIn("COO", roles["Từ chối"])
		self.assertIn("HR Manager", roles["Ra QĐ"])

	# --- expense claim ---
	def _approved_trip(self):
		doc = self._trip(approver=self.user)
		doc.insert()
		apply_workflow(doc, "Gửi duyệt")
		apply_workflow(doc, "Duyệt")
		apply_workflow(doc, "Ra QĐ")
		return doc

	def test_make_expense_claim_prefills_trip_and_approver(self):
		doc = self._approved_trip()
		claim = doc.make_expense_claim(employee=self.emp)  # returns a prefilled, unsaved dict
		self.assertEqual(claim["doctype"], "Expense Claim")
		self.assertEqual(claim["custom_business_trip"], doc.name)
		self.assertEqual(claim["expense_approver"], self.user)
		self.assertEqual(claim["employee"], self.emp)

	def test_make_expense_claim_blocked_before_qd(self):
		doc = self._trip(approver=self.user)
		doc.insert()
		apply_workflow(doc, "Gửi duyệt")  # still "Chờ COO duyệt"
		self.assertRaises(frappe.ValidationError, doc.make_expense_claim, self.emp)

	def test_make_expense_claim_rejects_non_traveler(self):
		other = frappe.db.get_value("Employee", {"name": ["!=", self.emp]}, "name")
		if not other:
			self.skipTest("need a second employee")
		doc = self._approved_trip()
		self.assertRaises(frappe.ValidationError, doc.make_expense_claim, other)

	def test_expense_claim_hook_writes_back_to_traveler(self):
		from hrms.hr.doctype.business_trip.business_trip import link_claim_to_trip

		doc = self._approved_trip()
		fake_claim = frappe._dict(custom_business_trip=doc.name, employee=self.emp, name="TEST-EC-0001")
		link_claim_to_trip(fake_claim)
		row = next(t for t in frappe.get_doc("Business Trip", doc.name).travelers if t.employee == self.emp)
		self.assertEqual(row.expense_claim, "TEST-EC-0001")

	def test_make_expense_claim_blocked_when_already_linked(self):
		from hrms.hr.doctype.business_trip.business_trip import link_claim_to_trip

		doc = self._approved_trip()
		link_claim_to_trip(
			frappe._dict(custom_business_trip=doc.name, employee=self.emp, name="TEST-EC-0002")
		)
		doc.reload()  # pick up the write-back on the traveler row
		self.assertRaises(frappe.ValidationError, doc.make_expense_claim, self.emp)

	# --- attendance integration ---
	def test_approval_creates_ct_attendance(self):
		doc = self._trip(approver=self.user, from_d="2097-07-01", to_d="2097-07-03")
		doc.insert()
		apply_workflow(doc, "Gửi duyệt")
		apply_workflow(doc, "Duyệt")  # -> COO đã duyệt triggers CT attendance
		atts = frappe.get_all(
			"Attendance",
			filters={
				"employee": self.emp,
				"attendance_date": ["between", ["2097-07-01", "2097-07-03"]],
				"custom_attendance_code": "CT",
			},
			fields=["name", "status"],
		)
		self.assertTrue(atts, "CT attendance phải được tạo khi chuyến được duyệt")
		for a in atts:
			self.assertEqual(a.status, "Work From Home")  # paid working day (payroll-neutral)

	# --- print formats ---
	def test_print_qd_and_giay_di_duong_render(self):
		doc = self._approved_trip()
		frappe.db.set_value("Business Trip", doc.name, "decision_no", "01/QĐ-CT", update_modified=False)

		qd = frappe.get_print("Business Trip", doc.name, print_format="QD Cu Di Cong Tac")
		self.assertIn("QUYẾT ĐỊNH", qd)
		self.assertIn(doc.destination, qd)

		gdd = frappe.get_print("Business Trip", doc.name, print_format="Giay Di Duong")
		self.assertIn("GIẤY ĐI ĐƯỜNG", gdd)
		emp_name = frappe.db.get_value("Employee", self.emp, "employee_name")
		if emp_name:
			self.assertIn(emp_name, gdd)  # giấy đi đường lists each traveler by name
