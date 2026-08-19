from datetime import datetime, timedelta

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder.functions import Date
from frappe.utils import (
	add_days,
	cint,
	cstr,
	flt,
	format_date,
	get_datetime,
	get_link_to_form,
	getdate,
	nowdate,
)

from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee
from erpnext.setup.doctype.holiday_list.holiday_list import is_holiday

import hrms
from hrms.hr.doctype.attendance.vn_day_classifier import (
	DEFAULT_LUNCH_END,
	DEFAULT_LUNCH_START,
	classify_day,
	resolve_lunch_window,
)
from hrms.hr.doctype.shift_assignment.shift_assignment import has_overlapping_timings
from hrms.hr.utils import (
	get_holiday_dates_for_employee,
	get_holidays_for_employee,
	validate_active_employee,
)


class DuplicateAttendanceError(frappe.ValidationError):
	pass


class OverlappingShiftAttendanceError(frappe.ValidationError):
	pass


# Khi NHIỀU mã công cùng maps_to_status (leave_type trống), reverse-derive (status→mã, thuần hiển thị)
# phải chọn ĐỊNH DANH. Mã "chính" cho mỗi native status có thể trùng: Present có X (+CV cũ), Work From
# Home có CT và W (làm nhà). W chỉ được đặt tường minh bởi hook Yêu cầu chấm công nên bản ghi WFH
# không mã phải quy về CT. Các status khác phân biệt bằng leave_type nên không cần liệt kê.
CANONICAL_REVERSE_CODE = {"Present": "X", "Work From Home": "CT"}


def _pick_reverse_code(status, matches):
	"""Chọn mã reverse xác định khi nhiều mã cùng khớp một status (thuần hiển thị)."""
	if not matches:
		return None
	if len(matches) == 1:
		return matches[0]
	preferred = CANONICAL_REVERSE_CODE.get(status)
	if preferred and preferred in matches:
		return preferred
	return sorted(matches)[0]  # ổn định (deterministic) khi không có mã ưu tiên


