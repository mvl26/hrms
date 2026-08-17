# Copyright (c) 2026, Miyano Việt Nam.
"""Luật vị trí file của repo. Chạy: python -m unittest discover -s scripts/tests -t ."""

import pathlib
import re
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from check_file_placement import check_all, check_path, hook_decision


class TestTestFilePlacement(unittest.TestCase):
	"""`test_*.py` chỉ được nằm trong tests/ hoặc cạnh doctype nó kiểm."""

	def test_test_file_in_a_tests_folder_is_fine(self):
		self.assertEqual(check_path("hrms/hr/tests/test_working_hours.py"), [])

	def test_test_file_in_app_wide_tests_folder_is_fine(self):
		self.assertEqual(check_path("hrms/tests/test_payroll_gate.py"), [])

	def test_test_file_beside_its_doctype_is_fine(self):
		"""Frappe ràng test_records.json theo đường dẫn doctype — không được chuyển đi."""
		self.assertEqual(check_path("hrms/hr/doctype/attendance/test_attendance.py"), [])

	def test_test_file_beside_its_report_is_fine(self):
		self.assertEqual(check_path("hrms/hr/report/leave_ledger/test_leave_ledger.py"), [])

	def test_test_file_at_module_root_is_rejected(self):
		"""Đúng lỗi đã gặp: test nằm cạnh mã nguồn trong hrms/hr/."""
		problems = check_path("hrms/hr/test_working_hours.py")
		self.assertTrue(problems, "test cạnh mã nguồn phải bị chặn")
		self.assertIn("hrms/hr/tests/", " ".join(problems))

	def test_test_file_in_patches_folder_is_rejected(self):
		problems = check_path("hrms/patches/v15_0/test_backfill_attendance_codes.py")
		self.assertTrue(problems, "test trong thư mục patch phải bị chặn")

	def test_patch_test_is_pointed_at_the_app_wide_tests_folder(self):
		"""Gợi ý `hrms/patches/v15_0/tests/` là vô nghĩa — patch test thuộc về hrms/tests/."""
		problems = check_path("hrms/patches/v15_0/test_backfill_attendance_codes.py")
		self.assertIn("hrms/tests/", " ".join(problems))
		self.assertNotIn("patches/v15_0/tests", " ".join(problems))

	def test_test_file_at_package_root_is_rejected(self):
		self.assertTrue(check_path("hrms/test_something.py"))


class TestDocPlacement(unittest.TestCase):
	"""Tài liệu vào docs/."""

	def test_markdown_under_docs_is_fine(self):
		self.assertEqual(check_path("docs/spec/leave-entitlement-vn.md"), [])

	def test_markdown_at_repo_root_is_rejected(self):
		problems = check_path("notes.md")
		self.assertTrue(problems)
		self.assertIn("docs/", " ".join(problems))

	def test_recreating_the_old_spec_folder_is_rejected(self):
		"""spec/ và tasks/ ở gốc đã bị dọn — không được lập lại."""
		self.assertTrue(check_path("spec/new-feature.md"))

	def test_recreating_the_old_tasks_folder_is_rejected(self):
		self.assertTrue(check_path("tasks/plan-new-feature.md"))

	def test_claude_md_at_root_is_fine(self):
		self.assertEqual(check_path("CLAUDE.md"), [])

	def test_readme_anywhere_is_fine(self):
		self.assertEqual(check_path("hrms/hr/doctype/attendance/README.md"), [])

	def test_claude_code_config_markdown_is_fine(self):
		"""Skill/agent của Claude Code buộc phải nằm trong .claude/, không dời sang docs/ được."""
		self.assertEqual(check_path(".claude/skills/file-placement/SKILL.md"), [])

	def test_notification_template_markdown_is_fine(self):
		"""Frappe đọc template thông báo từ chính thư mục notification."""
		self.assertEqual(check_path("hrms/hr/notification/training_scheduled/training_scheduled.md"), [])


