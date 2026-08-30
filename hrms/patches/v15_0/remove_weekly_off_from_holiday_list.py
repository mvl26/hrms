# Copyright (c) 2026, Miyano Việt Nam.
"""Gỡ dòng nghỉ cuối tuần khỏi Holiday List — lịch tuần nay thuộc `Shift Type`.

**KHÔNG `git revert` được** (xoá dữ liệu), nên patch tự chặn và tự đối soát: chỉ chạy khi lịch tuần
đã khai đủ, và **abort** nếu bất kỳ con số lương nào lệch. Idempotent — chạy lại khi đã sạch là
no-op.

Về mặt số học đây là no-op: `set_working_days` đặt mẫu số tuyệt đối từ lịch tuần chứ không cộng/trừ
theo Holiday List, nên gỡ hay giữ các dòng cuối tuần đều cho cùng con số. Bước đối soát ở cuối là để
chứng minh điều đó trên dữ liệu thật, không phải để hy vọng.

Spec: `docs/spec/work-schedule-and-holiday-separation.md` §10.
"""

import re

import frappe
from frappe.utils import flt

FIELDS = ("total_working_days", "payment_days", "absent_days", "leave_without_pay")
HTML_TAG = re.compile(r"<[^>]+>")


def live_holiday_lists() -> list[str]:
	"""Chỉ những Holiday List đang được Company hoặc Employee trỏ tới.

	Danh sách rác của test (`Salary Slip Test Holiday List`) KHÔNG đụng tới — nó không nằm trên
	đường chạy thật, sửa nó chỉ làm nhiễu chẩn đoán về sau.
	"""
	names = set(frappe.get_all("Company", pluck="default_holiday_list")) | set(
		frappe.get_all("Employee", pluck="holiday_list")
	)
	return sorted(n for n in names if n)


def payroll_numbers(slip_name: str) -> dict:
	"""Bốn con số lương, tính lại qua ĐÚNG đường thật (controller rồi hook).

	Cố ý không `run_method("validate")`: nó kéo theo cả engine MVL và cổng đối soát bảng công, có
	thể throw vì lý do chẳng liên quan gì tới lịch và làm hỏng phép đo.
	"""
	from hrms.vn_payroll.salary_slip_hook import set_working_days

	src = frappe.db.get_value(
		"Salary Slip", slip_name, ["employee", "company", "start_date", "end_date"], as_dict=True
	)
	slip = frappe.new_doc("Salary Slip")
	slip.employee, slip.company = src.employee, src.company
	slip.start_date, slip.end_date = src.start_date, src.end_date
	slip.get_working_days_details()
	set_working_days(slip)
	return {f: flt(slip.get(f)) for f in FIELDS}


def guard_work_schedule_is_configured(lists: list[str]) -> None:
	"""CHẶN TRƯỚC: chưa khai lịch tuần mà gỡ dòng cuối tuần là phá mẫu số của cả công ty."""
	from hrms.hr.work_schedule import company_default_weekdays, shift_weekdays

	if company_default_weekdays():
		return
	shifts = frappe.get_all("Shift Type", filters={"enable_auto_attendance": 1}, pluck="name")
	missing = [s for s in shifts if shift_weekdays(s) is None]
	if missing:
		names = ", ".join(missing)
		frappe.throw(
			f"Chưa khai ngày làm việc trong tuần cho ca: {names}. "
			"Khai trên Shift Type (hoặc đặt lịch mặc định ở Cấu hình lịch làm việc) rồi migrate lại."
		)


def strip_html_from_descriptions(lists: list[str]) -> int:
	"""Dọn HTML của trình soạn thảo lẫn trong `description` — nó hiện thô trên báo cáo, bản in và PWA."""
	cleaned = 0
	for row in frappe.get_all("Holiday", filters={"parent": ("in", lists)}, fields=["name", "description"]):
		if row.description and "<" in row.description:
			clean = HTML_TAG.sub("", row.description).strip()
			frappe.db.set_value("Holiday", row.name, "description", clean, update_modified=False)
			cleaned += 1
	return cleaned


def execute():
	lists = live_holiday_lists()
	if not lists:
		return

	guard_work_schedule_is_configured(lists)

	before = {
		s.name: {f: flt(s.get(f)) for f in FIELDS}
		for s in frappe.get_all("Salary Slip", fields=["name", *FIELDS])
	}

	frappe.db.delete("Holiday", {"parent": ("in", lists), "weekly_off": 1})

	# Gỡ ghim Employee.holiday_list -> mỗi năm chỉ còn MỘT chỗ phải trỏ lại (Company default).
	# `work_schedule.holiday_list_for` phân giải theo NGÀY nên không cần link trên từng nhân viên.
	frappe.db.set_value("Employee", {"holiday_list": ("in", lists)}, "holiday_list", None)

	strip_html_from_descriptions(lists)

	for name in lists:
		frappe.get_doc("Holiday List", name).save(ignore_permissions=True)  # cập nhật total_holidays
	frappe.clear_cache()

	for name, want in before.items():
		got = payroll_numbers(name)
		if got != want:
			frappe.db.rollback()
			frappe.throw(f"Phiếu lương {name} lệch sau di trú: {want} -> {got}. Đã rollback.")
