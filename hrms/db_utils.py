# Copyright (c) 2026, Miyano Việt Nam.
"""Tiện ích DB dùng chung cho các công cụ Miyano chạy ngoài request cycle."""

import frappe


def commit_unless_test() -> bool:
	"""Commit khi chạy thật; KHÔNG commit khi đang chạy test. Trả về True nếu đã commit.

	`FrappeTestCase` chỉ rollback đúng MỘT lần ở `tearDownClass` — xem
	`frappe/tests/utils.py`: `cls.addClassCleanup(_rollback_db)`. Vì vậy một `frappe.db.commit()`
	giữa chừng sẽ ghi thẳng vào DB test và **rò sang mọi test class chạy sau**, gây lỗi ở những
	test hoàn toàn không liên quan. Các công cụ bên dưới vẫn cần commit khi chạy thật qua
	`bench execute` (chạy dài, ghi từng phần để không mất việc đã làm), nên chặn theo cờ test
	thay vì bỏ hẳn.
	"""
	if frappe.flags.in_test:
		return False
	frappe.db.commit()  # nosemgrep
	return True
