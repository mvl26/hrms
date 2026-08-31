# Copyright (c) 2026, Miyano Việt Nam.
"""Bộ dựng cảnh dùng chung cho mọi test về lịch làm việc.

Trước module này mỗi bộ test tự dựng dữ liệu riêng, nên không chỗ nào chứng minh **các mảnh ăn khớp
với nhau** — chỉ chứng minh từng mảnh đúng riêng. Cảnh ở đây dựng một năm 2027 tất định, đủ để một
bộ test bất kỳ hỏi bất kỳ câu nào về lịch mà không phải dựng lại từ đầu.

Chỉ DỰNG DỮ LIỆU, không assert. Mỗi bộ test gọi `build_scenario()` rồi tự khẳng định phần của mình.
Idempotent: gọi nhiều lần trong cùng một test không nhân đôi gì.

Năm 2027 được chọn vì nó không đụng dữ liệu thật nào trên site (lịch thật là 2026), và vì các mốc
cần thiết rơi đúng thứ mong muốn — xem hằng số bên dưới.

Spec: `docs/spec/work-schedule-integration-hardening.md` §5.
"""

from calendar import monthrange

import frappe
from frappe.utils import getdate

from hrms.setup_vn_holiday import create_vn_holiday_list
from hrms.tests.vn_test_utils import default_company

# Số ngày T2-T6 của từng tháng 2027 — mốc đối chiếu cho mẫu số lương.
SCHEDULED_DAYS_2027 = [21, 20, 23, 22, 21, 22, 22, 22, 22, 21, 22, 23]

MON_TO_FRI = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
MON_TO_SAT = [*MON_TO_FRI, "Saturday"]
ALL_WEEK = [*MON_TO_SAT, "Sunday"]

SHIFTS = {
	"office": ("_Test WC Ca Hanh Chinh", MON_TO_FRI),
	"six_day": ("_Test WC Ca Sau Ngay", MON_TO_SAT),
	"all_week": ("_Test WC Ca Bay Ngay", ALL_WEEK),
}

HOLIDAY_LIST = "_Test WC 2027"

# Tết Nguyên Đán 2027 — mùng 1-3 rơi T2/T3/T4, tức nằm gọn trong ngày làm việc.
LUNAR_NEW_YEAR = {
	"2027-02-08": "Tết Nguyên Đán (mùng 1)",
	"2027-02-09": "Tết Nguyên Đán (mùng 2)",
	"2027-02-10": "Tết Nguyên Đán (mùng 3)",
}
ANCESTORS_DAY = {"2027-04-16": "Giỗ Tổ Hùng Vương (10/3 âm)"}

# Lễ riêng công ty, cố ý đặt giữa tuần (thứ Tư) để phân biệt với lễ rơi vào cuối tuần.
COMPANY_HOLIDAY = "2027-06-16"

# Nghỉ ghép + làm bù CÙNG tháng: tháng 8 mất một thứ Sáu, bù lại một thứ Bảy -> mẫu số KHÔNG đổi.
BRIDGE_SAME_MONTH = ("2027-08-13", "2027-08-14")

# Nghỉ ghép + làm bù KHÁC tháng: tháng 10 mất một thứ Sáu, tháng 11 thêm một thứ Bảy -> mẫu số của
# CẢ HAI tháng đổi, ngược chiều nhau. Đây là cái bẫy spec §3b đã cảnh báo, phải có người canh.
BRIDGE_CROSS_MONTH = ("2027-10-01", "2027-11-06")

EMPLOYEES = {
	"A": "wc_a_office@codes.com",
	"B": "wc_b_sixday@codes.com",
	"C": "wc_c_noshift@codes.com",
	"D": "wc_d_exempt@codes.com",
	"E": "wc_e_partial@codes.com",
}

E_JOINING, E_RELIEVING = "2027-03-16", "2027-11-15"


def month_range(day) -> tuple[str, str]:
	"""(ngày đầu, ngày cuối) của tháng chứa `day` — dạng chuỗi, dùng thẳng cho API lịch."""
	d = getdate(day)
	last = monthrange(d.year, d.month)[1]
	return f"{d.year}-{d.month:02d}-01", f"{d.year}-{d.month:02d}-{last:02d}"