class Attendance(Document):
	def before_validate(self):
		self.apply_vn_half_day_classifier()
		self.apply_attendance_code_bridge()
		self.set_lunch_flag()
		# Ghi lại Ý ĐỊNH trước khi validate chạy. check_leave_record sẽ ép half_day_status="Absent"
		# khi không có Leave Application; restore_code_driven_half_day_status chỉ được hoàn tác ĐÚNG
		# lần ép đó, tuyệt đối không đè giá trị "Absent" do người gọi cố ý đặt (payroll đọc field này).
		self.flags.vn_half_day_status_intent = self.half_day_status
		# Mốc so sánh cho resync_code_after_leave_record: check_leave_record (chạy trong `validate`,
		# tức SAU cầu nối) có thể lật status/leave_type theo đơn nghỉ đã duyệt. Chụp lại ở đây để
		# biết chính xác nó có đổi hay không.
		self.flags.vn_status_before_leave_record = (self.status, self.leave_type)

	def set_lunch_flag(self):
		"""Miyano: ghi cờ ăn trưa (custom_lunch) từ checkin của ngày này — nguồn duy nhất cho số buổi
		ăn trưa (report + Bảng Công Tháng + phiếu lương đều đếm từ cờ). Thuần dữ liệu, payroll đọc
		riêng cho phụ cấp ăn trưa; không đụng status/leave_type/half_day_status."""
		if not frappe.get_meta("Attendance").has_field("custom_lunch"):
			return  # field chưa migrate
		from hrms.vn_payroll.lunch import lunch_flag_for_attendance

		self.custom_lunch = (
			1
			if lunch_flag_for_attendance(self.employee, self.attendance_date, self.status, self.shift)
			else 0
		)

	def before_insert(self):
		if self.half_day_status == "":
			self.half_day_status = None

	def restore_code_driven_half_day_status(self):
		"""A half-day *leave* entered via mã công (1/2P, 1/2K, or a worked+leave split like X|P)
		has no backing Leave Application, so check_leave_record forces half_day_status="Absent".
		That is wrong here: the worked half IS present and the leave half's pay effect is already
		carried by leave_type (paid leaves aren't in payroll's LWP map; unpaid ones dock via it).
		Forcing Absent makes get_half_absent_days dock an extra 0.5 — over-deducting a paid half
		(1/2P) and double-deducting an unpaid half (1/2K). When a code drove this Half Day and set
		a leave_type, restore the worked half to Present. 1/2X (no leave_type) is left Absent so it
		still docks 0.5 exactly like a native Half Day."""
		code_driven = (
			self.get("custom_attendance_code")
			or self.get("custom_morning_code")
			or self.get("custom_afternoon_code")
		)
		if (
			code_driven
			and self.status == "Half Day"
			and self.leave_type
			and not self.leave_application
			# chỉ khi chính check_leave_record vừa lật Present -> Absent; nếu người gọi đặt "Absent"
			# ngay từ đầu (nửa ngày nghỉ KHÔNG hưởng công) thì giữ nguyên, nếu không payment_days
			# bị cộng thêm 0,5 cho mỗi ngày như vậy.
			and self.flags.get("vn_half_day_status_intent") == "Present"
		):
			self.half_day_status = "Present"

	# fallbacks for shifts that enable the split but leave a config field blank
	# (giờ nghỉ trưa: một nguồn duy nhất trong `vn_day_classifier`, xem `resolve_lunch_window`)
	VN_DEFAULT_LUNCH_START = DEFAULT_LUNCH_START
	VN_DEFAULT_LUNCH_END = DEFAULT_LUNCH_END
	VN_DEFAULT_FLEX_BAND_MINUTES = 180
	VN_DEFAULT_MIN_WORK_HOURS = 8.0

	def get_split_shift_config(self):
		"""Cấu hình ca cho luật chấm công VN, hoặc None nếu ca không bật tách buổi.

		Đọc PHÒNG THỦ: 3 field giờ linh hoạt là custom field (fixtures), site chưa migrate thì
		chưa có → bỏ qua chúng và coi như tắt giờ linh hoạt, tức hành vi y hệt trước đây."""
		meta = frappe.get_meta("Shift Type")
		fields = ["start_time", "end_time", "custom_split_half_day", "custom_lunch_start", "custom_lunch_end"]
		fields.append("mark_auto_attendance_on_holidays")  # quyết định ngày nghỉ có được chấm hay không
		fields += [
			f
			for f in ("custom_flexible_shift", "custom_flex_band_minutes", "custom_min_work_hours")
			if meta.has_field(f)
		]
		cfg = frappe.db.get_value("Shift Type", self.shift, fields, as_dict=True)
		if not cfg or not cint(cfg.custom_split_half_day) or not (cfg.start_time and cfg.end_time):
			return None
		return cfg

	def falls_on_holiday(self) -> bool:
		"""Ngày chấm công có nằm trong Holiday List của nhân viên không (T7/CN/lễ)."""
		holiday_list = get_holiday_list_for_employee(self.employee, raise_exception=False)
		return bool(holiday_list) and is_holiday(holiday_list, getdate(self.attendance_date))

	def apply_vn_half_day_classifier(self):
		"""Chấm mã công + giờ net từ giờ vào/ra theo luật ca trượt & đủ giờ (`vn_day_classifier`).

		Chỉ chạy khi: ca có bật `custom_split_half_day`, có đủ in/out, chưa có mã nhập tay, và ngày
		không thuộc diện nghỉ phép. Ngày nghỉ (T7/CN/lễ) thì tuỳ cờ `mark_auto_attendance_on_holidays`
		của ca: tắt → không chấm gì; bật → chấm y như ngày thường. Xem spec §4.2 và §13."""
		if not self.get("shift") or not self.get("in_time") or not self.get("out_time"):
			return
		if (
			self.get("custom_attendance_code")
			or self.get("custom_morning_code")
			or self.get("custom_afternoon_code")
		):
			return  # respect a manually entered code
		if self.get("status") == "On Leave" or self.get("leave_type"):
			# A day already attributed to a leave — full day, or a half-day leave whose other half
			# was worked — must keep that attribution. Re-deriving both halves from the clock would
			# rewrite leave_type from the leave-less "V" code and silently drop the employee's leave.
			return

		cfg = self.get_split_shift_config()
		if not cfg:
			return
		if not cint(cfg.get("mark_auto_attendance_on_holidays")) and self.falls_on_holiday():
			# Ngày nghỉ (T7/CN/lễ) mà ca KHÔNG bật chấm công ngày nghỉ: không tự chấm mã. Bản ghi vẫn
			# có thể sinh ra từ nhập tay / Yêu cầu chấm công; đem khung ca ngày thường ra chấm thì
			# người đi làm ngày nghỉ bị quy thành V hoặc nửa công.
			#
			# Ca CÓ bật cờ thì ngược lại: công ty chủ động tính công ngày nghỉ, nên ngày đó phải đi
			# đúng luật như ngày thường (trừ nghỉ trưa, đủ giờ mới X). Bỏ qua ở đây thì `working_hours`
			# là giờ THÔ chưa trừ trưa và chấm 10 phút cũng thành X đủ công.
			return

		band = cfg.get("custom_flex_band_minutes")
		lunch_start, lunch_end = resolve_lunch_window(cfg.custom_lunch_start, cfg.custom_lunch_end)
		# `working_hours` nhận GIỜ LÀM THỰC TẾ (không bị khung ca cắt) — làm 08:23-18:55 phải ghi
		# 9h02 chứ không phải 8h. Mã công thì quyết định theo `counted` (phần trong khung ca), nên
		# ở lại muộn vẫn không tự thành công thêm. Xem `DayResult`.
		ket_qua = classify_day(
			get_datetime(self.in_time),
			get_datetime(self.out_time),
			day=datetime.combine(getdate(self.attendance_date), datetime.min.time()),
			start_time=cfg.start_time,
			end_time=cfg.end_time,
			lunch_start=lunch_start,
			lunch_end=lunch_end,
			flexible=bool(cint(cfg.get("custom_flexible_shift"))),
			# 0 nghĩa là "tắt trượt" (khác với bỏ trống → dùng mặc định)
			band_minutes=self.VN_DEFAULT_FLEX_BAND_MINUTES if band is None else cint(band),
			min_work_hours=flt(cfg.get("custom_min_work_hours")) or self.VN_DEFAULT_MIN_WORK_HOURS,
		)
		self.working_hours = ket_qua.hours
		from hrms.hr.attendance_exempt import EXEMPT_CODE, is_exempt_working_day

		if is_exempt_working_day(self.employee, self.attendance_date):
			# Người miễn chấm công: giờ vào/ra chỉ để BÁO CÁO, không bao giờ quyết định công. Bỏ
			# bước này thì giám đốc ghé một tiếng bị quy 1/2K và mất nửa ngày lương.
			self.custom_attendance_code = EXEMPT_CODE
			return
		self.custom_attendance_code = ket_qua.code

	def apply_attendance_code_bridge(self):
		"""Two-way bridge between VN attendance codes (mã công) and the native status fields
		that payroll reads (status / leave_type / half_day_status). It never touches the
		skip logic and only sets fields native entry would set, so payroll stays invariant.

		Forward (user entered code(s)): morning/afternoon (or a single day code) -> native fields
		+ custom_work_credit (số công DOANH NGHIỆP TRẢ cho ngày đó — xem `_apply_codes_forward`).
		Reverse (record has a status but no code, e.g. from auto-attendance / leave): derive
		custom_attendance_code for display only, without changing native fields.
		"""
		if not frappe.get_meta("Attendance").has_field("custom_attendance_code"):
			return  # custom-field fixtures not installed yet

		self.clear_stale_work_code_on_leave()

		morning = self.get("custom_morning_code") or self.get("custom_attendance_code")
		afternoon = self.get("custom_afternoon_code") or self.get("custom_attendance_code")

		if morning or afternoon:
			self._apply_codes_forward(morning or afternoon, afternoon or morning)
		else:
			self._derive_attendance_code_reverse()

	def clear_stale_work_code_on_leave(self):
		"""Ngày do NGHỈ PHÉP dẫn dắt (có leave_application, status On Leave/Half Day) mà mã đang là mã ĐI
		LÀM (category "Công": X/CT/1/2X…) là mã CŨ sót từ lần auto-attendance chấm Present TRƯỚC khi áp đơn
		nghỉ. Giữ lại thì forward-bridge sẽ lật status về Present (mã X → Present) → mất nửa/cả ngày nghỉ.
		Bỏ mã sót để reverse suy lại đúng từ leave_type (vd nghỉ phép nửa ngày → 1/2P). Mã nghỉ / tách đúng
		(morning là mã nghỉ) được giữ nguyên."""
		if not (self.get("leave_application") and self.get("status") in ("On Leave", "Half Day")):
			return
		code = self.get("custom_morning_code") or self.get("custom_attendance_code")
		if not code:
			return
		c = self._get_attendance_code(code)
		if c and c.category == "Công":
			self.custom_attendance_code = None
			self.custom_morning_code = None
			self.custom_afternoon_code = None

	def resync_code_after_leave_record(self):
		"""Suy lại mã công SAU khi `check_leave_record` chốt `status`/`leave_type`.

		**Vì sao cần:** cầu nối mã công chạy ở `before_validate`, còn upstream `check_leave_record`
		chạy trong `validate` — tức SAU đó — và âm thầm lật `status` sang `On Leave`/`Half Day` +
		gán `leave_type`/`leave_application` khi ngày đó có đơn nghỉ ĐÃ DUYỆT. Mã vì thế được suy từ
		status CŨ rồi kẹt lại: auto-attendance chấm Vắng lên ngày đã có phép thì bản ghi lưu xuống
		là `status = On Leave` nhưng mã `V`. Bảng chấm công ưu tiên mã đã lưu hơn suy ngược từ status
		(`_resolve_day`) nên ngày nghỉ hiện thành VẮNG, trong khi lương (đọc `status`) tính là nghỉ.

		THUẦN HIỂN THỊ: chỉ ghi mã + `custom_work_credit`, KHÔNG đụng
		`status`/`leave_type`/`half_day_status` → lương bất biến.

		Hai ràng buộc, giống hệt bộ đồng bộ thủ công (`attendance_code_sync.expected_code`):
		- **Giữ nguyên** mã đang có nếu nó vẫn hợp lệ với status mới — nhiều mã chung một status và
		  KHÔNG thay được cho nhau (`W` làm tại nhà vs `CT` đi công tác).
		- **Không bịa** mã khi loại nghỉ chưa map tới `Attendance Code` nào.
		"""
		if not frappe.get_meta("Attendance").has_field("custom_attendance_code"):
			return  # custom-field fixtures chưa cài

		before = self.flags.get("vn_status_before_leave_record")
		if before is None or before == (self.status, self.leave_type):
			return  # check_leave_record không đổi gì → mã hiện tại vẫn suy từ đúng status

		from hrms.hr.attendance_code_sync import matching_codes
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import paid_credit

		matches = matching_codes(self)
		if self.custom_attendance_code in matches:
			return  # mã đang có vẫn hợp lệ với status mới

		code = _pick_reverse_code(self.status, matches)
		if not code:
			return  # chưa map được thì GIỮ NGUYÊN mã cũ

		self.custom_attendance_code = code
		# cả ngày đã do đơn nghỉ dẫn dắt → mã nửa buổi cũ (vd V/V) là rác, phải dọn
		self.custom_morning_code = None
		self.custom_afternoon_code = None
		self.custom_work_credit = paid_credit(self._get_attendance_code(code))

	def _get_attendance_code(self, name):
		if not name:
			return None
		return frappe.db.get_value(
			"Attendance Code",
			name,
			["category", "work_fraction", "is_paid", "maps_to_status", "leave_type"],
			as_dict=True,
		)

	def _apply_codes_forward(self, morning, afternoon):
		m = self._get_attendance_code(morning)
		a = self._get_attendance_code(afternoon)
		if not (m and a):
			return

		# Field "Công" = số công DOANH NGHIỆP TRẢ cho ngày này — khớp đúng cột "Tổng công" của bảng
		# công tháng (dùng chung `paid_credit`, không chép luật sang đây để hai nơi không lệch nhau).
		#
		# Trước đây field mang `work_fraction` — công ĐI LÀM thực tế — nên một ngày nghỉ phép năm hiện
		# "Công = 0" dù công ty trả đủ lương ngày đó, và con số 0 ấy gộp chung ba nhóm khác hẳn nhau:
		# nghỉ công ty trả (P/KH/R1/R2/NB/T), nghỉ BHXH chi trả (Ô/Cô/TS) và không ai trả (K/V).
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import paid_credit

		self.custom_work_credit = sum(paid_credit(c) * 0.5 for c in (m, a))
		# single display code only when the whole day is one code
		self.custom_attendance_code = morning if morning == afternoon else None

		if m.maps_to_status == a.maps_to_status:
			self.status = m.maps_to_status
			self.leave_type = m.leave_type if m.maps_to_status in ("On Leave", "Half Day") else None
			if m.maps_to_status == "Half Day":
				# a single Half-Day code (1/2X/1/2P/1/2K): worked half is present, the other half is
				# leave (if leave_type set) or unpaid absence (1/2X). Mirrors native Half-Day entry.
				# CHỈ điền khi còn trống: bản ghi lưu lần đầu đã được suy ngược ra mã, nên lần lưu
				# sau (submit) sẽ đi nhánh xuôi này lần nữa — đè lên đây sẽ xoá mất half_day_status
				# mà người gọi cố ý đặt là "Absent", cộng oan 0,5 ngày vào payment_days.
				self.half_day_status = self.half_day_status or "Present"
			else:
				# non-Half-Day status: half_day_status is meaningless -> clear any stale value the
				# threshold path (auto-attendance) may have pre-set before the code reclassified it.
				self.half_day_status = None
		else:
			# one working half + one non-working half -> Half Day; the non-working half sets leave_type
			self.status = "Half Day"
			leave_half = m if m.maps_to_status not in ("Present", "Work From Home") else a
			self.leave_type = leave_half.leave_type
			self.half_day_status = "Present" if leave_half.maps_to_status == "On Leave" else "Absent"

	def _derive_attendance_code_reverse(self):
		if self.get("custom_attendance_code") or not self.status:
			return
		# ["is","not set"] reliably matches NULL/'' Link values (unlike ["in", ["", None]])
		filters = {"maps_to_status": self.status, "leave_type": self.leave_type or ["is", "not set"]}
		matches = frappe.get_all("Attendance Code", filters=filters, pluck="name")
		code = _pick_reverse_code(self.status, matches)
		if not code:
			return
		self.custom_attendance_code = code
		c = self._get_attendance_code(code)
		# cùng một luật "ai trả" như nhánh forward — xem `_apply_codes_forward`
		from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import paid_credit

		self.custom_work_credit = paid_credit(c) if c else 0

	def validate(self):
		from erpnext.controllers.status_updater import validate_status

		validate_status(self.status, ["Present", "Absent", "On Leave", "Half Day", "Work From Home"])
		validate_active_employee(self.employee)
		self.validate_attendance_date()
		self.validate_duplicate_record()
		self.validate_overlapping_shift_attendance()
		self.validate_employee_status()
		self.check_leave_record()
		# check_leave_record forces half_day_status="Absent" when no Leave Application backs the day;
		# undo that for mã-công half-day leaves (the worked half is present). Runs on every save path.
		self.restore_code_driven_half_day_status()
		# ... và nếu chính check_leave_record vừa đổi status theo đơn nghỉ, suy lại mã công cho khớp.
		self.resync_code_after_leave_record()

	def on_cancel(self):
		self.unlink_attendance_from_checkins()
		self.reset_skipped_checkins()

	def reset_skipped_checkins(self):
		"""Re-enable auto attendance for check-ins that were auto-skipped (and are still
		unlinked) for this employee & date, so the next `process_auto_attendance` run can
		reprocess them. This Attendance may have been the record that blocked them (e.g. a
		duplicate/overlapping-shift attendance), so cancelling it should un-stick them
		instead of leaving `skip_auto_attendance` set forever."""
		EmployeeCheckin = frappe.qb.DocType("Employee Checkin")
		(
			frappe.qb.update(EmployeeCheckin)
			.set(EmployeeCheckin.skip_auto_attendance, 0)
			.where(
				(EmployeeCheckin.employee == self.employee)
				& (EmployeeCheckin.skip_auto_attendance == 1)
				& (EmployeeCheckin.attendance.isnull() | (EmployeeCheckin.attendance == ""))
				& (Date(EmployeeCheckin.shift_start) == self.attendance_date)
			)
		).run()

	def validate_attendance_date(self):
		date_of_joining = frappe.db.get_value("Employee", self.employee, "date_of_joining")

		if date_of_joining and getdate(self.attendance_date) < getdate(date_of_joining):
			frappe.throw(
				_("Attendance date {0} can not be less than employee {1}'s joining date: {2}").format(
					frappe.bold(format_date(self.attendance_date)),
					frappe.bold(self.employee),
					frappe.bold(format_date(date_of_joining)),
				)
			)

	def validate_duplicate_record(self):
		duplicate = self.get_duplicate_attendance_record()

		if duplicate:
			frappe.throw(
				_("Attendance for employee {0} is already marked for the date {1}: {2}").format(
					frappe.bold(self.employee),
					frappe.bold(format_date(self.attendance_date)),
					get_link_to_form("Attendance", duplicate),
				),
				title=_("Duplicate Attendance"),
				exc=DuplicateAttendanceError,
			)

	def get_duplicate_attendance_record(self) -> str | None:
		Attendance = frappe.qb.DocType("Attendance")
		query = (
			frappe.qb.from_(Attendance)
			.select(Attendance.name)
			.where(
				(Attendance.employee == self.employee)
				& (Attendance.docstatus < 2)
				& (Attendance.attendance_date == self.attendance_date)
				& (Attendance.name != self.name)
				& (
					Attendance.half_day_status.isnull()
					| (Attendance.half_day_status == "")
					| (Attendance.modify_half_day_status == 0)
				)
			)
			.for_update()
		)

		if self.shift:
			query = query.where(
				((Attendance.shift.isnull()) | (Attendance.shift == ""))
				| (
					((Attendance.shift.isnotnull()) | (Attendance.shift != ""))
					& (Attendance.shift == self.shift)
				)
			)

		duplicate = query.run(pluck=True)

		return duplicate[0] if duplicate else None

	def validate_overlapping_shift_attendance(self):
		attendance = self.get_overlapping_shift_attendance()

		if attendance:
			frappe.throw(
				_("Attendance for employee {0} is already marked for an overlapping shift {1}: {2}").format(
					frappe.bold(self.employee),
					frappe.bold(attendance.shift),
					get_link_to_form("Attendance", attendance.name),
				),
				title=_("Overlapping Shift Attendance"),
				exc=OverlappingShiftAttendanceError,
			)

	def get_overlapping_shift_attendance(self) -> dict:
		if not self.shift:
			return {}

		Attendance = frappe.qb.DocType("Attendance")
		same_date_attendance = (
			frappe.qb.from_(Attendance)
			.select(Attendance.name, Attendance.shift)
			.where(
				(Attendance.employee == self.employee)
				& (Attendance.docstatus < 2)
				& (Attendance.attendance_date == self.attendance_date)
				& (Attendance.shift != self.shift)
				& (Attendance.name != self.name)
			)
		).run(as_dict=True)

		for d in same_date_attendance:
			if has_overlapping_timings(self.shift, d.shift):
				return d

		return {}

	def validate_employee_status(self):
		if frappe.db.get_value("Employee", self.employee, "status") == "Inactive":
			frappe.throw(_("Cannot mark attendance for an Inactive employee {0}").format(self.employee))

	def check_leave_record(self):
		LeaveApplication = frappe.qb.DocType("Leave Application")
		leave_record = (
			frappe.qb.from_(LeaveApplication)
			.select(
				LeaveApplication.leave_type,
				LeaveApplication.half_day,
				LeaveApplication.half_day_date,
				LeaveApplication.name,
			)
			.where(
				(LeaveApplication.employee == self.employee)
				& (self.attendance_date >= LeaveApplication.from_date)
				& (self.attendance_date <= LeaveApplication.to_date)
				& (LeaveApplication.status == "Approved")
				& (LeaveApplication.docstatus == 1)
			)
		).run(as_dict=True)

		if leave_record:
			for d in leave_record:
				self.leave_type = d.leave_type
				self.leave_application = d.name
				if d.half_day_date == getdate(self.attendance_date):
					self.status = "Half Day"
					frappe.msgprint(
						_("Employee {0} on Half day on {1}").format(
							self.employee, format_date(self.attendance_date)
						)
					)
				else:
					self.status = "On Leave"
					frappe.msgprint(
						_("Employee {0} is on Leave on {1}").format(
							self.employee, format_date(self.attendance_date)
						)
					)

		if self.status in ("On Leave", "Half Day"):
			if not leave_record:
				self.modify_half_day_status = 0
				self.half_day_status = "Absent"
				frappe.msgprint(
					_("No leave record found for employee {0} on {1}").format(
						self.employee, format_date(self.attendance_date)
					),
					alert=1,
				)
		elif self.leave_type:
			self.leave_type = None
			self.leave_application = None

	def validate_employee(self):
		emp = frappe.db.sql(
			"select name from `tabEmployee` where name = %s and status = 'Active'", self.employee
		)
		if not emp:
			frappe.throw(_("Employee {0} is not active or does not exist").format(self.employee))

	def unlink_attendance_from_checkins(self):
		EmployeeCheckin = frappe.qb.DocType("Employee Checkin")
		linked_logs = (
			frappe.qb.from_(EmployeeCheckin)
			.select(EmployeeCheckin.name)
			.where(EmployeeCheckin.attendance == self.name)
			.for_update()
			.run(as_dict=True)
		)

		if linked_logs:
			(
				frappe.qb.update(EmployeeCheckin)
				.set("attendance", "")
				.where(EmployeeCheckin.attendance == self.name)
			).run()

			frappe.msgprint(
				msg=_("Unlinked Attendance record from Employee Checkins: {}").format(
					", ".join(get_link_to_form("Employee Checkin", log.name) for log in linked_logs)
				),
				title=_("Unlinked logs"),
				indicator="blue",
				is_minimizable=True,
				wide=True,
			)

	def on_update(self):
		self.publish_update()

	def after_delete(self):
		self.publish_update()
		# a deleted draft Attendance can also have been the record blocking auto attendance
		# (duplicate check uses docstatus < 2); un-stick those check-ins too
		self.reset_skipped_checkins()

	def publish_update(self):
		employee_user = frappe.db.get_value("Employee", self.employee, "user_id", cache=True)
		hrms.refetch_resource("hrms:attendance_calendar_events", employee_user)


