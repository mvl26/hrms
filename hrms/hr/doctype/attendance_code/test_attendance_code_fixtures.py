# Copyright (c) 2026, Miyano Việt Nam.
"""Integrity tests for the seeded VN timekeeping master data (Leave Type anchors +
Attendance Codes).

The flag/mapping tables below pin what the app SHIPS in `hrms/seed_data/`, not what the site holds:
after the first seed those records belong to HR (they may move `P` to their own leave type), so a
site-side assertion of the defaults would just re-encode the overwrite this repo stopped doing. On
the site we only check what must always hold — every code's leave type exists."""

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.setup_vn_defaults import seed_records
from hrms.tests.isolation import PerTestRollback

# VN Leave Type anchors — name -> expected flags (is_lwp, is_compensatory, is_ppl, fraction).
#
# Nghỉ do **BHXH chi trả** (ốm Đ.28, chăm con ốm Đ.25, thai sản Đ.39 Luật BHXH): công ty KHÔNG trả
# lương ngày đó nên payroll phải trừ ra (quyết định 2026-07-30, thay quyết định 2026-07-08 vốn giữ
# nguyên is_lwp=0). Cơ chế dùng là `is_ppl` (nghỉ trả một phần) với phần công ty trả = 0, KHÔNG phải
# `is_lwp`: `LeaveType.validate_lwp` chặn đặt is_lwp cho loại nghỉ đã có cấp phép, mà ba loại này đều
# có. Với fraction = 0, cả hai nhánh payroll (theo đơn nghỉ và theo Attendance) đều trừ trọn ngày.
#
# Tai nạn lao động thì KHÁC: Đ.38.3 Luật ATVSLĐ bắt công ty trả đủ lương khi điều trị → vẫn trả đủ.
VN_LEAVE_TYPES = {
	"Nghỉ phép năm": {"is_lwp": 0, "is_compensatory": 0},
	"Nghỉ ốm": {"is_lwp": 0, "is_compensatory": 0, "is_ppl": 1, "fraction": 0.0},
	"Nghỉ chăm con ốm": {"is_lwp": 0, "is_compensatory": 0, "is_ppl": 1, "fraction": 0.0},
	"Nghỉ thai sản": {"is_lwp": 0, "is_compensatory": 0, "is_ppl": 1, "fraction": 0.0},
	"Nghỉ tai nạn lao động": {"is_lwp": 0, "is_compensatory": 0},
	"Nghỉ bù": {"is_lwp": 0, "is_compensatory": 1},
	"Nghỉ không lương": {"is_lwp": 1, "is_compensatory": 0},
	# nghỉ việc riêng có lương (Điều 115 BLLĐ) tách 3 loại — có lương, không trừ phép năm
	"Nghỉ kết hôn": {"is_lwp": 0, "is_compensatory": 0},
	"Nghỉ con kết hôn": {"is_lwp": 0, "is_compensatory": 0},
	"Nghỉ tang": {"is_lwp": 0, "is_compensatory": 0},
}

# Attendance Codes — code -> (category, work_fraction, is_paid, maps_to_status, leave_type).
# work_fraction = phần ngày tính là CÔNG đi làm thực tế (1 / 0.5 / 0). Confirmed 2026-07-08.
VN_ATTENDANCE_CODES = {
	"X": ("Công", 1.0, 1, "Present", None),
	# đi làm nhưng KHÔNG đủ số giờ tối thiểu của ca → nửa công. Thay cho "NN" (bỏ 2026-07-29): NN
	# không nói nửa còn lại nghỉ vì gì, và không có gì tự sinh ra nó. 1/2X do bộ phân loại tự chấm.
	"1/2X": ("Công", 0.5, 1, "Half Day", None),
	"P": ("Phép", 0.0, 1, "On Leave", "Nghỉ phép năm"),
	"1/2P": ("Phép", 0.5, 1, "Half Day", "Nghỉ phép năm"),
	"Ô": ("Ốm", 0.0, 0, "On Leave", "Nghỉ ốm"),
	"Cô": ("Ốm", 0.0, 0, "On Leave", "Nghỉ chăm con ốm"),
	"TS": ("Thai sản", 0.0, 0, "On Leave", "Nghỉ thai sản"),
	"T": ("TNLĐ", 0.0, 1, "On Leave", "Nghỉ tai nạn lao động"),
	"NB": ("Nghỉ bù", 0.0, 1, "On Leave", "Nghỉ bù"),
	"K": ("Không lương", 0.0, 0, "On Leave", "Nghỉ không lương"),
	"1/2K": ("Không lương", 0.5, 0, "Half Day", "Nghỉ không lương"),
	"V": ("Vắng", 0.0, 0, "Absent", None),  # vắng không lý do — hiển thị cho ngày Absent
	"CT": ("Công", 1.0, 1, "Work From Home", None),  # đi công tác — tính công, paid
	"W": ("Công", 1.0, 1, "Work From Home", None),  # làm tại nhà (Yêu cầu chấm công WFH)
	# nghỉ việc riêng có lương (Điều 115) tách 3: kết hôn 3 ngày, con kết hôn 1 ngày, tang 3 ngày
	"KH": ("Việc riêng", 0.0, 1, "On Leave", "Nghỉ kết hôn"),
	"R1": ("Việc riêng", 0.0, 1, "On Leave", "Nghỉ con kết hôn"),
	"R2": ("Việc riêng", 0.0, 1, "On Leave", "Nghỉ tang"),
}


