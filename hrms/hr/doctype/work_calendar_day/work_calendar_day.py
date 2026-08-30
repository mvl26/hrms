# Copyright (c) 2026, Miyano Việt Nam.
from frappe.model.document import Document

DAY_TYPE_HOLIDAY = "Nghỉ lễ"
DAY_TYPE_MAKE_UP = "Làm bù"


class WorkCalendarDay(Document):
	"""Một ngày trong năm KHÁC với lịch tuần — ngoại lệ, khai tay theo từng năm.

	Hai chiều, cùng một bảng để HR nhìn thấy thế cân bằng "nghỉ ghép 2 ngày ↔ làm bù 2 ngày":

	- **Nghỉ lễ** — cả công ty nghỉ, hưởng nguyên lương. Gồm lễ âm (Tết, Giỗ Tổ, trôi mỗi năm nên
	  không suy ra được bằng công thức), lễ riêng của công ty, và ngày nghỉ ghép. Được đẩy xuống
	  Holiday List, áp cùng quy tắc nghỉ bù của Điều 112 khoản 3 như lễ dương.
	- **Làm bù** — ngày cuối tuần phải đi làm. KHÔNG xuống Holiday List: nó là ngày *làm việc*, nhét
	  vào bảng ngày nghỉ là sai ngay từ tên gọi. Nó sống ở Cấu hình lịch làm việc và được
	  `work_schedule.is_scheduled_day` đọc trực tiếp.

	Tên cũ của doctype này là `Lunar Holiday` — đã sai từ lúc bảng nhận thêm lễ riêng công ty, và
	sai hẳn khi nhận cả ngày làm bù.
	"""

	pass
