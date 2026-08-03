# Copyright (c) 2026, Miyano Việt Nam.
"""Luật chấm công theo GIỜ + ca trượt (`vn_day_classifier.classify_day`).

Đây là hàm THUẦN (không chạm DB) nên test được đầy đủ mọi nhánh mà không cần custom field đã
migrate — phần đọc cấu hình Shift Type được test riêng ở `test_vn_half_day_classifier.py`.

Quy ước ca chuẩn Miyano dùng xuyên suốt: 08:00-17:30, nghỉ trưa 12:00-13:30 (net đúng 8h),
biên trượt 180 phút, số giờ tối thiểu 8h.
"""

import unittest
from datetime import datetime, timedelta

from hrms.hr.doctype.attendance.vn_day_classifier import classify_day

DAY = datetime(2099, 3, 4)


def hm(h, m=0):
	return timedelta(hours=h, minutes=m)


def at(h, m=0):
	return DAY + hm(h, m)


def run(in_hm, out_hm, flexible=True, band_minutes=180, min_work_hours=8.0, start=None, end=None):
	"""Trả (giờ làm THỰC TẾ, mã công) — giờ tính công xem `run_counted`."""
	r = classify(in_hm, out_hm, flexible, band_minutes, min_work_hours, start, end)
	return r.hours, r.code


def run_counted(in_hm, out_hm, **kw):
	"""Giờ NẰM TRONG khung ca — con số quyết định đủ/thiếu công."""
	return classify(in_hm, out_hm, **kw).counted


def classify(in_hm, out_hm, flexible=True, band_minutes=180, min_work_hours=8.0, start=None, end=None):
	return classify_day(
		at(*in_hm),
		at(*out_hm),
		day=DAY,
		start_time=hm(8) if start is None else start,
		end_time=hm(17, 30) if end is None else end,
		lunch_start=hm(12),
		lunch_end=hm(13, 30),
		flexible=flexible,
		band_minutes=band_minutes,
		min_work_hours=min_work_hours,
	)