@frappe.whitelist()
def get_events(start, end, filters=None):
	employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user})
	if not employee:
		return []
	if isinstance(filters, str):
		import json

		filters = json.loads(filters)
	if not filters:
		filters = []
	filters.append(["attendance_date", "between", [get_datetime(start).date(), get_datetime(end).date()]])
	attendance_records = add_attendance(filters)
	add_holidays(attendance_records, start, end, employee)
	return attendance_records


def add_attendance(filters):
	attendance = frappe.get_list(
		"Attendance",
		fields=[
			"name",
			"'Attendance' as doctype",
			"attendance_date",
			"employee_name",
			"status",
			"docstatus",
		],
		filters=filters,
	)
	for record in attendance:
		record["title"] = f"{record.employee_name} : {record.status}"
	return attendance


def add_holidays(events, start, end, employee=None):
	holidays = get_holidays_for_employee(employee, start, end)
	if not holidays:
		return

	for holiday in holidays:
		events.append(
			{
				"doctype": "Holiday",
				"attendance_date": holiday.holiday_date,
				"title": _("Holiday") + ": " + cstr(holiday.description),
				"name": holiday.name,
				"allDay": 1,
			}
		)


def mark_attendance(
	employee,
	attendance_date,
	status,
	shift=None,
	leave_type=None,
	late_entry=False,
	early_exit=False,
	half_day_status=None,
):
	savepoint = "attendance_creation"

	try:
		frappe.db.savepoint(savepoint)
		attendance = frappe.new_doc("Attendance")
		attendance.update(
			{
				"doctype": "Attendance",
				"employee": employee,
				"attendance_date": attendance_date,
				"status": status,
				"shift": shift,
				"leave_type": leave_type,
				"late_entry": late_entry,
				"early_exit": early_exit,
				"half_day_status": half_day_status,
			}
		)
		attendance.insert()
		attendance.submit()
	except (DuplicateAttendanceError, OverlappingShiftAttendanceError):
		frappe.db.rollback(save_point=savepoint)
		return

	return attendance.name


