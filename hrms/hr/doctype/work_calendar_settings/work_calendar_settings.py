# Copyright (c) 2026, Miyano Việt Nam.
"""Nguồn sự thật cho lịch làm việc — Holiday List chỉ là kết quả sinh ra từ đây.

Ba loại ngày, ba nguồn tách bạch (spec `docs/spec/work-schedule-and-holiday-separation.md`):

- **ngày làm việc trong tuần** — khai trên `Shift Type.custom_working_days`; ô ở đây chỉ là lịch
  mặc định cho nhân viên chưa phân ca;
- **ngoài lịch tuần** (T7/CN) — suy ra, không lưu ở đâu cả;
- **ngày đặc biệt** — bảng `calendar_days`: `Nghỉ lễ` (đẩy xuống Holiday List) và `Làm bù` (ngày
  cuối tuần phải đi làm, KHÔNG xuống Holiday List vì nó là ngày *làm việc*).

Vì sao chính sách phải nằm ở một doctype thay vì là tham số truyền tay lúc chạy generator: chạy lại
mà quên tham số là lịch âm thầm đổi, mà lịch là MẪU SỐ của phiếu lương.
"""

from calendar import monthrange

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from hrms.hr.doctype.work_calendar_day.work_calendar_day import DAY_TYPE_HOLIDAY, DAY_TYPE_MAKE_UP