class TestSourcePlacement(unittest.TestCase):
	def test_python_under_hrms_is_fine(self):
		self.assertEqual(check_path("hrms/hr/working_hours.py"), [])

	def test_python_under_scripts_is_fine(self):
		self.assertEqual(check_path("scripts/check_file_placement.py"), [])

	def test_stray_python_at_repo_root_is_rejected(self):
		problems = check_path("fix_stuff.py")
		self.assertTrue(problems)

	def test_dotfile_directory_prefix_survives_normalisation(self):
		"""`.github/` bắt đầu bằng dấu chấm — chuẩn hoá đường dẫn không được ăn mất nó."""
		self.assertEqual(check_path(".github/helper/documentation.py"), [])

	def test_leading_dot_slash_is_stripped(self):
		self.assertEqual(check_path("./hrms/hr/working_hours.py"), [])


class TestNaming(unittest.TestCase):
	"""Chỉ ép những quy ước repo đang tuân 100% — luật báo nhầm hàng loạt là luật bị tắt."""

	def test_space_in_filename_is_rejected(self):
		problems = check_path("docs/MVL_05.25_bang luong.xlsx")
		self.assertTrue(problems)
		self.assertIn("dấu cách", " ".join(problems))

	def test_python_module_must_be_snake_case(self):
		self.assertTrue(check_path("hrms/hr/workingHours.py"))

	def test_snake_case_python_module_is_fine(self):
		self.assertEqual(check_path("hrms/hr/working_hours.py"), [])

	def test_dunder_init_is_fine(self):
		self.assertEqual(check_path("hrms/hr/tests/__init__.py"), [])

	def test_doctype_folder_must_be_snake_case(self):
		self.assertTrue(check_path("hrms/hr/doctype/AttendanceCode/attendance_code.py"))

	def test_test_file_suffix_style_is_rejected(self):
		"""Frappe chỉ nhận tiền tố test_; hậu tố *_test.py sẽ không bao giờ được chạy."""
		problems = check_path("hrms/hr/tests/working_hours_test.py")
		self.assertTrue(problems)
		self.assertIn("test_", " ".join(problems))

	def test_vue_component_must_be_pascal_case(self):
		self.assertTrue(check_path("frontend/src/components/my-widget.vue"))

	def test_pascal_case_vue_is_fine(self):
		self.assertEqual(check_path("frontend/src/components/MyWidget.vue"), [])

	def test_spec_doc_must_be_kebab_case(self):
		self.assertTrue(check_path("docs/spec/Leave_Entitlement.md"))

	def test_kebab_case_spec_doc_is_fine(self):
		self.assertEqual(check_path("docs/spec/leave-entitlement-vn.md"), [])

	def test_plan_doc_must_carry_the_plan_prefix(self):
		self.assertTrue(check_path("docs/tasks/leave-entitlement.md"))

	def test_plan_prefixed_doc_is_fine(self):
		self.assertEqual(check_path("docs/tasks/plan-leave-entitlement.md"), [])

	def test_bare_plan_doc_is_fine(self):
		self.assertEqual(check_path("docs/tasks/plan.md"), [])

	def test_legacy_uppercase_docs_at_docs_root_are_exempt(self):
		"""SPEC.md và tài liệu VN có sẵn ở gốc docs/ — miễn trừ, không đổi tên."""
		self.assertEqual(check_path("docs/SPEC.md"), [])
		self.assertEqual(check_path("docs/Cong_thuc_tinh_luong_MVL.md"), [])


class TestPatchesMustBeRegistered(unittest.TestCase):
	"""Patch không có entry trong patches.txt sẽ không bao giờ chạy — im lặng và vô dụng."""

	PATCHES_TXT = """[post_model_sync]
hrms.patches.v15_0.backfill_attendance_codes #2026-07-08
"""

	def test_registered_patch_is_fine(self):
		found = check_all(["hrms/patches/v15_0/backfill_attendance_codes.py"], self.PATCHES_TXT)
		self.assertEqual(found, {})

	def test_unregistered_patch_is_rejected(self):
		found = check_all(["hrms/patches/v15_0/orphan_patch.py"], self.PATCHES_TXT)
		self.assertIn("hrms/patches/v15_0/orphan_patch.py", found)
		self.assertIn("patches.txt", " ".join(found["hrms/patches/v15_0/orphan_patch.py"]))

	def test_legacy_post_install_patches_are_exempt(self):
		"""Patch upstream cũ đã bị tỉa entry — 16 file như vậy, không phải việc của ta."""
		found = check_all(["hrms/patches/post_install/set_department_for_doctypes.py"], self.PATCHES_TXT)
		self.assertEqual(found, {})

	def test_patch_init_file_is_exempt(self):
		found = check_all(["hrms/patches/v15_0/__init__.py"], self.PATCHES_TXT)
		self.assertEqual(found, {})


