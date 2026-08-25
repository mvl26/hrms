# Copyright (c) 2026, Miyano Việt Nam.
"""Ngày công GHI ĐÈ bởi đơn nghỉ đã duyệt: mã công phải đi theo `status` mới, không kẹt ở `V`.

Bối cảnh (khác `test_leave_code_on_existing_attendance`, chỗ đó là *đơn nghỉ duyệt sau*): ở đây
**đơn nghỉ đã duyệt TỪ TRƯỚC** và ngày công được ghi/dựng lại sau đó — auto-attendance chấm Vắng khi
không có checkin, HR chấm tay, hay công cụ dựng lại công.

Upstream `Attendance.check_leave_record()` chạy trong `validate()` và ÂM THẦM đổi
`status` → `On Leave`/`Half Day` + gán `leave_type`/`leave_application` khi ngày đó có đơn nghỉ đã
duyệt. Nhưng cầu nối mã công chạy ở `before_validate` — TRƯỚC đó — nên nó suy mã từ `status` CŨ
(`Absent` → `V`) và không ai suy lại. Bản ghi lưu xuống thành **status `On Leave` nhưng mã `V`**.

Bảng chấm công ưu tiên mã đã lưu hơn suy ngược từ status (`_resolve_day`), nên ngày nghỉ phép hiện
là VẮNG trong khi lương (đọc `status`) tính là nghỉ — đúng cái "không đồng bộ công" đã báo.

Chạy qua harness rollback (KHÔNG bench run-tests trên miyano).
"""

import frappe
from frappe.tests.utils import FrappeTestCase, change_settings

from hrms.hr.doctype.attendance.attendance import mark_attendance
from hrms.tests.isolation import PerTestRollback
from hrms.tests.vn_test_utils import default_company, test_employee