class WorkCalendarSettings(Document):
	def validate(self):
		self.validate_years()
		self.validate_no_duplicate_dates()
		self.validate_period_not_locked()

	def validate_years(self):
		"""Ngày phải nằm đúng trong năm đã khai — sai năm thì sinh lịch sẽ hụt ngày."""
		for row in self.calendar_days:
			if row.holiday_date and row.year and getdate(row.holiday_date).year != int(row.year):
				frappe.throw(
					_("Dòng {0}: ngày {1} không thuộc năm {2}.").format(
						row.idx, frappe.utils.formatdate(row.holiday_date), row.year
					)
				)

	def validate_no_duplicate_dates(self):
		"""Một ngày không thể vừa nghỉ vừa làm bù — để lọt thì kết quả tuỳ thứ tự dòng."""
		seen = {}
		for row in self.calendar_days:
			if not row.holiday_date:
				continue
			day = getdate(row.holiday_date)
			if day in seen:
				frappe.throw(
					_("Ngày {0} khai hai lần (dòng {1} và {2}).").format(
						frappe.utils.formatdate(day), seen[day], row.idx
					)
				)
			seen[day] = row.idx

	def validate_period_not_locked(self):
		"""Không cho sửa lịch của kỳ đã chốt công.

		Bảng Công Tháng đã ký mà đổi lịch quá khứ thì bảng và phiếu lương lệch nhau trong im lặng.

		Hỏi THẲNG `Monthly Attendance Sheet` đã submit phủ ngày bị sửa, không đi vòng qua
		`period_lock.locking_sheet`: hàm đó khoá theo PHÒNG BAN của một nhân viên cụ thể, nên nếu
		bảng đã chốt thuộc phòng ban khác thì việc sửa lịch vẫn lọt. Lịch là chính sách TOÀN CÔNG
		TY, nên câu hỏi đúng là 'có kỳ nào đã chốt phủ ngày này không', không phải 'kỳ của người
		này đã chốt chưa'.
		"""
		saved = self.get_doc_before_save()
		before = (
			{getdate(r.holiday_date): r.day_type for r in saved.calendar_days if r.holiday_date}
			if saved
			else {}
		)
		now = {getdate(r.holiday_date): r.day_type for r in self.calendar_days if r.holiday_date}
		changed = {d for d in set(before) | set(now) if before.get(d) != now.get(d)}

		for day in sorted(changed):
			sheet = frappe.db.get_value(
				"Monthly Attendance Sheet",
				{
					"docstatus": 1,
					"company": self.company,
					"from_date": ["<=", day],
					"to_date": [">=", day],
				},
				"name",
			)
			if sheet:
				frappe.throw(
					_("Ngày {0} thuộc kỳ đã chốt công ({1}). Huỷ chốt kỳ trước khi sửa lịch.").format(
						frappe.utils.formatdate(day), sheet
					)
				)

	def get_calendar_days(self, year: int, day_type: str) -> dict[str, str]:
		"""{"YYYY-MM-DD": "Tên ngày"} của riêng `year` và riêng một loại."""
		return {
			str(getdate(row.holiday_date)): row.description
			for row in self.calendar_days
			if row.holiday_date and int(row.year or 0) == int(year) and row.day_type == day_type
		}

	def get_public_holidays(self, year: int) -> dict[str, str]:
		"""Ngày nghỉ lễ nhập tay của `year` — dạng generator nhận."""
		return self.get_calendar_days(year, DAY_TYPE_HOLIDAY)

	def get_make_up_days(self, year: int) -> dict[str, str]:
		"""Ngày làm bù của `year`. KHÔNG xuống Holiday List — đây là ngày làm việc."""
		return self.get_calendar_days(year, DAY_TYPE_MAKE_UP)

	@frappe.whitelist()
	def working_days_preview(self, year: int | str | None = None) -> dict:
		"""{tháng: {"before": n, "after": n}} — số ngày công của từng tháng, trước và sau khi lưu.

		Khai một ngày làm bù mà quên khai ngày nghỉ ghép đi kèm là im lặng đổi lương cả tháng. Bảng
		này bắt đúng lỗi đó, trước khi HR bấm lưu.
		"""
		from hrms.hr.work_schedule import company_default_weekdays, scheduled_dates

		year = int(year or self.generate_for_year or frappe.utils.now_datetime().year)
		weekdays = company_default_weekdays() or frozenset()
		saved = self.get_doc_before_save()
		before_exceptions = (
			{getdate(r.holiday_date) for r in saved.calendar_days if r.day_type == DAY_TYPE_MAKE_UP}
			if saved
			else set()
		)
		after_exceptions = {
			getdate(r.holiday_date) for r in self.calendar_days if r.day_type == DAY_TYPE_MAKE_UP
		}

		out = {}
		for month in range(1, 13):
			last = monthrange(year, month)[1]
			start, end = f"{year}-{month:02d}-01", f"{year}-{month:02d}-{last:02d}"
			base = scheduled_dates(weekdays, start, end)
			window = (getdate(start), getdate(end))
			out[month] = {
				"before": len(base | {d for d in before_exceptions if window[0] <= d <= window[1]}),
				"after": len(base | {d for d in after_exceptions if window[0] <= d <= window[1]}),
			}
		return out


@frappe.whitelist()
def generate_holiday_list(year: int | str | None = None, company: str | None = None) -> str:
	"""Sinh / cập nhật Holiday List của `year` theo đúng chính sách đang lưu. Trả tên list.

	Idempotent: chạy lại không nhân đôi ngày. Đây là con đường DUY NHẤT nên dùng để tạo lịch, vì nó
	luôn kéo chính sách từ một chỗ. Chỉ dòng loại `Nghỉ lễ` được đẩy xuống — ngày `Làm bù` là ngày
	làm việc, nhét vào bảng ngày nghỉ là sai ngay từ tên gọi.
	"""
	settings = frappe.get_single("Work Calendar Settings")
	year = int(year or settings.generate_for_year or frappe.utils.now_datetime().year)
	company = company or settings.company
	if not company:
		frappe.throw(_("Hãy chọn Công ty trong Cấu hình lịch làm việc trước."))

	# import tại chỗ: generator là module cấp app, tránh vòng import khi doctype được nạp sớm
	from hrms.setup_vn_holiday import create_vn_holiday_list

	name = create_vn_holiday_list(year, company, extra_holidays=settings.get_public_holidays(year))
	frappe.msgprint(_("Đã sinh / cập nhật {0}.").format(name), alert=True)
	return name
