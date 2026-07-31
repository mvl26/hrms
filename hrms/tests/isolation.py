# Copyright (c) 2026, Miyano Việt Nam.
"""Cô lập từng test method — thứ `FrappeTestCase` KHÔNG cung cấp.

`FrappeTestCase.setUpClass` chỉ đăng ký `cls.addClassCleanup(_rollback_db)`
(xem `frappe/tests/utils.py`), nghĩa là rollback đúng một lần ở `tearDownClass`. Mọi test method
trong cùng một class vì thế dùng chung MỘT transaction: bản ghi test trước tạo ra vẫn còn nguyên
khi test sau chạy.

Với test của Miyano, phần lớn dùng đi dùng lại cùng một nhân viên và cùng một mốc thời gian neo
(ví dụ 2099-06-15, hay kỳ phép 2099), điều đó làm test thứ hai trở đi đâm vào bản ghi của test đầu
— `DuplicateAttendanceError`, trùng Leave Allocation, v.v. Harness console của repo mở savepoint
quanh mỗi test nên cục bộ không lộ; CI chạy `bench run-tests` thì lộ ngay.

Cho class kế thừa `PerTestRollback` TRƯỚC `FrappeTestCase` để mỗi test tự dọn sau lưng nó.
"""

import frappe

SAVEPOINT = "hrms_per_test"


class PerTestRollback:
	"""Mở savepoint ở `setUp`, rollback về đúng đó sau mỗi test.

	Chỉ hoàn tác thay đổi DB — savepoint không gọi được rollback watcher, nên test nào ghi ra
	filesystem vẫn phải tự dọn.
	"""

	def _callSetUp(self):
		# Móc vào `_callSetUp` chứ KHÔNG phải `setUp`: rất nhiều test class ở đây tự định nghĩa
		# `setUp` mà không gọi `super().setUp()` — móc vào `setUp` thì bản của mixin không bao giờ
		# chạy và cô lập biến mất trong im lặng. `unittest.TestCase.run()` luôn đi qua `_callSetUp`
		# (có từ Python 3.8), nên savepoint được mở kể cả khi lớp con ghi đè `setUp`.
		frappe.db.savepoint(SAVEPOINT)
		# đăng ký trước mọi cleanup của chính test → chạy sau cùng (LIFO), dọn nốt phần còn lại
		self.addCleanup(self.rollback_to_savepoint)
		super()._callSetUp()

	def rollback_to_savepoint(self):
		try:
			frappe.db.rollback(save_point=SAVEPOINT)
		except Exception:
			# COMMIT giữa chừng huỷ mọi savepoint (code upstream vẫn commit ở vài chỗ, ví dụ
			# process_auto_attendance) → savepoint không còn, lùi về rollback cả transaction.
			frappe.db.rollback()
