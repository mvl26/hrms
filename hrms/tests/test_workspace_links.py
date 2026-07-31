# Copyright (c) 2026, Miyano Việt Nam.
"""Bất biến của Workspace: thẻ/phím tắt chỉ hiện khi có mặt trong `content`, link phải trỏ đi đâu đó.

Workspace lưu nội dung ở HAI chỗ: bảng con `links`/`shortcuts` (dữ liệu) và chuỗi JSON `content`
(bố cục). Thêm một Card Break mà quên thêm vào `content` thì cả nhóm link **không hiện gì trên
desk** mà cũng chẳng có lỗi nào — đúng loại sai lặng lẽ mà test này chặn.
"""

import json
import os

import frappe
from frappe.tests.utils import FrappeTestCase

from hrms.tests.isolation import PerTestRollback

# workspace của Miyano (đã thêm/sửa link VN) — soi kỹ; workspace upstream để nguyên
MIYANO_WORKSPACES = ("shift_&_attendance",)


def read_workspace(folder):
	path = os.path.join(frappe.get_app_path("hrms"), "hr", "workspace", folder, f"{folder}.json")
	with open(path, encoding="utf-8") as f:
		return json.load(f)


class TestWorkspaceLinks(PerTestRollback, FrappeTestCase):
	def test_every_card_is_laid_out_in_content(self):
		for folder in MIYANO_WORKSPACES:
			doc = read_workspace(folder)
			content = json.loads(doc.get("content") or "[]")
			laid_out = {c["data"]["card_name"] for c in content if c.get("type") == "card"}
			cards = {l["label"] for l in doc["links"] if l.get("type") == "Card Break"}

			self.assertEqual(
				cards - laid_out, set(), f"{folder}: thẻ có link nhưng thiếu trong content -> vô hình"
			)
			self.assertEqual(laid_out - cards, set(), f"{folder}: content bày thẻ không tồn tại trong links")

	def test_every_shortcut_is_laid_out_in_content(self):
		for folder in MIYANO_WORKSPACES:
			doc = read_workspace(folder)
			content = json.loads(doc.get("content") or "[]")
			laid_out = {c["data"]["shortcut_name"] for c in content if c.get("type") == "shortcut"}
			shortcuts = {s["label"] for s in doc.get("shortcuts", [])}

			self.assertEqual(shortcuts - laid_out, set(), f"{folder}: phím tắt thiếu trong content")
			self.assertEqual(laid_out - shortcuts, set(), f"{folder}: content bày phím tắt không tồn tại")

	def test_every_link_points_at_something_real(self):
		for folder in MIYANO_WORKSPACES:
			doc = read_workspace(folder)
			dangling = []
			for link in doc["links"]:
				if link.get("type") == "Card Break" or not link.get("link_to"):
					continue
				if link.get("link_type") not in ("DocType", "Report", "Page", "Dashboard"):
					continue
				if not frappe.db.exists(link["link_type"], link["link_to"]):
					dangling.append((link["link_type"], link["link_to"]))

			self.assertEqual(dangling, [], f"{folder}: link trỏ tới thứ không tồn tại trên site")

	def test_vn_timekeeping_pages_are_reachable(self):
		"""Các trang chấm công của Miyano phải có mặt — HR vào bằng workspace, không gõ URL."""
		doc = read_workspace("shift_&_attendance")
		linked = {l.get("link_to") for l in doc["links"]}

		for target in (
			"Monthly Attendance Sheet",  # Bảng Công Tháng
			"Business Trip",  # Công Tác
			"Attendance Code",  # Mã công
			"Attendance Correction Log",  # Nhật ký sửa công
			"Work Calendar Settings",  # Cấu hình lịch làm việc
			"Attendance Request",  # Yêu cầu chấm công
			"Employee Working Hours",  # report giờ làm việc
			"Monthly Attendance Report",  # bảng chấm công tháng
		):
			self.assertIn(target, linked, f"thiếu link tới {target} trên workspace Shift & Attendance")
