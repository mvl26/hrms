# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
"""Test engine lương MVL — oracle là ví dụ số thật trong docs/Cong_thuc_tinh_luong_MVL.md.

Engine thuần nên test là plain unittest, chạy được cả ngoài Frappe. Vẫn nạp qua harness rollback.
"""

import unittest

from hrms.vn_payroll.mvl import (
	MVLInput,
	_progressive_tax,
	_round,
	compute_mvl,
	default_config,
)


class TestMVLCore(unittest.TestCase):
	def setUp(self):
		self.cfg = default_config()

	def test_chinh_thuc_ta_truong_xuan(self):
		# doc 3.1: F=25tr, 22/22 công, ăn 21 ngày, 1 phụ thuộc, có đăng ký giảm trừ
		r = compute_mvl(MVLInput("Chính thức", 25_000_000, 25_000_000, 1, True, 21, 22, 22), self.cfg)
		self.assertEqual(r.I, 25_000_000)
		self.assertEqual(r.J, 735_000)
		self.assertEqual(r.K, 25_735_000)
		self.assertEqual(r.N, 21_700_000)
		self.assertEqual(r.O, 3_300_000)
		self.assertEqual(r.Q, 173_684)  # ROUND(3_473_684 * 5%)
		self.assertEqual(r.R, 5_375_000)
		self.assertEqual(r.S, 2_625_000)
		self.assertEqual(r.T, 25_735_000)

	def test_thu_viec_nguyen_yen_chi(self):
		# doc 3.2: F=13.5tr, hệ số 0.85, 11.5/22 công, ăn 9 ngày, có đăng ký giảm trừ, không BHXH
		r = compute_mvl(MVLInput("Thử việc", 13_500_000, 0, 0, True, 9, 22, 11.5), self.cfg)
		self.assertEqual(r.I, 5_998_295)
		self.assertEqual(r.K, 6_313_295)
		self.assertEqual(r.O, 0)  # sau giảm trừ 15.5tr → 0
		self.assertEqual(r.Q, 0)
		self.assertEqual(r.R, 0)
		self.assertEqual(r.S, 0)
		self.assertEqual(r.T, 6_313_295)

	def test_nghi_khong_luong_giam_cong(self):
		# doc 3: Phạm Thị Yến lương 20tr, đi làm 10/22 công → I = 20tr × 10/22
		r = compute_mvl(MVLInput("Chính thức", 20_000_000, 0, 0, False, 0, 22, 10), self.cfg)
		self.assertEqual(r.I, 9_090_909)  # ROUND(20_000_000 / 22 * 10)

	def test_parttime_cu_tru_10pct(self):
		# doc 3.3: O = 10tr → P = 11.111.111 → Q = 1.111.111
		r = compute_mvl(MVLInput("Parttime cư trú", 10_000_000, 0, 0, False, 0, 22, 22), self.cfg)
		self.assertEqual(r.O, 10_000_000)
		self.assertEqual(r.J, 0)
		self.assertEqual(r.P, 11_111_111)
		self.assertEqual(r.Q, 1_111_111)
		self.assertEqual(r.T, 10_000_000)

	def test_parttime_nuoc_ngoai_20pct(self):
		# doc 3.3: O = 3tr → P = 3.750.000 → Q = 750.000
		r = compute_mvl(MVLInput("Parttime nước ngoài", 3_000_000, 0, 0, False, 0, 22, 22), self.cfg)
		self.assertEqual(r.P, 3_750_000)
		self.assertEqual(r.Q, 750_000)

	def test_parttime_cam_ket_08_khong_thue(self):
		r = compute_mvl(MVLInput("Parttime cam kết 08", 5_000_000, 0, 0, False, 0, 22, 22), self.cfg)
		self.assertEqual(r.P, 0)
		self.assertEqual(r.Q, 0)
		self.assertEqual(r.T, 5_000_000)

	def test_khoan_chuyen_gia(self):
		# doc 3.4: khoán 30tr NET → P = 33.333.333 → Q = 3.333.333, không nhân theo công
		r = compute_mvl(MVLInput("Khoán", 30_000_000, 0, 0, False, 0, 22, 10), self.cfg)
		self.assertEqual(r.I, 30_000_000)  # KHÔNG bị nhân 10/22
		self.assertEqual(r.P, 33_333_333)
		self.assertEqual(r.Q, 3_333_333)

	def test_tax_bracket_boundaries(self):
		b = self.cfg.tax_brackets
		self.assertEqual(_progressive_tax(9_999_999, b), _round(9_999_999 * 0.05))
		self.assertEqual(_progressive_tax(10_000_000, b), _round(10_000_000 * 0.10 - 500_000))
		self.assertEqual(_progressive_tax(29_999_999, b), _round(29_999_999 * 0.10 - 500_000))
		self.assertEqual(_progressive_tax(30_000_000, b), _round(30_000_000 * 0.20 - 3_500_000))
		self.assertEqual(_progressive_tax(60_000_000, b), _round(60_000_000 * 0.30 - 9_500_000))
		self.assertEqual(_progressive_tax(100_000_000, b), _round(100_000_000 * 0.35 - 14_500_000))
		self.assertEqual(_progressive_tax(-1, b), 0)

	def test_bonus_added_to_income_and_taxed(self):
		# Chính thức 25M, 22/22, ăn 21, 1 phụ thuộc + thưởng 5M (HR tự điền)
		r = compute_mvl(
			MVLInput("Chính thức", 25_000_000, 25_000_000, 1, True, 21, 22, 22, bonus=5_000_000), self.cfg
		)
		self.assertEqual(r.K, 25_735_000 + 5_000_000)  # K = I + J + thưởng
		self.assertEqual(r.O, 8_300_000)  # O = K − N − J → thưởng chịu thuế
		self.assertEqual(r.T, 30_735_000)  # thực lĩnh gồm cả thưởng
		# không thưởng → như cũ
		r0 = compute_mvl(MVLInput("Chính thức", 25_000_000, 25_000_000, 1, True, 21, 22, 22), self.cfg)
		self.assertEqual(r0.Q, 173_684)
		self.assertGreater(r.Q, r0.Q)  # thưởng làm thuế tăng

	def test_grossup_bracket_boundaries(self):
		# O đúng ngưỡng 9.5tr thuộc bậc 1 (/0.95); vượt lên bậc 2 ((O-500k)/0.9)
		r1 = compute_mvl(MVLInput("Chính thức", 9_500_000, 0, 0, False, 0, 22, 22), self.cfg)
		self.assertEqual(r1.P, _round(9_500_000 / 0.95))
		r2 = compute_mvl(MVLInput("Chính thức", 9_500_001, 0, 0, False, 0, 22, 22), self.cfg)
		self.assertEqual(r2.P, _round((9_500_001 - 500_000) / 0.9))