class TestClassifyDay(unittest.TestCase):
	def test_standard_day_is_full(self):
		self.assertEqual(run((8, 0), (17, 30)), (8.0, "X"))

	def test_flex_late_in_late_out_is_full_day(self):
		"""Vào 11:00 → ca trượt 11:00-20:30; ở đủ tới 20:30 là đủ 8h."""
		self.assertEqual(run((11, 0), (20, 30)), (8.0, "X"))

	def test_flex_late_in_short_by_an_hour_is_half(self):
		"""Ca của user: vào 11:00 ra 19:30 → ghi nhận ĐÚNG 7h (không phải 5h), thiếu 1h → 1/2X."""
		self.assertEqual(run((11, 0), (19, 30)), (7.0, "1/2X"))

	def test_flex_early_in_early_out_is_full_day(self):
		"""Làm sớm về sớm: vào 06:30 → ca 06:30-16:00."""
		self.assertEqual(run((6, 30), (16, 0)), (8.0, "X"))

	def test_flex_band_clamps_beyond_three_hours(self):
		"""Vào 14:00 vượt biên +3h → ca kẹp ở 11:00-20:30.

		Giờ GHI NHẬN vẫn là giờ thật (14:00-22:00 = 8h, không rơi vào giờ trưa nên không trừ), nhưng
		chỉ 6,5h nằm trong khung ca nên ngày đó chỉ được nửa công."""
		self.assertEqual(run((14, 0), (22, 0)), (8.0, "1/2X"))
		self.assertEqual(run_counted((14, 0), (22, 0)), 6.5)

	def test_flex_band_clamps_on_the_early_side(self):
		"""Vào 03:00 vượt biên -3h → ca kẹp ở 05:00-14:30; giờ 03:00-05:00 không tính CÔNG."""
		self.assertEqual(run((3, 0), (14, 30)), (10.0, "X"))  # ghi nhận đủ 10h đã làm
		self.assertEqual(run_counted((3, 0), (14, 30)), 8.0)  # nhưng chỉ 8h trong khung ca

	def test_work_beyond_the_window_is_recorded_but_adds_no_extra_cong(self):
		"""Ở lại quá khung ca: giờ vẫn ghi nhận ĐỦ, nhưng không biến thành công thêm."""
		self.assertEqual(run((11, 0), (23, 0)), (10.5, "X"))  # 12h - 1,5h trưa
		self.assertEqual(run_counted((11, 0), (23, 0)), 8.0)

	def test_below_minimum_is_half_day_code(self):
		self.assertEqual(run((8, 0), (12, 0)), (4.0, "1/2X"))

	def test_only_lunch_time_is_absent(self):
		self.assertEqual(run((12, 15), (13, 15)), (0.0, "V"))

	def test_out_before_in_is_absent(self):
		self.assertEqual(run((17, 0), (9, 0)), (0.0, "V"))

	def test_flag_off_keeps_the_fixed_window(self):
		"""Tắt cờ linh hoạt: giờ ghi nhận vẫn là 7h thật, nhưng chỉ 5h nằm trong khung ca cứng."""
		self.assertEqual(run((11, 0), (19, 30), flexible=False), (7.0, "1/2X"))
		self.assertEqual(run_counted((11, 0), (19, 30), flexible=False), 5.0)

	def test_flag_off_standard_day_unchanged(self):
		self.assertEqual(run((8, 0), (17, 30), flexible=False), (8.0, "X"))

	def test_min_hours_configurable(self):
		"""Hạ ngưỡng xuống 7h thì chính ngày 11:00-19:30 thành đủ công."""
		self.assertEqual(run((11, 0), (19, 30), min_work_hours=7.0), (7.0, "X"))

	def test_band_zero_disables_sliding(self):
		self.assertEqual(run((11, 0), (19, 30), band_minutes=0), (7.0, "1/2X"))
		self.assertEqual(run_counted((11, 0), (19, 30), band_minutes=0), 5.0)

	def test_lunch_always_inside_window_within_band(self):
		"""Với biên ±3h và trưa 12:00-13:30, khung trượt luôn nuốt trọn giờ trưa → luôn trừ đủ 1,5h."""
		for h in range(5, 12):  # giờ vào từ 05:00 đến 11:00
			hours, _code = run((h, 0), (h + 9, 30))
			self.assertEqual(hours, 8.0, f"vào {h}:00 phải ra đúng 8h net")


class TestRecordedHoursAreTheRealOnes(unittest.TestCase):
	"""Giờ ghi nhận phải là giờ NGƯỜI TA ĐÃ LÀM, không phải phần lọt vào khung ca.

	Hai con số khác nhau và trước đây bị gộp làm một:

	- `hours`   — giờ làm thực tế (ra - vào, trừ phần trùng nghỉ trưa). Đây là thứ hiện trên bảng
	  công và báo cáo giờ làm việc.
	- `counted` — phần nằm trong khung ca, dùng để quyết định đủ công hay thiếu giờ. Khung ca chặn
	  việc ở lại muộn tự biến thành công, nhưng KHÔNG được phép bóp méo số giờ đã làm.
	"""

	def test_the_case_from_the_shop_floor(self):
		"""Làm 08:23-18:55 phải ghi hơn 9h, không phải 8h cắt tại 17:30."""
		gio, ma = run((8, 23), (18, 55))
		self.assertAlmostEqual(gio, 9.03, places=2)  # 10h32 - 1h30 nghỉ trưa
		self.assertEqual(ma, "X")

	def test_staying_late_does_not_inflate_cong(self):
		"""Cùng ngày đó, phần tính công vẫn chốt ở 8h — làm thêm không thành công thêm."""
		self.assertEqual(run_counted((8, 23), (18, 55)), 8.0)

	def test_lunch_is_still_deducted_from_the_real_hours(self):
		"""Giờ thực tế vẫn trừ nghỉ trưa — 'giờ làm việc' chứ không phải 'giờ có mặt'."""
		self.assertEqual(run((8, 0), (17, 30))[0], 8.0)  # 9,5h có mặt - 1,5h trưa

	def test_a_day_entirely_outside_lunch_loses_nothing(self):
		self.assertEqual(run((14, 0), (18, 0))[0], 4.0)