class TestCodeResyncOnLeaveRecord(PerTestRollback, FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.year = 2097
		cls.emp = test_employee()
		cls.company = frappe.db.get_value("Employee", cls.emp, "company")

	def alloc(self, leave_type, days=30):
		doc = frappe.get_doc(
			{
				"doctype": "Leave Allocation",
				"employee": self.emp,
				"leave_type": leave_type,
				"from_date": f"{self.year}-01-01",
				"to_date": f"{self.year}-12-31",
				"new_leaves_allocated": days,
				"company": self.company,
			}
		)
		doc.insert(ignore_permissions=True)
		doc.submit()

	def approve_leave(self, leave_type, date, reason=None, half_day=False, period=None):
		doc = frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": self.emp,
				"leave_type": leave_type,
				"from_date": date,
				"to_date": date,
				"company": self.company,
				"status": "Approved",
			}
		)
		if reason:
			doc.custom_leave_reason = reason
		if half_day:
			doc.half_day = 1
			doc.half_day_date = date
			if period:
				doc.custom_half_day_period = period
		doc.insert(ignore_permissions=True)
		doc.submit()
		return doc

	def drop_attendance(self, date):
		"""Xoá ngày công đơn nghỉ vừa sinh — dựng lại đúng tình huống bản ghi phải ghi lại từ đầu
		(công cụ dựng lại công, HR huỷ rồi chấm lại, bản ghi bị xoá)."""
		name = frappe.db.get_value(
			"Attendance", {"employee": self.emp, "attendance_date": date, "docstatus": ("<", 2)}
		)
		if not name:
			return
		doc = frappe.get_doc("Attendance", name)
		if doc.docstatus == 1:
			doc.cancel()
		frappe.delete_doc("Attendance", name, force=1)

	def row(self, date):
		return frappe.db.get_value(
			"Attendance",
			{"employee": self.emp, "attendance_date": date, "docstatus": ("<", 2)},
			[
				"status",
				"leave_type",
				"half_day_status",
				"custom_attendance_code",
				"custom_morning_code",
				"custom_afternoon_code",
				"custom_work_credit",
			],
			as_dict=True,
		)

	def mark_absent(self, date):
		"""Đúng lối auto-attendance chấm Vắng khi ngày đó không có checkin."""
		return mark_attendance(self.emp, date, "Absent")

	# --- lỗi được báo -------------------------------------------------------------------------
	def test_auto_attendance_absent_on_leave_day_gets_leave_code(self):
		"""Đơn nghỉ đã duyệt + auto-attendance chấm Vắng → mã phải là `Ô`, không phải `V`."""
		date = f"{self.year}-05-04"
		self.alloc("Nghỉ ốm")
		self.approve_leave("Nghỉ ốm", date)
		self.drop_attendance(date)

		self.mark_absent(date)

		row = self.row(date)
		self.assertEqual(row.status, "On Leave", "tiền đề: check_leave_record đã lật sang nghỉ")
		self.assertEqual(row.custom_attendance_code, "Ô", "mã phải theo loại nghỉ, không kẹt ở V")

	def test_manual_absent_entry_on_leave_day_gets_leave_code(self):
		"""HR chấm tay Vắng lên ngày đã có đơn nghỉ duyệt → mã cũng phải theo loại nghỉ."""
		date = f"{self.year}-05-05"
		self.alloc("Nghỉ tang", 3)
		self.approve_leave("Nghỉ tang", date)
		self.drop_attendance(date)

		doc = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": date,
				"company": self.company,
				"status": "Absent",
			}
		)
		doc.insert(ignore_permissions=True)
		doc.submit()

		self.assertEqual(self.row(date).custom_attendance_code, "R2")

	def test_half_day_leave_day_gets_half_day_token(self):
		"""Nghỉ NỬA ngày đã duyệt + chấm Vắng → token nửa ngày `1/2P`, không phải `V`."""
		date = f"{self.year}-05-06"
		self.alloc("Nghỉ phép năm", 12)
		self.approve_leave("Nghỉ phép năm", date, reason="Nghỉ phép năm", half_day=True, period="Sáng")
		self.drop_attendance(date)

		self.mark_absent(date)

		row = self.row(date)
		self.assertEqual(row.status, "Half Day")
		self.assertEqual(row.custom_attendance_code, "1/2P")

	def test_work_credit_follows_new_code(self):
		"""Số công của ngày phải tính lại theo mã mới, không giữ số của mã `V` cũ.

		`Nghỉ bù` do CÔNG TY trả nên đủ công (1.0); `V` là 0.0."""
		date = f"{self.year}-05-07"
		self.alloc("Nghỉ bù", 5)
		self.approve_leave("Nghỉ bù", date)
		self.drop_attendance(date)

		self.mark_absent(date)

		row = self.row(date)
		self.assertEqual(row.custom_attendance_code, "NB")
		self.assertEqual(row.custom_work_credit, 1.0)

	def test_stale_half_codes_cleared(self):
		"""Mã nửa buổi cũ (`V`/`V`) không được sót lại khi cả ngày đã thành ngày nghỉ."""
		date = f"{self.year}-05-08"
		self.alloc("Nghỉ ốm")
		self.approve_leave("Nghỉ ốm", date)
		self.drop_attendance(date)

		doc = frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": self.emp,
				"attendance_date": date,
				"company": self.company,
				"status": "Absent",
				"custom_morning_code": "V",
				"custom_afternoon_code": "V",
			}
		)
		doc.insert(ignore_permissions=True)
		doc.submit()

		row = self.row(date)
		self.assertEqual(row.custom_attendance_code, "Ô")
		self.assertIsNone(row.custom_morning_code)
		self.assertIsNone(row.custom_afternoon_code)

	# --- ràng buộc: không được làm hỏng cái đang đúng ------------------------------------------
	def test_payroll_fields_untouched(self):
		"""Sửa mã công là THUẦN HIỂN THỊ — ba field lương giữ đúng giá trị check_leave_record đặt."""
		date = f"{self.year}-05-11"
		self.alloc("Nghỉ ốm")
		self.approve_leave("Nghỉ ốm", date)
		self.drop_attendance(date)

		self.mark_absent(date)

		row = self.row(date)
		self.assertEqual(row.status, "On Leave")
		self.assertEqual(row.leave_type, "Nghỉ ốm")
		self.assertIsNone(row.half_day_status)

	def test_absent_day_without_leave_keeps_v(self):
		"""Ngày vắng THẬT (không có đơn nghỉ) vẫn là `V` — bản sửa không được đụng tới."""
		date = f"{self.year}-05-12"
		self.mark_absent(date)

		row = self.row(date)
		self.assertEqual(row.status, "Absent")
		self.assertEqual(row.custom_attendance_code, "V")

	def test_unmapped_leave_type_keeps_existing_code(self):
		"""Loại nghỉ mất mã: bộ suy lại GIỮ NGUYÊN mã cũ, tuyệt đối không bịa.

		Từ 2026-08-24 đơn nghỉ theo loại chưa có mã bị chặn ngay (`test_leave_type_code_gate.py`),
		nên không dựng được kịch bản này bằng cách tạo đơn cho loại nghỉ trắng nữa. Đường còn lại —
		và là đường thật sự xảy ra ngoài đời: đơn duyệt lúc mã còn, HR gỡ mã sau, rồi ngày công mới
		được ghi. Bộ suy lại vẫn phải tự thủ."""
		lt = frappe.get_doc(
			{"doctype": "Leave Type", "leave_type_name": "Nghỉ thử mất mã resync", "is_lwp": 0}
		)
		lt.insert(ignore_permissions=True)
		code = frappe.get_doc(
			{
				"doctype": "Attendance Code",
				"code": "ZR",
				"code_name": "Mã thử sẽ bị gỡ",
				"category": "Phép",
				"maps_to_status": "On Leave",
				"work_fraction": 0,
				"leave_type": lt.name,
			}
		)
		code.insert(ignore_permissions=True)

		date = f"{self.year}-05-13"
		self.alloc(lt.name)
		self.approve_leave(lt.name, date)
		self.drop_attendance(date)

		# HR gỡ mã SAU khi đơn đã duyệt → loại nghỉ không còn đường tra ngược
		frappe.db.set_value("Attendance Code", code.name, "leave_type", None)

		self.mark_absent(date)

		row = self.row(date)
		self.assertEqual(row.status, "On Leave", "tiền đề: check_leave_record vẫn lật sang nghỉ")
		self.assertEqual(row.custom_attendance_code, "V", "không tra được mã thì giữ nguyên, không bịa")

	def test_valid_code_is_not_rewritten(self):
		"""Mã đã hợp lệ với status/loại nghỉ thì giữ nguyên — không bị đè bởi bộ suy lại."""
		date = f"{self.year}-05-14"
		self.alloc("Nghỉ ốm")
		self.approve_leave("Nghỉ ốm", date)

		# đơn nghỉ sinh ngày công + hook đã ghi mã Ô; lưu lại lần nữa không được đổi gì
		name = frappe.db.get_value(
			"Attendance", {"employee": self.emp, "attendance_date": date, "docstatus": ("<", 2)}
		)
		doc = frappe.get_doc("Attendance", name)
		doc.save(ignore_permissions=True)

		self.assertEqual(self.row(date).custom_attendance_code, "Ô")


