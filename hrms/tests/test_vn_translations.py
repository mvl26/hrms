# Copyright (c) 2026, Miyano Việt Nam.
import csv
import os
from collections import defaultdict

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.tests.isolation import PerTestRollback

# The VN labels HR must see for the doctypes/reports renamed to English names
# (docs/tasks/plan-english-naming-standardization.md). Source string -> expected translation.
VN_TIMEKEEPING_LABELS = {
	"Monthly Attendance Sheet": "Bảng Công Tháng",
	"Monthly Attendance Sheet Detail": "Chi tiết Bảng Công Tháng",
	"Monthly Attendance Report": "Bảng chấm công tháng",
	"Business Trip": "Công Tác",
	"Business Trip Traveler": "Người đi công tác",
	# Đổi tên 2026-08-25: tên cũ "Bảng Lương MVL" có DẤU nên `scrub(name)` ra đường dẫn không
	# khớp thư mục ASCII → báo cáo không import được, mở trên Desk là ModuleNotFoundError.
	"MVL Salary Register": "Bảng lương MVL",
}


def read_vi_csv():
	path = os.path.join(os.path.dirname(frappe.get_app_path("hrms")), "hrms", "translations", "vi.csv")
	with open(path, encoding="utf-8") as f:
		return path, [row for row in csv.reader(f) if row]


class TestVnTranslations(PerTestRollback, FrappeTestCase):
	def test_no_source_key_has_two_different_translations(self):
		"""frappe.translate keys a 2-column row by source text alone and lets a later row overwrite an
		earlier one, so a duplicated source string silently drops one translation. Catch it here."""
		_path, rows = read_vi_csv()

		by_source = defaultdict(set)
		for row in rows:
			if len(row) == 2:
				by_source[row[0]].add(row[1])

		conflicting = {src: sorted(vals) for src, vals in by_source.items() if len(vals) > 1}
		self.assertEqual(
			conflicting, {}, f"vi.csv has source strings with conflicting translations: {conflicting}"
		)

	def test_every_row_is_well_formed(self):
		"""frappe logs an error and (with throw) refuses rows that are not 2 or 3 columns."""
		_path, rows = read_vi_csv()
		bad = [(i, row) for i, row in enumerate(rows, 1) if len(row) not in (2, 3)]
		self.assertEqual(bad, [], f"vi.csv rows must have 2 or 3 columns: {bad}")

	def test_renamed_timekeeping_doctypes_keep_their_vn_labels(self):
		"""The English rename must stay invisible to HR: the VN label is what they see on Desk."""
		_path, rows = read_vi_csv()
		mapping = {row[0]: row[1] for row in rows if len(row) == 2}

		for source, expected in VN_TIMEKEEPING_LABELS.items():
			self.assertEqual(
				mapping.get(source), expected, f"vi.csv must translate {source!r} to {expected!r}"
			)