@frappe.whitelist()
def mark_bulk_attendance(data):
	import json

	if isinstance(data, str):
		data = json.loads(data)
	data = frappe._dict(data)
	if not data.unmarked_days:
		frappe.throw(_("Please select a date."))
		return

	for date in data.unmarked_days:
		doc_dict = {
			"doctype": "Attendance",
			"employee": data.employee,
			"attendance_date": get_datetime(date),
			"status": data.status,
			"half_day_status": "Absent" if data.status == "Half Day" else None,
		}
		attendance = frappe.get_doc(doc_dict).insert()
		attendance.submit()


@frappe.whitelist()
def get_unmarked_days(employee, from_date, to_date, exclude_holidays=0):
	joining_date, relieving_date = frappe.get_cached_value(
		"Employee", employee, ["date_of_joining", "relieving_date"]
	)

	from_date = max(getdate(from_date), joining_date or getdate(from_date))
	to_date = min(getdate(to_date), relieving_date or getdate(to_date))

	records = frappe.get_all(
		"Attendance",
		fields=["attendance_date", "employee"],
		filters=[
			["attendance_date", ">=", from_date],
			["attendance_date", "<=", to_date],
			["employee", "=", employee],
			["docstatus", "!=", 2],
		],
	)

	marked_days = [getdate(record.attendance_date) for record in records]

	if cint(exclude_holidays):
		holiday_dates = get_holiday_dates_for_employee(employee, from_date, to_date)
		holidays = [getdate(record) for record in holiday_dates]
		marked_days.extend(holidays)

	unmarked_days = []

	while from_date <= to_date:
		if from_date not in marked_days:
			unmarked_days.append(from_date)

		from_date = add_days(from_date, 1)

	return unmarked_days