class TestHookDecision(unittest.TestCase):
	"""Quyết định của PreToolUse hook: chặn cái gì, để yên cái gì."""

	ROOT = "/repo"

	def decide(self, tool, path, exists=False):
		payload = {"tool_name": tool, "tool_input": {"file_path": path}}
		return hook_decision(payload, root=self.ROOT, exists=lambda _p: exists)

	def test_creating_a_misplaced_file_is_blocked(self):
		message = self.decide("Write", "/repo/hrms/hr/test_new_thing.py")
		self.assertIsNotNone(message)
		self.assertIn("hrms/hr/tests/", message)

	def test_creating_a_well_placed_file_is_allowed(self):
		self.assertIsNone(self.decide("Write", "/repo/hrms/hr/tests/test_new_thing.py"))

	def test_editing_an_existing_misplaced_file_is_allowed(self):
		"""Sửa file đang sai chỗ có thể chính là đang dọn nó — không chặn."""
		self.assertIsNone(self.decide("Edit", "/repo/hrms/hr/test_old.py"))

	def test_overwriting_an_existing_misplaced_file_is_allowed(self):
		self.assertIsNone(self.decide("Write", "/repo/hrms/hr/test_old.py", exists=True))

	def test_paths_outside_the_repo_are_ignored(self):
		self.assertIsNone(self.decide("Write", "/tmp/scratch/test_thing.py"))

	def test_payload_without_a_path_is_ignored(self):
		self.assertIsNone(hook_decision({"tool_name": "Write", "tool_input": {}}, root=self.ROOT))


class TestSkillDocMatchesTheRules(unittest.TestCase):
	"""Skill và cổng chặn phải nói cùng một thứ.

	Kiểu tài liệu này hỏng theo đúng một cách: luật đổi, skill ở lại, rồi AI đọc skill
	và làm sai một cách tự tin. Test này đọc bảng ví dụ trong SKILL.md và bắt checker
	phán quyết đúng như bảng đã hứa.
	"""

	ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*(✅|❌)\s*\|")

	def skill_examples(self):
		skill = pathlib.Path(__file__).resolve().parents[2] / ".claude/skills/file-placement/SKILL.md"
		self.assertTrue(skill.is_file(), f"không thấy skill ở {skill}")
		found = []
		for line in skill.read_text(encoding="utf-8").splitlines():
			match = self.ROW.match(line)
			if match:
				found.append((match.group(1), match.group(2) == "✅"))
		return found

	def test_the_table_was_actually_parsed(self):
		"""Nếu bảng đổi định dạng, test dưới sẽ xanh rỗng — chốt lại để không xanh giả."""
		self.assertGreaterEqual(len(self.skill_examples()), 8)

	def test_every_example_matches_what_the_checker_says(self):
		for path, should_be_valid in self.skill_examples():
			with self.subTest(path=path):
				problems = check_path(path)
				if should_be_valid:
					self.assertEqual(problems, [], f"skill bảo `{path}` hợp lệ, checker không đồng ý")
				else:
					self.assertTrue(problems, f"skill bảo `{path}` sai, checker lại cho qua")


class TestCheckAll(unittest.TestCase):
	def test_reports_every_offending_path(self):
		found = check_all(["hrms/hr/test_a.py", "notes.md", "hrms/hr/working_hours.py"], "")
		self.assertEqual(set(found), {"hrms/hr/test_a.py", "notes.md"})

	def test_clean_list_reports_nothing(self):
		self.assertEqual(check_all(["hrms/hr/working_hours.py", "docs/spec/a-b.md"], ""), {})


if __name__ == "__main__":
	unittest.main()
