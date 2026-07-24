# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class LunarHoliday(Document):
	"""Một ngày lễ không cố định theo dương lịch (Tết Âm lịch, Giỗ Tổ).

	Ngày âm trôi mỗi năm nên không suy ra được bằng công thức — HR nhập ngày dương tương ứng
	cho từng năm. `Work Calendar Settings` gom chúng lại và đẩy vào Holiday List, nơi chúng
	được áp cùng quy tắc nghỉ bù (Điều 112 khoản 3) như lễ dương.
	"""

	pass
