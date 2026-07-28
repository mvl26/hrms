"""Dựng lại Attendance của một tháng ĐÚNG ĐƯỜNG: checkin -> job, không tạo tay.

Attendance tạo thẳng bằng script/tay thì không liên kết với Employee Checkin: cột `attendance`
trên checkin rỗng, và không có gì chứng minh con số công đến từ máy chấm công. Công cụ này xoá
các bản tạo tay của một tháng rồi để `Shift Type.process_auto_attendance()` sinh lại từ checkin.

GIỮ NGUYÊN các bản có `leave_application` — ngày nghỉ phép do Leave Application sinh ra, đó mới
là nguồn đúng; job auto-attendance cố tình bỏ qua ngày đã có đơn nghỉ và sẽ KHÔNG dựng lại chúng.

CHẠY (từ thư mục frappe-bench):

  # 1) Chạy thử — chỉ in kế hoạch, không đổi gì:
  bench --site <site> execute hrms.rebuild_attendance_from_checkin.rebuild \
        --kwargs "{'year': 2026, 'month': 6}"

  # 2) Làm thật (sao lưu ra JSON trước khi xoá):
  bench --site <site> execute hrms.rebuild_attendance_from_checkin.rebuild \
        --kwargs "{'year': 2026, 'month': 6, 'apply': True}"

  # 3) Làm thật và ĐỂ auto-attendance bật tiếp sau khi xong:
  bench --site <site> execute hrms.rebuild_attendance_from_checkin.rebuild \
        --kwargs "{'year': 2026, 'month': 6, 'apply': True, 'keep_enabled': True}"

CẢNH BÁO khi dùng `keep_enabled`: job chạy hằng giờ sẽ tự đẩy `last_sync_of_checkin` lên hiện
tại rồi chấm **Vắng** cho mọi ngày không có checkin từ `process_attendance_after` trở đi. Với ca
chỉ gán cho nhân viên demo (không ai chấm công tiếp) thì đó là hàng loạt bản ghi rác. Mặc định
công cụ trả cờ về trạng thái cũ sau khi backfill xong.

Cửa sổ tan ca (`allow_check_out_after_shift_end_time`) được nới nếu tháng đó có lượt chấm ra
muộn hơn cửa sổ hiện tại — nếu không, lượt tan ca tăng ca không gắn được vào ca và ngày đó mất
giờ ra, dễ bị chấm nhầm thành nửa ngày/vắng. Thay đổi này được GIỮ LẠI (không hoàn tác) vì nó
là sửa cấu hình đúng, không phải trạng thái tạm.
"""

import datetime
import json
import os
from calendar import monthrange

import frappe
from frappe.utils import get_datetime, getdate

FIELDS_BACKUP = [
	"name",
	"employee",
	"employee_name",
	"attendance_date",
	"status",
	"leave_type",
	"leave_application",
	"in_time",
	"out_time",
	"working_hours",
	"shift",
	"custom_attendance_code",
	"custom_morning_code",
	"custom_afternoon_code",
	"docstatus",
]
CHECKOUT_HEADROOM_MINUTES = 60  # nới thêm quá lượt tan ca muộn nhất, cho chắc


def month_bounds(year, month):
	start = getdate(f"{year}-{month:02d}-01")
	return start, getdate(f"{year}-{month:02d}-{monthrange(year, month)[1]:02d}")


def guard_payroll(start, end):
	"""Tháng đã chạy lương thì không được dựng lại chấm công — số đã chốt sẽ lệch."""
	slips = frappe.get_all(
		"Salary Slip",
		filters={"docstatus": ["<", 2], "start_date": ["<=", end], "end_date": [">=", start]},
		fields=["name"],
		limit=5,
	)
	if slips:
		frappe.throw(
			f"Đã có Salary Slip phủ khoảng {start}..{end} (vd {slips[0].name}). "
			"Không dựng lại chấm công cho tháng đã chạy lương."
		)


