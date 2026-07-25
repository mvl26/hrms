# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# For license information, please see license.txt
"""Engine tính lương MVL (Miyano) — thuần Python, KHÔNG đụng DB.

Oracle là các ví dụ số thật trong `docs/Cong_thuc_tinh_luong_MVL.md` (trích từ bảng lương 06/2026).
Frappe Salary Slip tính GROSS→NET; MVL trả NET rồi gross-up nộp thay thuế + BH, và biểu thuế/gross-up
là bracket + phân nhánh theo loại nhân sự — quá phức tạp cho formula component, nên gói gọn ở đây để
test được từng con số. `hrms/vn_payroll/salary_slip_hook.py` là lớp mỏng nối engine này vào Salary Slip.
"""

from dataclasses import dataclass
from math import floor


def _round(x) -> float:
	"""ROUND(x, 0) của Excel = làm tròn nửa LÊN. Python round() là banker's rounding nên lệch."""
	return float(floor(float(x) + 0.5))


# Loại nhân sự trả NET có đầy đủ phụ cấp ăn + giảm trừ + gross-up bậc.
NET_FULLTIME_TYPES = ("Chính thức", "Thử việc")


@dataclass
class MVLInput:
	salary_type: str
	base: float  # F — lương ngày công (với Khoán: toàn bộ số tiền khoán)
	bhxh_salary: float  # G — lương đóng BHXH (0 → không đóng)
	dependents: int  # M — số người phụ thuộc
	register_personal_deduction: bool  # có đăng ký giảm trừ bản thân (L)
	lunch_days: float  # số ngày ăn tại công ty
	standard_days: float  # H7 — công chuẩn tháng
	worked_days: float  # H — công thực tế (payment_days)
	bonus: float = 0.0  # tiền thưởng (HR tự điền) — cộng vào thu nhập chịu thuế + thực lĩnh


@dataclass
class MVLConfig:
	personal_deduction: float
	dependent_deduction: float
	lunch_rate: float
	ins_company: float
	ins_employee: float
	probation_coef: float
	tax_brackets: list  # [(threshold_upto, rate, subtract)] lũy tiến trên P (bậc cuối threshold=inf)
	grossup_brackets: list  # [(threshold_upto, subtract, divisor)] quy đổi NET→gross trên O


@dataclass
class MVLResult:
	I: float = 0.0  # lương thực tế theo công
	J: float = 0.0  # phụ cấp ăn trưa
	K: float = 0.0  # tổng thu nhập (I + J)
	N: float = 0.0  # tổng giảm trừ gia cảnh
	O: float = 0.0  # thu nhập làm căn cứ quy đổi
	P: float = 0.0  # thu nhập tính thuế (đã gross-up)
	Q: float = 0.0  # thuế TNCN
	R: float = 0.0  # BH công ty trả
	S: float = 0.0  # BH người lao động (công ty nộp thay khi NET)
	T: float = 0.0  # thực lĩnh
	U: float = 0.0  # thu nhập chịu thuế kê khai


def default_config() -> MVLConfig:
	"""Tham số kỳ 06/2026 (doc mục 1 + biểu thuế/gross-up Bước 6–7). Nguồn sự thật khi chạy = Settings."""
	return MVLConfig(
		personal_deduction=15_500_000,
		dependent_deduction=6_200_000,
		lunch_rate=35_000,
		ins_company=0.215,
		ins_employee=0.105,
		probation_coef=0.85,
		tax_brackets=[
			(10_000_000, 0.05, 0),
			(30_000_000, 0.10, 500_000),
			(60_000_000, 0.20, 3_500_000),
			(100_000_000, 0.30, 9_500_000),
			(float("inf"), 0.35, 14_500_000),
		],
		grossup_brackets=[
			(9_500_000, 0, 0.95),
			(27_500_000, 500_000, 0.9),
			(51_500_000, 3_500_000, 0.8),
			(79_500_000, 9_500_000, 0.7),
			(float("inf"), 14_500_000, 0.65),
		],
	)


def _grossup(o: float, brackets: list) -> float:
	"""Quy đổi thu nhập NET (O) → thu nhập tính thuế (P) theo bậc (Bước 6)."""
	for threshold_upto, subtract, divisor in brackets:
		if o <= threshold_upto:
			return _round((o - subtract) / divisor)
	return 0.0


def _progressive_tax(p: float, brackets: list) -> float:
	"""Thuế TNCN lũy tiến từng phần trên thu nhập tính thuế P (Bước 7). P < 0 → 0."""
	if p < 0:
		return 0.0
	for threshold_upto, rate, subtract in brackets:
		if p < threshold_upto:
			return _round(p * rate - subtract)
	return 0.0


def _coefficient(salary_type: str, cfg: MVLConfig) -> float:
	return cfg.probation_coef if salary_type == "Thử việc" else 1.0


def compute_mvl(inp: MVLInput, cfg: MVLConfig) -> MVLResult:
	"""Chạy toàn bộ Bước 1–9 cho một nhân sự trong một kỳ. Trả mọi số trung gian để in + kiểm."""
	r = MVLResult()
	is_net_fulltime = inp.salary_type in NET_FULLTIME_TYPES
	e = _coefficient(inp.salary_type, cfg)

	# Bước 1 — lương theo công. Khoán/chuyên gia: trả trọn gói, không nhân theo công.
	if inp.salary_type == "Khoán":
		r.I = _round(inp.base)
	else:
		r.I = _round(inp.base * e / inp.standard_days * inp.worked_days)

	# Bước 2 — phụ cấp ăn (chỉ NET fulltime); Bước 3 — tổng thu nhập (+ tiền thưởng nếu có)
	r.J = _round(inp.lunch_days * cfg.lunch_rate) if is_net_fulltime else 0.0
	r.K = r.I + r.J + _round(inp.bonus)

	# Bước 4 — giảm trừ gia cảnh; Bước 5 — thu nhập làm căn cứ quy đổi
	r.N = (
		cfg.personal_deduction if inp.register_personal_deduction else 0.0
	) + cfg.dependent_deduction * inp.dependents
	r.O = max(r.K - r.N - r.J, 0.0)

	# Bước 6–7 — quy đổi + thuế, phân nhánh theo loại nhân sự
	if is_net_fulltime:
		r.P = _grossup(r.O, cfg.grossup_brackets)
		r.Q = _progressive_tax(r.P, cfg.tax_brackets)
	elif inp.salary_type in ("Parttime cư trú", "Khoán"):
		r.P = _round(r.O / 0.9)
		r.Q = _round(r.P * 0.10)
	elif inp.salary_type == "Parttime nước ngoài":
		r.P = _round(r.O / 0.8)
		r.Q = _round(r.P * 0.20)
	elif inp.salary_type == "Parttime cam kết 08":
		r.P = 0.0
		r.Q = 0.0

	# Bước 8 — bảo hiểm; Bước 9 — thực lĩnh + kê khai
	r.R = _round(inp.bhxh_salary * cfg.ins_company)
	r.S = _round(inp.bhxh_salary * cfg.ins_employee)
	r.T = r.K
	r.U = r.K + r.Q + r.S - r.J
	return r
