"""On-demand generator for a Vietnamese Holiday List.

Creates ONE Holiday List per (company, year) using the stock Holiday List doctype:
  - weekly-off rows (Chủ nhật, optionally + Thứ 7) via the doctype's own get_weekly_off_dates;
  - the fixed SOLAR public holidays of Điều 112 BLLĐ 2019 (Tết dương, 30/4, 1/5, Quốc khánh ×2);
  - a compensatory day off (nghỉ bù, Điều 112 khoản 3) on the next working day whenever a solar
    holiday coincides with a weekly-off day.

Tết Âm lịch (5 ngày) + Giỗ Tổ (10/3 âm) shift every year (lunar) → HR enters those by hand.
Idempotent (re-running never duplicates dates). On-demand only — NOT wired to migrate/install,
because creating a Holiday List is creating company data (ask-first on production).

Usage:
  bench --site <s> execute hrms.setup_vn_holiday.create_vn_holiday_list \
        --kwargs "{'year': 2026, 'company': 'Miyano', 'weekly_off_days': ['Sunday']}"
"""

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import getdate

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


def create_vn_holiday_list(year, company, weekly_off_days=("Sunday",), name=None):
	"""Create/refresh a VN Holiday List for `year`. Returns its name. Idempotent."""
	year = int(year)
	list_name = name or f"VN {company} {year}"

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

	# weekly-off rows: get_weekly_off_dates skips dates already present, so looping is idempotent
	for day in weekly_off_days:
		doc.weekly_off = day
		doc.get_weekly_off_dates()

	weekly_off_dates = {getdate(h.holiday_date) for h in doc.holidays if h.weekly_off}
	holiday_dates = {getdate(h.holiday_date) for h in doc.holidays if not h.weekly_off}
	bu_descriptions = {h.description for h in doc.holidays if not h.weekly_off}
	for mm, dd in SOLAR_HOLIDAYS:
		d = getdate(f"{year}-{mm:02d}-{dd:02d}")
		label = SOLAR_LABELS[(mm, dd)]
		if d in weekly_off_dates:
			# lễ trùng ngày nghỉ hàng tuần -> nghỉ bù vào ngày làm việc kế tiếp (Điều 112 khoản 3)
			bu_label = f"Nghỉ bù {label}"
			if bu_label in bu_descriptions:
				continue  # đã có ngày bù cho lễ này -> chạy lại không nhân đôi
			bu = d + timedelta(days=1)
			while bu in weekly_off_dates or bu in holiday_dates:
				bu = bu + timedelta(days=1)  # bỏ qua CN + ngày lễ liền kề
			doc.append("holidays", {"holiday_date": bu, "description": bu_label, "weekly_off": 0})
			holiday_dates.add(bu)
			bu_descriptions.add(bu_label)
		elif d not in holiday_dates:
			doc.append("holidays", {"holiday_date": d, "description": label, "weekly_off": 0})
			holiday_dates.add(d)

	doc.save()  # validate() sorts, counts, and rejects duplicate dates
	frappe.msgprint(
		_("Đã tạo {0}. Nhớ nhập tay Tết Âm lịch + Giỗ Tổ (10/3 âm) cho năm {1}.").format(list_name, year)
	)
	return doc.name
