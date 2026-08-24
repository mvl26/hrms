# Copyright (c) 2026, Miyano Việt Nam.
"""Miyano — tập NHÓM (category) chuẩn của mã công. Khai một chỗ, năm nơi tiêu thụ.

``Attendance Code.category`` quyết định ngày mang mã đó rơi vào cột nào của bảng công tháng và có
được cộng vào "Tổng công" hay không. Trước 2026-08-24 field này là ``Data`` tự do, còn tập giá trị
hợp lệ bị chép cứng ở năm chỗ: ``REPORT_CATEGORIES``, ``NON_PAID_LEAVE_CATEGORIES``,
``CATEGORY_STATE`` (báo cáo chấm công tháng), ``CATEGORY_FIELD`` (Bảng Công Tháng) và
``CATEGORY_ORDER`` (chú thích). Gõ ``"Phep"`` thay vì ``"Phép"`` thì mã vẫn hiện đúng từng ngày
nhưng ngày đó **lặng lẽ rơi khỏi mọi cột tổng** — không lỗi, không cảnh báo.

Đây là điểm mở rộng THẬT của hệ thống mã công: Loại nghỉ thì tạo bao nhiêu tuỳ ý, nhưng mỗi mã
phải xếp vào một nhóm mà bảng công đã có cột. ``hrms/hr/tests/test_attendance_category.py`` ép năm
nơi kia không được lệch với danh sách ở đây.

Xem `docs/spec/attendance-code-as-anchor.md`.
"""

# Thứ tự đọc từ trái sang là đi từ "trả đủ" tới "không trả" — cũng là thứ tự khối chú thích.
CATEGORIES = (
	"Công",
	"Phép",
	"Ốm",
	"Thai sản",
	"Tai nạn LĐ",
	"Nghỉ bù",
	"Việc riêng",
	"Không lương",
	"Vắng",
)

# Nhóm CỐ Ý không có cột riêng trên Bảng Công Tháng: phần đi làm đã nằm trong "Tổng công", tách ra
# thành hai con số công trên cùng một bảng là mời người đọc hiểu nhầm.
CATEGORY_WITHOUT_SHEET_COLUMN = ("Công",)


def select_options() -> str:
	"""Chuỗi ``options`` cho field Select của ``Attendance Code.category``."""
	return "\n".join(CATEGORIES)
