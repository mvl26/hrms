# Copyright (c) 2026, Miyano Việt Nam.
import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.setup_vn_defaults import check_fixture_master_data, ensure_defaults
from hrms.tests.isolation import PerTestRollback


class TestSetupVnDefaults(PerTestRollback, FrappeTestCase):
	def test_ensure_defaults_creates_workflow_and_role(self):
		# Remove the workflow so ensure_defaults() has to recreate it (self-healing path)
		frappe.db.delete("Workflow", {"name": "Cong Tac Approval"})
		self.assertFalse(frappe.db.exists("Workflow", "Cong Tac Approval"))

		summary = ensure_defaults()
		self.assertTrue(frappe.db.exists("Workflow", "Cong Tac Approval"))
		self.assertTrue(frappe.db.exists("Role", "COO"))
		self.assertTrue(summary["workflow"])
		self.assertTrue(summary["coo_role"])

	def test_ensure_defaults_is_idempotent(self):
		ensure_defaults()
		ensure_defaults()  # must not raise or duplicate
		self.assertEqual(frappe.db.count("Workflow", {"name": "Cong Tac Approval"}), 1)
		self.assertEqual(frappe.db.count("Role", {"name": "COO"}), 1)

	def test_fixture_master_data_present(self):
		# All fork fixtures are synced on this site → nothing missing
		self.assertEqual(check_fixture_master_data(), {})

	def test_ensure_defaults_is_payroll_neutral(self):
		before = {dt: frappe.db.count(dt) for dt in ("Attendance", "Salary Slip", "Employee Checkin")}
		ensure_defaults()
		after = {dt: frappe.db.count(dt) for dt in ("Attendance", "Salary Slip", "Employee Checkin")}
		self.assertEqual(before, after)

	def test_hooks_fixture_filters_match_fixture_files(self):
		# A fixtures `name in [...]` filter must list exactly the records in its JSON file, else a
		# `bench export-fixtures` would silently drop the records missing from the filter.
		import hrms.hooks as hooks
		from hrms.setup_vn_defaults import _fixture_names

		for entry in hooks.fixtures:
			if not isinstance(entry, dict):
				continue
			name_filter = (entry.get("filters") or {}).get("name")
			if not (isinstance(name_filter, list | tuple) and name_filter and name_filter[0] == "in"):
				continue
			filtered = set(name_filter[1])
			file_names = set(_fixture_names(frappe.scrub(entry["dt"])))
			self.assertEqual(
				filtered,
				file_names,
				f"hooks.py fixtures filter for {entry['dt']} is out of sync with its fixture file",
			)

	def test_reports_leave_types_without_any_attendance_code(self):
		"""Loại nghỉ chưa gắn mã phải lộ ra lúc migrate, không đợi tới lúc in bảng công."""
		from hrms.setup_vn_defaults import leave_types_without_code

		self.assertEqual(leave_types_without_code(), [], "tiền đề: site đang sạch")

		frappe.get_doc(
			{"doctype": "Leave Type", "leave_type_name": "Nghỉ thử chưa gắn mã", "is_lwp": 0}
		).insert(ignore_permissions=True)

		self.assertIn("Nghỉ thử chưa gắn mã", leave_types_without_code())


class TestSeedNeverOverwritesHrChoices(PerTestRollback, FrappeTestCase):
	"""Mã công + Loại nghỉ là dữ liệu GIEO MỘT LẦN, không phải fixture.

	Sự cố 2026-10-29: HR gắn `P` sang một loại nghỉ phép năm có lương của họ, rồi mỗi lần
	`bench migrate` thì `P` lại về "Nghỉ phép năm" mặc định. Lý do: `sync_fixtures` nạp MỌI file
	JSON trong `hrms/fixtures/` theo kiểu xoá-rồi-chèn (`import_doc(force=True)`), nên nó ghi đè
	từng mã công và dựng lại từng loại nghỉ mặc định. Công xoay quanh mã công — mã đã có chủ thì
	app không được đổi chủ, cũng không được đẻ thêm loại nghỉ cho nó."""

	OWN_TYPE = "Phép năm có lương (HR tự tạo)"

	def setUp(self):
		frappe.get_doc({"doctype": "Leave Type", "leave_type_name": self.OWN_TYPE, "is_lwp": 0}).insert(
			ignore_permissions=True
		)
		# đổi chủ thẳng ở nguồn sự thật, như HR làm trên form Mã Công
		for code in ("P", "1/2P"):
			frappe.db.set_value("Attendance Code", code, "leave_type", self.OWN_TYPE)

	def test_seed_keeps_a_code_on_the_leave_type_hr_chose(self):
		from hrms.setup_vn_defaults import seed_master_data

		seed_master_data()
		self.assertEqual(frappe.db.get_value("Attendance Code", "P", "leave_type"), self.OWN_TYPE)
		self.assertEqual(frappe.db.get_value("Attendance Code", "1/2P", "leave_type"), self.OWN_TYPE)

	def test_seed_does_not_recreate_a_default_leave_type_whose_codes_are_taken(self):
		from hrms.setup_vn_defaults import seed_master_data

		frappe.db.delete("Leave Type", {"name": "Nghỉ phép năm"})
		seed_master_data()
		self.assertFalse(frappe.db.exists("Leave Type", "Nghỉ phép năm"))

	def test_seed_keeps_hr_edits_on_an_existing_leave_type(self):
		from hrms.setup_vn_defaults import seed_master_data

		frappe.db.set_value("Leave Type", "Nghỉ phép năm", "max_leaves_allowed", 99)
		seed_master_data()
		self.assertEqual(frappe.db.get_value("Leave Type", "Nghỉ phép năm", "max_leaves_allowed"), 99)

	def test_seed_still_fills_a_fresh_site(self):
		"""Site mới (CI, cài lại) vẫn phải có đủ bộ mặc định, đã gắn sẵn với nhau."""
		from hrms.setup_vn_defaults import seed_master_data

		frappe.db.delete("Attendance Code", {"name": "KH"})
		frappe.db.delete("Leave Type", {"name": "Nghỉ kết hôn"})
		seed_master_data()
		self.assertTrue(frappe.db.exists("Leave Type", "Nghỉ kết hôn"))
		self.assertEqual(frappe.db.get_value("Attendance Code", "KH", "leave_type"), "Nghỉ kết hôn")

	def test_seed_is_idempotent(self):
		from hrms.setup_vn_defaults import seed_master_data

		seed_master_data()
		before = (frappe.db.count("Attendance Code"), frappe.db.count("Leave Type"))
		seed_master_data()
		self.assertEqual((frappe.db.count("Attendance Code"), frappe.db.count("Leave Type")), before)

	def test_codes_and_leave_types_are_not_fixtures(self):
		"""`sync_fixtures` nạp mọi JSON trong `hrms/fixtures/`, kể cả khi hooks không khai — nên
		bỏ khỏi hooks là chưa đủ, file phải ra khỏi thư mục đó."""
		import os

		import hrms.hooks as hooks

		declared = {e if isinstance(e, str) else e["dt"] for e in hooks.fixtures}
		self.assertNotIn("Attendance Code", declared)
		self.assertNotIn("Leave Type", declared)
		fixture_dir = frappe.get_app_path("hrms", "fixtures")
		self.assertNotIn("attendance_code.json", os.listdir(fixture_dir))
		self.assertNotIn("leave_type.json", os.listdir(fixture_dir))