class TestAttendanceCodeFixtures(PerTestRollback, FrappeTestCase):
	def test_vn_leave_type_anchors_exist(self):
		seeded = {r["name"]: r for r in seed_records("leave_type")}
		self.assertEqual(set(seeded), set(VN_LEAVE_TYPES))
		for name, flags in VN_LEAVE_TYPES.items():
			row = seeded[name]
			self.assertEqual(int(row["is_lwp"]), flags["is_lwp"], f"{name}.is_lwp")
			self.assertEqual(int(row["is_compensatory"]), flags["is_compensatory"], f"{name}.is_compensatory")
			self.assertEqual(int(row["is_ppl"]), flags.get("is_ppl", 0), f"{name}.is_ppl")
			self.assertEqual(
				float(row["fraction_of_daily_salary_per_leave"] or 0),
				flags.get("fraction", 0.0),
				f"{name}: phần lương công ty trả cho ngày nghỉ này",
			)

	def test_deprecated_kl_code_removed(self):
		# 'KL' was renamed to 'K' (+ half-day '1/2K') on 2026-07-08; the old code must be gone.
		self.assertFalse(frappe.db.exists("Attendance Code", "KL"), "deprecated code 'KL' should be removed")

	def test_deprecated_nn_code_removed(self):
		# 'NN' bỏ 2026-07-29, thay bằng '1/2X' (xem docs/spec/flex-shift-and-timekeeping-pipeline.md §4.3).
		self.assertFalse(frappe.db.exists("Attendance Code", "NN"), "deprecated code 'NN' should be removed")

	def test_attendance_custom_fields_exist(self):
		for fn in (
			"custom_attendance_code",
			"custom_morning_code",
			"custom_afternoon_code",
			"custom_work_credit",
		):
			self.assertTrue(
				frappe.db.exists("Custom Field", f"Attendance-{fn}"), f"Missing Custom Field: Attendance-{fn}"
			)

	def test_vn_attendance_codes_resolve(self):
		valid_status = {"Present", "Absent", "Half Day", "On Leave", "Work From Home"}
		seeded = {r["name"]: r for r in seed_records("attendance_code")}
		seeded_leave_types = {r["name"] for r in seed_records("leave_type")}
		self.assertEqual(set(seeded), set(VN_ATTENDANCE_CODES))
		for code, (category, wf, is_paid, status, leave_type) in VN_ATTENDANCE_CODES.items():
			row = seeded[code]
			self.assertEqual(row["category"], category, f"{code}.category")
			self.assertEqual(float(row["work_fraction"]), wf, f"{code}.work_fraction")
			self.assertEqual(int(row["is_paid"]), is_paid, f"{code}.is_paid")
			self.assertIn(row["maps_to_status"], valid_status, f"{code}.maps_to_status")
			self.assertEqual(row["maps_to_status"], status, f"{code}.maps_to_status")
			self.assertEqual(row.get("leave_type") or None, leave_type, f"{code}.leave_type")
			if leave_type:
				self.assertIn(leave_type, seeded_leave_types, f"{code} -> leave type not seeded")

	def test_site_codes_point_at_existing_leave_types(self):
		"""Trên site, mã trỏ loại nghỉ NÀO là việc của HR — nhưng loại đó phải có thật."""
		for code, leave_type in frappe.get_all(
			"Attendance Code",
			filters={"leave_type": ("is", "set")},
			fields=["name", "leave_type"],
			as_list=True,
		):
			self.assertTrue(
				frappe.db.exists("Leave Type", leave_type), f"{code} -> missing Leave Type {leave_type}"
			)
