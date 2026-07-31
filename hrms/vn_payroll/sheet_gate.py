# Copyright (c) 2026, Miyano Việt Nam.
"""CỔNG LƯƠNG — buộc phiếu lương phải khớp Bảng Công Tháng đã chốt.

Yêu cầu là "lương lấy số từ bảng đã chốt". Cách rẻ và an toàn hơn hẳn việc đổi nguồn đọc của
Salary Slip (phải fork 4 hàm lõi upstream rồi tự gánh mỗi lần merge): **không sửa một dòng công
thức lương nào**, mà siết hai đầu:

1. `require_submitted_sheet` — kỳ lương chưa có Bảng Công Tháng đã chốt phủ nhân viên đó thì không
   cho lập phiếu. Hết cảnh tính lương trên số công chưa ai soát.
2. `reconcile_with_sheet` — so số công bảng đã chốt ghi nhận với `payment_days` mà controller vừa
   tính từ Attendance; lệch là chặn, kèm số liệu hai bên.

`hrms.hr.period_lock` đã đóng băng kỳ khi chốt nên hai nguồn không thể trôi khỏi nhau; cổng này là
cái máy kiểm chứng điều đó cho TỪNG phiếu thay vì tin tưởng suông.

CÔNG THỨC ĐỐI SOÁT — chốt bằng dữ liệu thật, không suy diễn:

    payment_days  ==  cột "Tổng công" của nhân viên trong bảng đã chốt

Đo trên 12 phiếu lương thật T6+T7/2026 của site: **10/12 khớp tuyệt đối**. Hai phiếu còn lại
(HR-EMP-00002) lệch đúng 0,5 vì ngày `1/2P` — nghỉ phép năm nửa ngày, CÓ LƯƠNG, có đơn đã duyệt —
lại mang `half_day_status="Absent"`, nên `get_half_absent_days` trừ 0,5 của nửa ngày phép có lương.
Bảng ghi 20,5 công còn phiếu trả 20,0.

Đó là lệch THẬT, do DỮ LIỆU SEED demo ghi sai chứ không phải đường code sai (đường đơn nghỉ chạy
thật cho ra "Present" — xem `test_half_day_leave_payroll.py`). Cổng phải chặn chứ không được nới
công thức để chiều nó: chính loại lệch âm thầm này là lý do tính năng tồn tại.

Cả hai vế đều dùng `total_working_days` / `Tổng công` đã loại ngày nghỉ lễ - cuối tuần (bảng đếm
"Nghỉ lễ" ở cột riêng, payroll không tính ngày nghỉ vào `total_working_days`), nên so thẳng được.

Cổng TẮT mặc định. Bật bằng cờ site config `hrms_enforce_sheet_gate: 1` sau khi đối soát chạy sạch
trên dữ liệu thật — bật khi còn phiếu lệch thì không ai lập được lương.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from hrms.hr.report.monthly_attendance_report.monthly_attendance_report import (
	TOTAL_PAID,
	get_sheet_rows,
)

TOLERANCE = 0.001  # sai số làm tròn float, KHÔNG phải dung sai nghiệp vụ
CONFIG_FLAG = "hrms_enforce_sheet_gate"


def gate_enabled() -> bool:
	return bool(cint(frappe.conf.get(CONFIG_FLAG) or 0)) and not frappe.flags.get("skip_sheet_gate")


def submitted_sheet_for(employee: str, start, end) -> str | None:
	"""Bảng Công Tháng ĐÃ CHỐT phủ trọn kỳ lương của nhân viên này, hoặc None.

	Phải phủ cả hai đầu kỳ: một bảng chỉ chốt nửa kỳ thì phần còn lại vẫn sửa được, nên chưa đủ
	để bảo đảm số công đứng yên."""
	from hrms.hr.period_lock import locking_sheet

	first = locking_sheet(employee, start)
	return first if first and first == locking_sheet(employee, end) else None


def sheet_row_for(employee: str, start) -> dict | None:
	"""Hàng của nhân viên trong bảng công tháng đó — qua `get_sheet_rows`, đúng nguồn suy diễn
	mà chính Bảng Công Tháng dùng để chụp ảnh."""
	start = getdate(start)
	rows = get_sheet_rows(
		{
			"month": start.month,
			"year": start.year,
			"company": frappe.db.get_value("Employee", employee, "company"),
		}
	)
	return next((r for r in rows if r["employee"] == employee), None)


def paid_days_in_sheet(row: dict) -> float:
	"""Số ngày ĐƯỢC TRẢ LƯƠNG bảng ghi nhận (đi làm + mọi nghỉ có lương; không gồm nghỉ lễ)."""
	return flt(row["totals"].get(TOTAL_PAID, 0.0))


def require_submitted_sheet(doc, method=None):
	"""Chặn lập phiếu lương khi kỳ chấm công chưa được chốt."""
	if not submitted_sheet_for(doc.employee, doc.start_date, doc.end_date):
		frappe.throw(
			_(
				"Kỳ lương {0} - {1} chưa có Bảng Công Tháng nào được chốt cho nhân viên {2}. "
				"Phải soát công và chốt công trước khi tính lương."
			).format(
				frappe.utils.formatdate(doc.start_date),
				frappe.utils.formatdate(doc.end_date),
				frappe.bold(doc.employee),
			),
			title=_("Chưa chốt công"),
		)


def reconcile_with_sheet(doc, method=None):
	"""So `payment_days` của phiếu với số công trong bảng đã chốt; lệch thì chặn."""
	sheet = submitted_sheet_for(doc.employee, doc.start_date, doc.end_date)
	if not sheet:
		return  # `require_submitted_sheet` lo phần chặn; ở đây không có gì để đối soát

	row = sheet_row_for(doc.employee, doc.start_date)
	if not row:
		frappe.throw(
			_("Nhân viên {0} không có hàng nào trong Bảng Công Tháng đã chốt {1}.").format(
				frappe.bold(doc.employee), sheet
			),
			title=_("Thiếu trong bảng công"),
		)

	from_sheet = paid_days_in_sheet(row)
	from_slip = flt(doc.get("payment_days"))

	if abs(from_sheet - from_slip) > TOLERANCE:
		frappe.throw(
			_(
				"Phiếu lương không khớp Bảng Công Tháng đã chốt {0}.<br>"
				"Bảng đã chốt: <b>{1}</b> công được trả<br>"
				"Phiếu lương: <b>{2}</b> (payment_days)<br>"
				"Lệch <b>{3}</b> ngày. Hãy mở lại bảng chốt, soát công rồi chốt lại."
			).format(sheet, from_sheet, from_slip, round(from_slip - from_sheet, 3)),
			title=_("Lệch giữa bảng công và phiếu lương"),
		)


def gate(doc, method=None):
	"""Điểm vào duy nhất cho `doc_events["Salary Slip"]["validate"]`."""
	if not gate_enabled():
		return
	if not (doc.get("employee") and doc.get("start_date") and doc.get("end_date")):
		return
	require_submitted_sheet(doc, method)
	reconcile_with_sheet(doc, method)
