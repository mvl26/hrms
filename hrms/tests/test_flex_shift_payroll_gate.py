# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
"""CỔNG BẤT BIẾN LƯƠNG cho luật ca trượt + đủ giờ (spec §8) — chạy trên DỮ LIỆU THẬT của site.

Khác với test đơn vị (dựng dữ liệu giả), cổng này lấy đúng những ngày công đang có trên site,
chấm lại toàn bộ bằng luật MỚI, rồi hỏi một câu duy nhất: **số tiền công có đổi không?**

Hai tầng:

1. `TestEveryLiveDayKeepsItsPaidFraction` — từng ngày một: số công CÓ LƯƠNG trước/sau phải bằng
   nhau. Dùng `_day_paid_fraction`, chính hàm engine lương MVL dùng, nên không so field thô:
   `1/2K` (nghỉ không lương nửa ngày) và `1/2X` (thiếu giờ) đi hai đường khác nhau — LWP và
   half-absent — nhưng đều phải trừ đúng 0,5.
2. `TestLiveSalarySlipsAreUnmoved` — end-to-end: ghi đè kết quả chấm lại vào Attendance (trong
   transaction sẽ rollback), rồi bắt controller tính lại `payment_days` / `absent_days` /
   `leave_without_pay` cho từng phiếu lương ĐÃ SUBMIT và so với con số đang lưu.

Chạy qua harness rollback; không ghi gì vào dữ liệu thật.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.tests.isolation import PerTestRollback
from hrms.vn_payroll.salary_slip_hook import _day_paid_fraction

PAYROLL_FIELDS = ("status", "leave_type", "half_day_status")


def lwp_leave_types() -> set:
	return set(frappe.get_all("Leave Type", filters={"is_lwp": 1}, pluck="name"))


def worked_days_on_site() -> list:
	"""Mọi ngày công đã submit có đủ giờ vào/ra — tức là những ngày luật mới sẽ chấm lại."""
	return frappe.get_all(
		"Attendance",
		filters={"docstatus": 1, "in_time": ["is", "set"], "out_time": ["is", "set"]},
		fields=[
			"name",
			"employee",
			"attendance_date",
			"status",
			"leave_type",
			"half_day_status",
			"custom_attendance_code",
			"working_hours",
		],
		order_by="attendance_date",
	)


def reclassify(name: str):
	"""Chấm lại một ngày bằng luật mới, trả về doc trong bộ nhớ (KHÔNG lưu).

	Xoá mã cũ trước để bộ phân loại thực sự suy lại từ đồng hồ thay vì tôn trọng mã sẵn có.

	Phải chạy **đủ cả hai pha** của đường lưu thật, không chỉ `before_validate`:

	    before_validate: bộ phân loại -> cầu nối mã công   (đặt half_day_status = "Present")
	    validate:        check_leave_record                (ép "Absent" khi không có đơn nghỉ)
	                     restore_code_driven_half_day_status

	Bỏ pha `validate` thì mọi ngày `1/2X` đọc thành 1,0 công thay vì 0,5 — cổng sẽ báo "xê dịch"
	cho dữ liệu vốn đang đúng. Chính chặng giữa mới quyết định số tiền, nên nó phải có mặt ở đây."""
	doc = frappe.get_doc("Attendance", name)
	doc.custom_attendance_code = None
	doc.custom_morning_code = None
	doc.custom_afternoon_code = None
	doc.apply_vn_half_day_classifier()
	doc.apply_attendance_code_bridge()
	doc.check_leave_record()
	doc.restore_code_driven_half_day_status()
	return doc


class TestEveryLiveDayKeepsItsPaidFraction(PerTestRollback, FrappeTestCase):
	def test_no_live_day_changes_how_much_it_pays(self):
		days = worked_days_on_site()
		self.assertTrue(days, "site không có ngày công nào có giờ vào/ra — cổng này sẽ vô nghĩa")

		lwp = lwp_leave_types()
		moved = []
		for row in days:
			after = reclassify(row.name)
			before_paid = _day_paid_fraction(row.status, row.half_day_status, row.leave_type, lwp)
			after_paid = _day_paid_fraction(after.status, after.half_day_status, after.leave_type, lwp)
			if before_paid != after_paid:
				moved.append(
					{
						"ngày": str(row.attendance_date),
						"nhân viên": row.employee,
						"trước": f"{row.custom_attendance_code} {row.status}/{row.leave_type} = {before_paid}",
						"sau": f"{after.custom_attendance_code} {after.status}/{after.leave_type} = {after_paid}",
					}
				)

		self.assertEqual(moved, [], f"luật mới làm xê dịch công có lương của {len(moved)} ngày")

	def test_the_gate_actually_examined_the_kinds_of_day_that_could_move(self):
		"""Cổng chỉ có giá trị nếu nó thực sự soi những ngày dễ đổi nhất: ngày nửa công và ngày
		thiếu giờ. Đếm nổi không có ngày nào như vậy thì phải nói ra, đừng đọc thành 'sạch'."""
		days = worked_days_on_site()
		half_days = [d for d in days if d.status == "Half Day"]
		self.assertTrue(
			half_days,
			"không có ngày Half Day nào trên site → cổng chưa chứng minh được nhánh nửa công",
		)


class TestLiveSalarySlipsAreUnmoved(PerTestRollback, FrappeTestCase):
	def test_submitted_salary_slips_recompute_to_the_same_numbers(self):
		slips = frappe.get_all(
			"Salary Slip",
			filters={"docstatus": 1},
			fields=["name", "employee", "start_date", "end_date", "company"],
			order_by="start_date",
		)
		self.assertTrue(slips, "site không có phiếu lương đã submit nào để đối chiếu")

		stored = {
			s.name: frappe.db.get_value(
				"Salary Slip", s.name, ["payment_days", "absent_days", "leave_without_pay"], as_dict=True
			)
			for s in slips
		}

		# ghi kết quả chấm lại vào Attendance (transaction này sẽ được rollback)
		for row in worked_days_on_site():
			after = reclassify(row.name)
			frappe.db.set_value(
				"Attendance",
				row.name,
				{
					"status": after.status,
					"leave_type": after.leave_type,
					"half_day_status": after.half_day_status,
					"custom_attendance_code": after.custom_attendance_code,
					"working_hours": after.working_hours,
				},
				update_modified=False,
			)

		lệch = []
		for s in slips:
			fresh = frappe.new_doc("Salary Slip")
			fresh.employee = s.employee
			fresh.company = s.company
			fresh.start_date = s.start_date
			fresh.end_date = s.end_date
			fresh.get_working_days_details()
			for field in ("payment_days", "absent_days", "leave_without_pay"):
				cũ, mới = frappe.utils.flt(stored[s.name][field]), frappe.utils.flt(fresh.get(field))
				if cũ != mới:
					lệch.append(f"{s.name} ({s.employee}) {field}: {cũ} -> {mới}")

		self.assertEqual(lệch, [], "phiếu lương đã submit đổi số sau khi chấm lại bằng luật mới")