class TestPayrollUnmovedByCodeResync(PerTestRollback, FrappeTestCase):
	"""Cổng bất biến lương (CLAUDE.md): suy lại mã công KHÔNG được làm xê dịch số của phiếu lương.

	Chọn đúng ca hiểm nhất — nghỉ phép NỬA ngày trên ngày công phải dựng lại: đó là ca duy nhất bản
	sửa chạm tới `half_day_status` (None → "Present", do cầu nối xuôi điền khi thấy mã `1/2P`). Ba
	con số lương đọc từ chấm công phải y hệt bản chưa sửa. "Present" cũng chính là giá trị đường đơn
	nghỉ vẫn ghi (xem `test_half_day_leave_payroll`); chỉ ngày bị dựng lại mới rơi vào None, nên bản
	sửa kéo hai đường về cùng một chỗ chứ không đẻ ra giá trị mới."""

	def setUp(self):
		super().setUp()
		# Bộ này kiểm con số lương, không kiểm cổng chốt công (kỳ 2099 không có Bảng Công Tháng).
		frappe.flags.skip_sheet_gate = True
		self.addCleanup(lambda: frappe.flags.pop("skip_sheet_gate", None))

	@change_settings("Payroll Settings", {"payroll_based_on": "Attendance"})
	def test_half_day_leave_rebuilt_day_keeps_payroll_numbers(self):
		from erpnext.setup.doctype.employee.test_employee import make_employee

		from hrms.vn_payroll.setup_mvl import ensure_mvl_defaults
		from hrms.vn_payroll.tests.test_salary_slip_mvl import (
			ensure_fiscal_year_2099,
			make_slip,
			make_ssa,
			mark_full_month,
		)

		ensure_fiscal_year_2099()
		ensure_mvl_defaults()
		company = default_company()
		emp = make_employee("resync_payroll@codes.com", company=company)
		make_ssa(emp, base=25_000_000, custom_salary_type="Chính thức", custom_bhxh_salary=25_000_000)
		mark_full_month(emp)

		date = "2099-06-15"
		alloc = frappe.get_doc(
			{
				"doctype": "Leave Allocation",
				"employee": emp,
				"leave_type": "Nghỉ phép năm",
				"from_date": "2099-01-01",
				"to_date": "2099-12-31",
				"new_leaves_allocated": 12,
				"company": company,
			}
		)
		alloc.insert()
		alloc.submit()

		# ngày công của mark_full_month phải nhường chỗ cho đơn nghỉ
		existing = frappe.db.get_value(
			"Attendance", {"employee": emp, "attendance_date": date, "docstatus": ("<", 2)}
		)
		doc = frappe.get_doc("Attendance", existing)
		doc.cancel()
		frappe.delete_doc("Attendance", existing, force=1)

		leave = frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": emp,
				"leave_type": "Nghỉ phép năm",
				"from_date": date,
				"to_date": date,
				"half_day": 1,
				"half_day_date": date,
				"company": company,
				"status": "Approved",
				"custom_leave_reason": "Nghỉ phép năm",
				"custom_half_day_period": "Sáng",
			}
		)
		leave.insert()
		leave.submit()

		# ...rồi ngày công ấy bị dựng lại (công cụ rebuild / auto-attendance chấm Vắng)
		rebuilt = frappe.db.get_value(
			"Attendance", {"employee": emp, "attendance_date": date, "docstatus": ("<", 2)}
		)
		doc = frappe.get_doc("Attendance", rebuilt)
		doc.cancel()
		frappe.delete_doc("Attendance", rebuilt, force=1)
		mark_attendance(emp, date, "Absent")

		row = frappe.db.get_value(
			"Attendance",
			{"employee": emp, "attendance_date": date, "docstatus": ("<", 2)},
			["status", "half_day_status", "custom_attendance_code"],
			as_dict=True,
		)
		self.assertEqual(row.custom_attendance_code, "1/2P", "tiền đề: bản sửa đã suy lại mã")
		self.assertEqual(row.status, "Half Day")
		self.assertNotEqual(
			row.half_day_status, "Absent", "nửa đi làm không được thành Absent — sẽ bị trừ thêm 0,5"
		)

		ss = make_slip(emp)
		# Ba con số lương đọc từ chấm công. Giá trị này BẰNG ĐÚNG bản chưa sửa (đã đối chiếu
		# bằng cách stash bản sửa và chạy lại chính test này) — nghỉ phép năm là nghỉ CÓ LƯƠNG,
		# nửa còn lại đi làm, nên ngày đó vẫn trả đủ và không tính vắng, không tính LWP.
		self.assertEqual(ss.payment_days, 30)
		self.assertEqual(ss.absent_days, 0)
		self.assertEqual(ss.leave_without_pay, 0)