def shift_employees(shift, start, end):
	"""Nhân viên thuộc ca trong kỳ: có Shift Assignment gối lên kỳ, hoặc lấy ca này làm mặc định.

	Phải quét theo nhân viên chứ không theo cột `shift` của Attendance: bản tạo tay có thể bỏ
	trống `shift` và sẽ lọt lưới nếu lọc theo cột đó.
	"""
	assigned = frappe.get_all(
		"Shift Assignment",
		filters={
			"shift_type": shift,
			"docstatus": 1,
			"start_date": ["<=", end],
		},
		or_filters=[["end_date", "is", "not set"], ["end_date", ">=", start]],
		pluck="employee",
	)
	default = frappe.get_all("Employee", filters={"default_shift": shift}, pluck="name")
	return sorted(set(assigned) | set(default))


def snapshot(start, end, employees):
	if not employees:
		return []
	return frappe.get_all(
		"Attendance",
		filters={"attendance_date": ["between", [start, end]], "employee": ["in", employees]},
		fields=FIELDS_BACKUP,
		order_by="employee, attendance_date",
	)


def checkin_filters(start, end):
	return {"time": ["between", [str(start), f"{end} 23:59:59"]]}


def summarise(start, end, employees):
	linked = frappe.db.count("Employee Checkin", {**checkin_filters(start, end), "attendance": ["is", "set"]})
	total = frappe.db.count("Employee Checkin", checkin_filters(start, end))
	statuses = frappe.get_all(
		"Attendance",
		filters={
			"attendance_date": ["between", [start, end]],
			"employee": ["in", employees],
			"docstatus": ["<", 2],
		},
		fields=["status", "count(name) as c"],
		group_by="status",
	)
	return {
		"checkin_linked": f"{linked}/{total}",
		"attendance": {s.status: s.c for s in statuses},
	}


def widen_checkout_window(shift_doc, start, end):
	"""Trả về số phút cần nới, hoặc 0 nếu cửa sổ hiện tại đã đủ."""
	latest = frappe.db.sql(
		"""select max(time(time)) from `tabEmployee Checkin`
		   where time between %s and %s and log_type='OUT'""",
		(str(start), f"{end} 23:59:59"),
	)[0][0]
	if not latest:
		return 0
	shift_end = (datetime.datetime.min + shift_doc.end_time).time()
	latest_t = (datetime.datetime.min + latest).time()
	overrun = (
		datetime.datetime.combine(datetime.date.min, latest_t)
		- datetime.datetime.combine(datetime.date.min, shift_end)
	).total_seconds() / 60
	needed = int(overrun) + CHECKOUT_HEADROOM_MINUTES
	return needed if needed > (shift_doc.allow_check_out_after_shift_end_time or 0) else 0


def run_auto_attendance_for_period(shift, start, end, keep_enabled=False):
	"""Cho job sinh Attendance từ checkin trong đúng khoảng ngày, rồi trả cờ về như cũ.

	Khoá `process_attendance_after`/`last_sync_of_checkin` vào đúng kỳ để job không quét lan sang
	tháng khác. Nới cửa sổ tan ca nếu kỳ đó có lượt chấm ra muộn hơn cửa sổ hiện tại — không nới
	thì lượt tan ca tăng ca không gắn được vào ca và ngày đó mất giờ ra.

	Trả cờ `enable_auto_attendance` về trạng thái cũ trừ khi `keep_enabled`: để bật thì job hằng
	giờ sẽ đẩy mốc quét lên hiện tại rồi chấm Vắng cho mọi ngày không có checkin.
	"""
	shift_doc = frappe.get_doc("Shift Type", shift)
	previous = {
		"enable_auto_attendance": shift_doc.enable_auto_attendance,
		"process_attendance_after": shift_doc.process_attendance_after,
		"last_sync_of_checkin": shift_doc.last_sync_of_checkin,
	}
	widen_to = widen_checkout_window(shift_doc, start, end)

	if widen_to:
		shift_doc.allow_check_out_after_shift_end_time = widen_to
	shift_doc.enable_auto_attendance = 1
	shift_doc.process_attendance_after = start - datetime.timedelta(days=1)
	shift_doc.last_sync_of_checkin = get_datetime(f"{end} 23:59:59")
	shift_doc.save(ignore_permissions=True)
	# commit chủ đích: công cụ chạy ngoài request cycle (bench execute), ghi từng phần để lần chạy dài không mất việc đã làm
	frappe.db.commit()  # nosemgrep

	# gắn lại ca cho lượt chấm từng rơi ngoài cửa sổ (validate -> fetch_shift)
	for name in frappe.get_all(
		"Employee Checkin", filters={**checkin_filters(start, end), "shift": ["is", "not set"]}, pluck="name"
	):
		frappe.get_doc("Employee Checkin", name).save(ignore_permissions=True)
	# commit chủ đích: công cụ chạy ngoài request cycle (bench execute), ghi từng phần để lần chạy dài không mất việc đã làm
	frappe.db.commit()  # nosemgrep

	frappe.db.set_value(
		"Employee Checkin", checkin_filters(start, end), "skip_auto_attendance", 0, update_modified=False
	)
	# commit chủ đích: công cụ chạy ngoài request cycle (bench execute), ghi từng phần để lần chạy dài không mất việc đã làm
	frappe.db.commit()  # nosemgrep

	frappe.get_doc("Shift Type", shift).process_auto_attendance()
	# commit chủ đích: công cụ chạy ngoài request cycle (bench execute), ghi từng phần để lần chạy dài không mất việc đã làm
	frappe.db.commit()  # nosemgrep

	if not keep_enabled:
		frappe.db.set_value("Shift Type", shift, previous, update_modified=False)
		# commit chủ đích: công cụ chạy ngoài request cycle (bench execute), ghi từng phần để lần chạy dài không mất việc đã làm
		frappe.db.commit()  # nosemgrep
	return {"widened_checkout_window_to": widen_to or None, "auto_attendance_kept_on": bool(keep_enabled)}


