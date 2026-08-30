# Copyright (c) 2026, Miyano Việt Nam.
"""Cờ "ngoài lịch làm việc" trên Employee Checkin — nền cho tính năng OT.

Điều quan trọng nhất được chứng minh ở đây không phải là cờ bật đúng chỗ, mà là **cờ TRƠ**: bật nó
lên rồi chấm lại thì mã công và giờ y hệt. Một cờ ghi nhận mà lỡ chạm vào đường sinh công thì nó
thành một đường ghi thứ hai không ai kiểm soát.

Chạy qua harness rollback — mọi thay đổi đều được rollback.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import default_company, test_employee

MON_TO_FRI = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

WORKING_DAY = "2026-07-21"  # thứ Ba
SATURDAY = "2026-07-25"
PUBLIC_HOLIDAY = "2026-07-17"  # thứ Sáu, "Nghỉ lễ công ty"


class TestCheckinOutsideSchedule(PerTestRollback, FrappeTestCase):
	def setUp(self):
		self.company = default_company()
		self.employee = test_employee("outside_schedule@codes.com")
		self.shift = "_Test Ca Ngoai Lich"
		if not frappe.db.exists("Shift Type", self.shift):
			frappe.get_doc(
				{
					"doctype": "Shift Type",
					"__newname": self.shift,
					"start_time": "8:0:0",
					"end_time": "17:0:0",
				}
			).insert(ignore_permissions=True)
		for idx, day in enumerate(MON_TO_FRI, start=1):
			frappe.get_doc(
				{
					"doctype": "Assignment Rule Day",
					"parent": self.shift,
					"parenttype": "Shift Type",
					"parentfield": "custom_working_days",
					"day": day,
					"idx": idx,
				}
			).insert(ignore_permissions=True)
		frappe.db.set_value("Employee", self.employee, "default_shift", self.shift)
		frappe.db.set_value("Employee", self.employee, "holiday_list", self.make_holiday_list())
		frappe.clear_cache(doctype="Employee")

	def make_holiday_list(self) -> str:
		name = "_Test Ngoai Lich 2026"
		if frappe.db.exists("Holiday List", name):
			frappe.delete_doc("Holiday List", name, force=True, ignore_permissions=True)
		return frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": name,
				"from_date": "2026-01-01",
				"to_date": "2026-12-31",
				"holidays": [
					{"holiday_date": PUBLIC_HOLIDAY, "description": "Nghỉ lễ công ty", "weekly_off": 0}
				],
			}
		).insert(ignore_permissions=True).name

	def checkin(self, timestamp, log_type="IN"):
		doc = frappe.get_doc(
			{
				"doctype": "Employee Checkin",
				"employee": self.employee,
				"time": timestamp,
				"log_type": log_type,
				"skip_auto_attendance": 1,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc

	# --- cờ bật đúng chỗ ------------------------------------------------------

	def test_checkin_on_a_saturday_is_flagged_as_a_rest_day(self):
		"""Dữ liệu thật đã có ca này: HR-EMP-00006 chấm 2 lượt vào T7 25/07/2026, không sinh công nào."""
		log = self.checkin(f"{SATURDAY} 09:00:00")
		self.assertEqual(log.custom_outside_schedule, 1)
		self.assertEqual(log.custom_outside_reason, "Ngày nghỉ")

	def test_checkin_on_a_public_holiday_is_flagged_as_a_rest_day(self):
		log = self.checkin(f"{PUBLIC_HOLIDAY} 09:00:00")
		self.assertEqual(log.custom_outside_schedule, 1)
		self.assertEqual(log.custom_outside_reason, "Ngày nghỉ")

	def test_checkin_after_the_shift_ends_is_flagged_as_overtime_window(self):
		log = self.checkin(f"{WORKING_DAY} 20:30:00", log_type="OUT")
		self.assertEqual(log.custom_outside_schedule, 1)
		self.assertEqual(log.custom_outside_reason, "Ngoài giờ")

	def test_checkin_before_the_shift_starts_is_flagged_as_overtime_window(self):
		log = self.checkin(f"{WORKING_DAY} 05:30:00")
		self.assertEqual(log.custom_outside_schedule, 1)
		self.assertEqual(log.custom_outside_reason, "Ngoài giờ")

	def test_checkin_inside_the_shift_is_not_flagged(self):
		log = self.checkin(f"{WORKING_DAY} 08:30:00")
		self.assertEqual(log.custom_outside_schedule, 0)
		self.assertFalse(log.custom_outside_reason)

	def test_a_make_up_day_is_not_flagged(self):
		"""Khai làm bù thì thứ Bảy thành ngày làm việc — chấm trong ca không còn là ngoài lịch."""
		settings = frappe.get_single("Work Calendar Settings")
		settings.append(
			"calendar_days",
			{
				"year": 2026,
				"holiday_date": SATURDAY,
				"day_type": "Làm bù",
				"description": "Làm bù test",
			},
		)
		settings.flags.ignore_permissions = True
		settings.save()
		log = self.checkin(f"{SATURDAY} 09:00:00")
		self.assertEqual(log.custom_outside_schedule, 0)

	# --- CỐT TỬ: cờ phải TRƠ --------------------------------------------------

	def test_the_flag_never_moves_the_attendance_code(self):
		"""Bật cờ tay trên một ngày làm việc bình thường rồi chấm lại → mã công y hệt."""
		att = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.employee,
				"attendance_date": getdate(WORKING_DAY),
				"company": self.company,
				"status": "Present",
			}
		)
		att.insert(ignore_permissions=True)
		att.submit()
		before = frappe.db.get_value(
			"Attendance", att.name, ["status", "custom_attendance_code", "working_hours"], as_dict=True
		)

		log = self.checkin(f"{WORKING_DAY} 08:30:00")
		log.db_set("custom_outside_schedule", 1, update_modified=False)
		log.db_set("custom_outside_reason", "Ngoài giờ", update_modified=False)

		reloaded = frappe.get_doc("Attendance", att.name)
		reloaded.run_method("before_validate")
		after = {
			"status": reloaded.status,
			"custom_attendance_code": reloaded.custom_attendance_code,
			"working_hours": reloaded.working_hours,
		}
		self.assertEqual(dict(before), after, "cờ ghi nhận đã chạm vào mã công — không được phép")