def set_weekday_rows(parent: str, parenttype: str, parentfield: str, days) -> None:
	"""Ghi thẳng bảng con `Assignment Rule Day`.

	Không đi qua Document của doctype cha: cách này chạy được cả khi site chưa migrate custom field,
	và không kéo theo validate của cha (Shift Type có `validate` khá nặng).
	"""
	frappe.db.delete(
		"Assignment Rule Day",
		{"parent": parent, "parenttype": parenttype, "parentfield": parentfield},
	)
	for idx, day in enumerate(days, start=1):
		frappe.get_doc(
			{
				"doctype": "Assignment Rule Day",
				"parent": parent,
				"parenttype": parenttype,
				"parentfield": parentfield,
				"day": day,
				"idx": idx,
			}
		).insert(ignore_permissions=True)


def set_company_weekdays(days=MON_TO_FRI) -> None:
	"""Lịch làm việc mặc định của công ty — tầng cuối của chuỗi phân giải."""
	set_weekday_rows("Work Calendar Settings", "Work Calendar Settings", "default_working_days", days)


def ensure_shift(name: str, days) -> str:
	if not frappe.db.exists("Shift Type", name):
		frappe.get_doc(
			{
				"doctype": "Shift Type",
				"__newname": name,
				"start_time": "8:0:0",
				"end_time": "17:0:0",
			}
		).insert(ignore_permissions=True)
	set_weekday_rows(name, "Shift Type", "custom_working_days", days)
	return name


def set_calendar_days(rows) -> None:
	"""Bảng ngày đặc biệt: `(năm, ngày, loại, tên)`. Thay thế toàn bộ, không cộng dồn."""
	settings = frappe.get_single("Work Calendar Settings")
	settings.company = default_company()
	settings.calendar_days = []
	for year, day, day_type, desc in rows:
		settings.append(
			"calendar_days",
			{"year": year, "holiday_date": day, "day_type": day_type, "description": desc},
		)
	settings.flags.ignore_permissions = True
	settings.save()


def scenario_calendar_days() -> list[tuple]:
	"""Mọi ngày đặc biệt của cảnh 2027, dạng bảng `Work Calendar Day`."""
	rows = [(2027, d, "Nghỉ lễ", desc) for d, desc in {**LUNAR_NEW_YEAR, **ANCESTORS_DAY}.items()]
	rows.append((2027, COMPANY_HOLIDAY, "Nghỉ lễ", "Nghỉ lễ công ty"))
	for off, make_up in (BRIDGE_SAME_MONTH, BRIDGE_CROSS_MONTH):
		rows.append((2027, off, "Nghỉ lễ", f"Nghỉ ghép {off}"))
		rows.append((2027, make_up, "Làm bù", f"Làm bù {off}"))
	return rows


def build_scenario(year: int = 2027) -> frappe._dict:
	"""Dựng cả cảnh và trả về mọi thứ một bộ test có thể cần. Idempotent."""
	from erpnext.setup.doctype.employee.test_employee import make_employee

	company = default_company()
	set_company_weekdays()
	set_calendar_days(scenario_calendar_days())

	shifts = {key: ensure_shift(name, days) for key, (name, days) in SHIFTS.items()}

	employees = {key: make_employee(email, company=company) for key, email in EMPLOYEES.items()}

	settings = frappe.get_single("Work Calendar Settings")
	holiday_list = create_vn_holiday_list(
		year,
		company,
		name=HOLIDAY_LIST,
		extra_holidays=settings.get_public_holidays(year),
	)

	assign = {
		"A": shifts["office"],
		"B": shifts["six_day"],
		"C": None,  # cố ý không phân ca -> rơi về lịch mặc định của công ty
		"D": shifts["office"],
		"E": shifts["office"],
	}
	for key, employee in employees.items():
		frappe.db.set_value(
			"Employee",
			employee,
			{
				"default_shift": assign[key],
				"holiday_list": holiday_list,
				"date_of_joining": E_JOINING if key == "E" else "2020-01-01",
				"relieving_date": E_RELIEVING if key == "E" else None,
				"status": "Left" if key == "E" else "Active",
				"custom_exempt_from_checkin": 1 if key == "D" else 0,
			},
			update_modified=False,
		)
	frappe.clear_cache(doctype="Employee")

	return frappe._dict(
		company=company,
		year=year,
		shifts=shifts,
		employees=employees,
		holiday_list=holiday_list,
		company_holiday=COMPANY_HOLIDAY,
		bridge_same_month=BRIDGE_SAME_MONTH,
		bridge_cross_month=BRIDGE_CROSS_MONTH,
	)