def rebuild(year, month, shift="Ca Hành Chính", apply=False, keep_enabled=False):
	year, month = int(year), int(month)
	start, end = month_bounds(year, month)
	shift_doc = frappe.get_doc("Shift Type", shift)

	employees = shift_employees(shift, start, end)
	before = snapshot(start, end, employees)
	keep = [a for a in before if a.leave_application]
	drop = [a for a in before if not a.leave_application]
	shiftless = frappe.get_all(
		"Employee Checkin", filters={**checkin_filters(start, end), "shift": ["is", "not set"]}, pluck="name"
	)
	widen_to = widen_checkout_window(shift_doc, start, end)

	plan = {
		"period": f"{start}..{end}",
		"shift": shift,
		"employees_in_shift": len(employees),
		"attendance_total": len(before),
		"attendance_keep_from_leave": len(keep),
		"attendance_to_delete": len(drop),
		"checkins_without_shift": len(shiftless),
		"widen_checkout_window_to": widen_to or "không cần",
		"before": summarise(start, end, employees),
	}
	if not apply:
		plan["note"] = "CHẠY THỬ — chưa đổi gì. Thêm 'apply': True để làm thật."
		print(frappe.as_json(plan))
		return plan

	guard_payroll(start, end)

	backup_path = os.path.join(
		frappe.get_site_path("private", "files"), f"attendance_backup_{year}_{month:02d}.json"
	)
	# đường dẫn do quản trị viên truyền khi chạy bench execute, không đến từ request
	with open(backup_path, "w") as fh:  # nosemgrep
		json.dump(before, fh, indent=1, default=str, ensure_ascii=False)
	plan["backup"] = backup_path

	for a in drop:
		doc = frappe.get_doc("Attendance", a.name)
		if doc.docstatus == 1:
			doc.cancel()
		frappe.delete_doc("Attendance", a.name, force=True, ignore_permissions=True)
	# commit chủ đích: công cụ chạy ngoài request cycle (bench execute), ghi từng phần để lần chạy dài không mất việc đã làm
	frappe.db.commit()  # nosemgrep

	plan.update(run_auto_attendance_for_period(shift, start, end, keep_enabled=keep_enabled))
	plan["checkins_still_without_shift"] = frappe.db.count(
		"Employee Checkin", {**checkin_filters(start, end), "shift": ["is", "not set"]}
	)
	plan["auto_attendance_left"] = "BẬT" if keep_enabled else "đã trả về trạng thái cũ"
	plan["after"] = summarise(start, end, employees)
	print(frappe.as_json(plan))
	return plan
