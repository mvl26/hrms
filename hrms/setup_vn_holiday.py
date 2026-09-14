"""Sinh Holiday List Việt Nam — CHỈ ngày nghỉ lễ.

Một Holiday List cho mỗi (công ty, năm), gồm:
  - lễ dương cố định của Điều 112 BLLĐ 2019 (Tết dương, 30/4, 1/5, Quốc khánh x2);
  - lễ nhập tay truyền vào qua `extra_holidays` (Tết Âm, Giỗ Tổ, lễ riêng công ty, nghỉ ghép);
  - nghỉ bù (Điều 112 khoản 3) khi một ngày lễ rơi vào ngày KHÔNG làm việc.

Danh sách này KHÔNG còn chứa ngày nghỉ cuối tuần: ngày làm việc trong tuần nay thuộc `Shift Type`
(xem `hrms/hr/work_schedule.py`). Nhờ vậy quên tạo lịch của năm mới chỉ làm mất ký hiệu NL, chứ
không biến mọi thứ Bảy thành ngày công.

Idempotent (chạy lại không nhân đôi ngày). Chỉ chạy theo yêu cầu — KHÔNG gắn vào migrate/install,
vì tạo Holiday List là tạo dữ liệu công ty (ask-first trên site thật).

Dùng:
  bench --site <s> execute hrms.setup_vn_holiday.create_vn_holiday_list \
        --kwargs "{'year': 2026, 'company': 'Miyano'}"
"""

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import getdate

from hrms.hr.work_schedule import company_default_weekdays, scheduled_dates

# (month, day) of the fixed SOLAR public holidays. Quốc khánh = 2 ngày (01/09 + 02/09).
SOLAR_HOLIDAYS = [
	(1, 1),  # Tết Dương lịch
	(4, 30),  # Ngày Giải phóng miền Nam
	(5, 1),  # Quốc tế Lao động
	(9, 1),  # Quốc khánh (ngày liền kề)
	(9, 2),  # Quốc khánh
]

SOLAR_LABELS = {
	(1, 1): "Tết Dương lịch",
	(4, 30): "Ngày Giải phóng miền Nam",
	(5, 1): "Quốc tế Lao động",
	(9, 1): "Nghỉ Quốc khánh",
	(9, 2): "Quốc khánh",
}


def vn_holiday_list_name(company, year) -> str:
	"""Tên Holiday List của một (công ty, năm) — quy ước đặt tên, khai báo MỘT chỗ.

	Generator đặt tên theo quy ước này, và `work_schedule.holiday_list_for` dựa vào đúng quy ước đó
	để tìm lịch của năm được hỏi (mỗi năm một list). Để hai bên tự đoán tên là mời một ngày nào đó
	chúng lệch nhau và cả năm cũ mất sạch ký hiệu NL.
	"""
	return f"VN {company} {int(year)}"


def create_vn_holiday_list(year, company, name=None, extra_holidays=None):
	"""Create/refresh a VN Holiday List for `year`. Returns its name. Idempotent.

	`extra_holidays` = {"YYYY-MM-DD": "Nhãn"} cho những ngày lễ KHÔNG cố định theo dương lịch
	(Tết Âm lịch, Giỗ Tổ) — chúng trôi mỗi năm nên không hardcode được; truyền vào từ ngoài và
	vẫn được áp cùng quy tắc nghỉ bù của Điều 112 khoản 3 như lễ dương.
	"""
	year = int(year)
	list_name = name or vn_holiday_list_name(company, year)
	settings = frappe.get_single("Work Calendar Settings")
	make_up_days = {getdate(d) for d in settings.get_make_up_days(year)}

	if frappe.db.exists("Holiday List", list_name):
		doc = frappe.get_doc("Holiday List", list_name)
	else:
		doc = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": list_name,
				"from_date": f"{year}-01-01",
				"to_date": f"{year}-12-31",
			}
		)

	holiday_dates = {getdate(h.holiday_date) for h in doc.holidays if not h.weekly_off}
	bu_descriptions = {h.description for h in doc.holidays if not h.weekly_off}

	# Mọi ngày lễ của năm, biết TRƯỚC khi đi tìm ngày bù. Nếu chỉ tránh `holiday_dates` (các ngày
	# đã thêm) thì ngày bù của một lễ xử lý sớm sẽ rơi trúng một lễ chưa tới lượt và nuốt mất nó:
	# vd 30/4/2028 rơi Chủ nhật -> ngày bù nhảy vào đúng 1/5, và Quốc tế Lao động biến mất.
	scheduled_holidays = {getdate(f"{year}-{mm:02d}-{dd:02d}") for mm, dd in SOLAR_HOLIDAYS}
	scheduled_holidays |= {getdate(ds) for ds in (extra_holidays or {})}

	weekdays = company_default_weekdays() or frozenset()

	def is_scheduled(d) -> bool:
		"""Ngày có nằm trong lịch tuần không — kể cả ngoại lệ làm bù."""
		return d in scheduled_dates(weekdays, d, d) or d in make_up_days

	def add_public_holiday(d, label):
		"""Một ngày nghỉ lễ; nếu rơi vào ngày KHÔNG làm việc thì sinh nghỉ bù (Điều 112 khoản 3).

		Hỏi lịch tuần chứ không hỏi cờ `weekly_off` của chính danh sách này — danh sách nay chỉ còn
		ngày lễ nên không còn cờ nào để hỏi. Kết quả bảo đảm một bất biến quan trọng: dòng lễ CHỈ
		nằm trên ngày làm việc, nhờ đó không thể cộng khống một ngày công vào lương."""
		if not is_scheduled(d):
			bu_label = f"Nghỉ bù {label}"
			if bu_label in bu_descriptions:
				return  # đã có ngày bù cho lễ này -> chạy lại không nhân đôi
			bu = d + timedelta(days=1)
			# bỏ qua ngày ngoài lịch tuần + mọi ngày lễ khác (kể cả lễ chưa được thêm vào doc)
			while not is_scheduled(bu) or bu in holiday_dates or bu in scheduled_holidays:
				bu = bu + timedelta(days=1)
			doc.append("holidays", {"holiday_date": bu, "description": bu_label, "weekly_off": 0})
			holiday_dates.add(bu)
			bu_descriptions.add(bu_label)
		elif d not in holiday_dates:
			doc.append("holidays", {"holiday_date": d, "description": label, "weekly_off": 0})
			holiday_dates.add(d)

	for mm, dd in SOLAR_HOLIDAYS:
		add_public_holiday(getdate(f"{year}-{mm:02d}-{dd:02d}"), SOLAR_LABELS[(mm, dd)])

	for date_str, label in (extra_holidays or {}).items():
		add_public_holiday(getdate(date_str), label)

	doc.save()  # validate() sorts, counts, and rejects duplicate dates
	frappe.msgprint(
		_("Đã tạo {0}. Nhớ khai Tết Âm lịch + Giỗ Tổ (10/3 âm) của năm {1} ở Cấu hình lịch làm việc.").format(
			list_name, year
		)
	)
	return doc.name
