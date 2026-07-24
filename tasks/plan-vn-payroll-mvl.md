# Tính lương MVL — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use `- [ ]`.
> Spec: `spec/vn-payroll-mvl.md`. Nhánh: `feat/skip-attendance-diag`.

**Goal:** Sinh Salary Slip đúng công thức lương NET của Miyano (gross-up nộp thay thuế + BH), số ngày
công lấy từ hệ thống chấm công; cấu hình chuẩn đóng gói vào app, sửa được trên UI.

**Architecture:** Engine Python thuần (`hrms/vn_payroll/mvl.py`) tính toàn bộ công thức; tham số chuẩn
trong Single DocType `MVL Payroll Settings`; cấu hình mỗi NV trong custom fields của Salary Structure
Assignment; Salary Slip.validate gọi engine, gán component + net_pay.

**Tech Stack:** Frappe/ERPNext v15, Python 3.10, ruff (tabs, double quotes, 110 cols).

## Global Constraints

- KHÔNG `bench run-tests` trên `miyano` — chạy qua **harness rollback**, kiểm rò rỉ sau mỗi lượt.
- Engine KHÔNG đụng DB (input thuần) — test theo đúng ví dụ số trong `docs/Cong_thuc_tinh_luong_MVL.md`.
- KHÔNG đụng `SalarySlip.get_working_days_details` (payment_days) — chỉ tiêu thụ.
- Additive, `git revert`-được. Fixtures đồng bộ filter trong `hooks.py`. Cài dev = `reload_doc` (không migrate).
- Số tiền lương thật của NV = HR nhập trên UI; plan chỉ dựng hệ thống + test theo doc.

## File Structure

- `hrms/vn_payroll/__init__.py` — package mới.
- `hrms/vn_payroll/mvl.py` — engine thuần: dataclass input/output + `compute_mvl()` + helpers thuế/gross-up.
- `hrms/vn_payroll/test_mvl.py` — test engine theo oracle của doc.
- `hrms/hr/doctype/mvl_payroll_settings/` — Single DocType tham số chuẩn (+ 2 child: bậc thuế, bậc gross-up).
- `hrms/hr/doctype/mvl_tax_bracket/`, `hrms/hr/doctype/mvl_grossup_bracket/` — child doctypes.
- `hrms/vn_payroll/salary_slip_hook.py` — cầu nối: đọc SSA + settings + payment_days → engine → slip.
- `hrms/vn_payroll/test_salary_slip_mvl.py` — test tích hợp qua harness.
- `hrms/vn_payroll/setup_mvl.py` — `ensure_mvl_defaults()`: seed components + structure + settings mặc định.
- Sửa: `hrms/hooks.py` (doc_events Salary Slip, after_migrate, fixtures), Custom Field fixtures.

---

### Task 1: Engine — bước lõi NET fulltime + thử việc

**Files:**
- Create: `hrms/vn_payroll/__init__.py` (rỗng)
- Create: `hrms/vn_payroll/mvl.py`
- Test: `hrms/vn_payroll/test_mvl.py`

**Interfaces:**
- Produces: `compute_mvl(inp: MVLInput, cfg: MVLConfig) -> MVLResult`. `MVLInput(salary_type, base, bhxh_salary, dependents, register_personal_deduction, lunch_days, standard_days, worked_days)`. `MVLConfig(personal_deduction, dependent_deduction, lunch_rate, ins_company, ins_employee, probation_coef, tax_brackets, grossup_brackets)`. `MVLResult(I, J, K, N, O, P, Q, R, S, T, U)` (mọi field float đã ROUND).

- [ ] **Step 1: Write the failing test** (oracle = doc mục 3.1 + 3.2)

```python
import unittest
from hrms.vn_payroll.mvl import MVLInput, MVLResult, compute_mvl, default_config


class TestMVLCore(unittest.TestCase):
	def setUp(self):
		self.cfg = default_config()

	def test_chinh_thuc_ta_truong_xuan(self):
		# doc 3.1: F=25tr, 22/22 cong, an 21 ngay, 1 phu thuoc, co dang ky giam tru
		r = compute_mvl(
			MVLInput("Chính thức", 25_000_000, 25_000_000, 1, True, 21, 22, 22), self.cfg
		)
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
		# doc 3.2: F=13.5tr, he so 0.85, 11.5/22 cong, an 9 ngay, co dang ky giam tru, khong BHXH
		r = compute_mvl(
			MVLInput("Thử việc", 13_500_000, 0, 0, True, 9, 22, 11.5), self.cfg
		)
		self.assertEqual(r.I, 5_998_295)
		self.assertEqual(r.K, 6_313_295)
		self.assertEqual(r.O, 0)   # sau giam tru 15.5tr -> 0
		self.assertEqual(r.Q, 0)
		self.assertEqual(r.R, 0)
		self.assertEqual(r.S, 0)
		self.assertEqual(r.T, 6_313_295)
```

- [ ] **Step 2: Run test to verify it fails**

Run: harness với `HARNESS_MODULES=hrms.vn_payroll.test_mvl`. Expected: FAIL (import error `compute_mvl`).

- [ ] **Step 3: Write minimal implementation**

```python
"""Engine tính lương MVL (Miyano) — thuần, không đụng DB. Oracle: docs/Cong_thuc_tinh_luong_MVL.md."""

from dataclasses import dataclass, field


def _round(x) -> float:
	# ROUND(...,0) của Excel = làm tròn nửa lên; Python round() là banker's. Dùng floor(x+0.5).
	from math import floor

	return float(floor(float(x) + 0.5))


@dataclass
class MVLInput:
	salary_type: str
	base: float  # F — lương ngày công
	bhxh_salary: float  # G
	dependents: int  # M
	register_personal_deduction: bool  # L
	lunch_days: float  # số ngày ăn
	standard_days: float  # H7
	worked_days: float  # H


@dataclass
class MVLConfig:
	personal_deduction: float
	dependent_deduction: float
	lunch_rate: float
	ins_company: float
	ins_employee: float
	probation_coef: float
	tax_brackets: list  # [(threshold, rate, subtract)] lũy tiến trên P
	grossup_brackets: list  # [(threshold, subtract, divisor)] quy đổi NET->gross trên O


@dataclass
class MVLResult:
	I: float = 0.0
	J: float = 0.0
	K: float = 0.0
	N: float = 0.0
	O: float = 0.0
	P: float = 0.0
	Q: float = 0.0
	R: float = 0.0
	S: float = 0.0
	T: float = 0.0
	U: float = 0.0


def default_config() -> MVLConfig:
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


def _grossup(O, brackets):
	for threshold, subtract, divisor in brackets:
		if O <= threshold:
			return _round((O - subtract) / divisor)
	return 0.0


def _progressive_tax(P, brackets):
	if P < 0:
		return 0.0
	for threshold, rate, subtract in brackets:
		if P < threshold:
			return _round(P * rate - subtract)
	return 0.0


def _coefficient(salary_type, cfg):
	return cfg.probation_coef if salary_type == "Thử việc" else 1.0


def compute_mvl(inp: MVLInput, cfg: MVLConfig) -> MVLResult:
	r = MVLResult()
	e = _coefficient(inp.salary_type, cfg)
	r.I = inp.base if inp.salary_type == "Khoán" else _round(inp.base * e / inp.standard_days * inp.worked_days)
	is_net_fulltime = inp.salary_type in ("Chính thức", "Thử việc")
	r.J = _round(inp.lunch_days * cfg.lunch_rate) if is_net_fulltime else 0.0
	r.K = r.I + r.J
	r.N = (cfg.personal_deduction if inp.register_personal_deduction else 0) + cfg.dependent_deduction * inp.dependents
	r.O = max(r.K - r.N - r.J, 0.0)
	if is_net_fulltime:
		r.P = _grossup(r.O, cfg.grossup_brackets)
		r.Q = _progressive_tax(r.P, cfg.tax_brackets)
	r.R = _round(inp.bhxh_salary * cfg.ins_company)
	r.S = _round(inp.bhxh_salary * cfg.ins_employee)
	r.T = r.K
	r.U = r.K + r.Q + r.S - r.J
	return r
```

- [ ] **Step 4: Run test to verify it passes**

Run: harness `HARNESS_MODULES=hrms.vn_payroll.test_mvl`. Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add hrms/vn_payroll/__init__.py hrms/vn_payroll/mvl.py hrms/vn_payroll/test_mvl.py
git commit -m "feat(hr): engine luong MVL — buoc loi NET chinh thuc + thu viec"
```

---

### Task 2: Engine — parttime, khoán, cam kết 08, ca biên biểu thuế

**Files:**
- Modify: `hrms/vn_payroll/mvl.py` (nhánh P/Q theo loại)
- Test: `hrms/vn_payroll/test_mvl.py`

**Interfaces:**
- Consumes: `compute_mvl` từ Task 1.
- Produces: `compute_mvl` xử lý đủ `Parttime cư trú` (10%), `Parttime nước ngoài` (20%), `Parttime cam kết 08` (0), `Khoán` (10% trên toàn bộ).

- [ ] **Step 1: Write the failing test** (oracle = doc 3.3 + 3.4)

```python
	def test_parttime_cu_tru_10pct(self):
		# doc 3.3: O = 10tr -> P = 11.111.111 -> Q = 1.111.111
		r = compute_mvl(MVLInput("Parttime cư trú", 10_000_000, 0, 0, False, 0, 22, 22), self.cfg)
		self.assertEqual(r.O, 10_000_000)
		self.assertEqual(r.P, 11_111_111)
		self.assertEqual(r.Q, 1_111_111)
		self.assertEqual(r.T, 10_000_000)

	def test_parttime_nuoc_ngoai_20pct(self):
		# doc 3.3: O = 3tr -> P = 3.750.000 -> Q = 750.000
		r = compute_mvl(MVLInput("Parttime nước ngoài", 3_000_000, 0, 0, False, 0, 22, 22), self.cfg)
		self.assertEqual(r.P, 3_750_000)
		self.assertEqual(r.Q, 750_000)

	def test_parttime_cam_ket_08_khong_thue(self):
		r = compute_mvl(MVLInput("Parttime cam kết 08", 5_000_000, 0, 0, False, 0, 22, 22), self.cfg)
		self.assertEqual(r.P, 0)
		self.assertEqual(r.Q, 0)

	def test_khoan_chuyen_gia(self):
		# doc 3.4: khoan 30tr NET -> P = 33.333.333 -> Q = 3.333.333
		r = compute_mvl(MVLInput("Khoán", 30_000_000, 0, 0, False, 0, 22, 22), self.cfg)
		self.assertEqual(r.I, 30_000_000)  # khong nhan cong
		self.assertEqual(r.P, 33_333_333)
		self.assertEqual(r.Q, 3_333_333)

	def test_tax_bracket_boundaries(self):
		# P dung nguong 10tr -> bac 2 (10% - 500k); 30tr -> bac 3 (20% - 3.5tr)
		self.assertEqual(_progressive_tax(9_999_999, self.cfg.tax_brackets), _round(9_999_999 * 0.05))
		self.assertEqual(_progressive_tax(10_000_000, self.cfg.tax_brackets), _round(10_000_000 * 0.10 - 500_000))
		self.assertEqual(_progressive_tax(30_000_000, self.cfg.tax_brackets), _round(30_000_000 * 0.20 - 3_500_000))
```

(Thêm `from hrms.vn_payroll.mvl import _progressive_tax, _round` vào import test.)

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL (parttime/khoán trả P=0, Q=0 vì Task 1 chỉ set P/Q cho NET fulltime).

- [ ] **Step 3: Write minimal implementation** (thay khối `if is_net_fulltime:` trong `compute_mvl`)

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Expected: PASS (toàn bộ test engine).

- [ ] **Step 5: Commit**

```bash
git add hrms/vn_payroll/mvl.py hrms/vn_payroll/test_mvl.py
git commit -m "feat(hr): engine luong MVL — parttime/khoan/cam ket 08 + ca bien bieu thue"
```

---

### Task 3: MVL Payroll Settings (Single) + 2 child doctypes

**Files:**
- Create: `hrms/hr/doctype/mvl_tax_bracket/{mvl_tax_bracket.json,__init__.py,mvl_tax_bracket.py}`
- Create: `hrms/hr/doctype/mvl_grossup_bracket/{...}`
- Create: `hrms/hr/doctype/mvl_payroll_settings/{mvl_payroll_settings.json,__init__.py,mvl_payroll_settings.py}`
- Create: `hrms/vn_payroll/settings.py` — `config_from_settings() -> MVLConfig`
- Test: `hrms/vn_payroll/test_settings.py`

**Interfaces:**
- Produces: `config_from_settings()` đọc Single `MVL Payroll Settings` → `MVLConfig` (dùng ở Task 5).

- [ ] **Step 1:** Tạo 2 child doctype JSON.
  - `Mvl Tax Bracket` (istable): `threshold_upto` (Currency), `rate` (Percent), `subtract` (Currency).
  - `Mvl Grossup Bracket` (istable): `threshold_upto` (Currency), `subtract` (Currency), `divisor` (Float).

- [ ] **Step 2:** Tạo `MVL Payroll Settings` Single JSON: các field số ở Data model của spec + 2 Table field
  `tax_brackets` (→ Mvl Tax Bracket), `grossup_brackets` (→ Mvl Grossup Bracket). Permissions: System Manager + HR Manager.

- [ ] **Step 3: Write the failing test**

```python
import frappe
from frappe.tests.utils import FrappeTestCase
from hrms.vn_payroll.settings import config_from_settings
from hrms.vn_payroll.setup_mvl import ensure_mvl_defaults


class TestMVLSettings(FrappeTestCase):
	def test_config_from_settings_matches_defaults(self):
		ensure_mvl_defaults()
		cfg = config_from_settings()
		self.assertEqual(cfg.personal_deduction, 15_500_000)
		self.assertEqual(cfg.dependent_deduction, 6_200_000)
		self.assertEqual(cfg.lunch_rate, 35_000)
		self.assertEqual(len(cfg.tax_brackets), 5)
		self.assertEqual(len(cfg.grossup_brackets), 5)
		# bac cuoi = vo cuc
		self.assertEqual(cfg.tax_brackets[-1][0], float("inf"))
```

- [ ] **Step 4:** Cài doctype dev bằng `reload_doc` (script scratchpad), rồi implement `config_from_settings()`:

```python
import frappe
from hrms.vn_payroll.mvl import MVLConfig


def config_from_settings() -> MVLConfig:
	s = frappe.get_single("MVL Payroll Settings")
	tax = [
		(b.threshold_upto or float("inf"), (b.rate or 0) / 100.0, b.subtract or 0)
		for b in s.tax_brackets
	]
	grossup = [
		(b.threshold_upto or float("inf"), b.subtract or 0, b.divisor or 1)
		for b in s.grossup_brackets
	]
	return MVLConfig(
		personal_deduction=s.personal_deduction,
		dependent_deduction=s.dependent_deduction,
		lunch_rate=s.lunch_rate_per_day,
		ins_company=s.insurance_company_rate,
		ins_employee=s.insurance_employee_rate,
		probation_coef=s.probation_coefficient,
		tax_brackets=tax,
		grossup_brackets=grossup,
	)
```

- [ ] **Step 5:** Run harness `HARNESS_MODULES=hrms.vn_payroll.test_settings` → PASS. Commit.

```bash
git add hrms/hr/doctype/mvl_tax_bracket hrms/hr/doctype/mvl_grossup_bracket hrms/hr/doctype/mvl_payroll_settings hrms/vn_payroll/settings.py hrms/vn_payroll/test_settings.py
git commit -m "feat(hr): MVL Payroll Settings + config_from_settings"
```

---

### Task 4: Setup mặc định — components, structure, settings (đóng gói)

**Files:**
- Create: `hrms/vn_payroll/setup_mvl.py` — `ensure_mvl_defaults()`
- Create: custom fields Salary Structure Assignment (trong setup, export fixture ở Task 6)
- Test: `hrms/vn_payroll/test_setup_mvl.py`

**Interfaces:**
- Consumes: engine, settings.
- Produces: `ensure_mvl_defaults()` idempotent tạo: 5 Salary Component, Salary Structure "MVL Việt Nam",
  Single settings mặc định (bậc thuế/gross-up), custom fields SSA. Không ghi đè giá trị đã sửa.

- [ ] **Step 1: Write the failing test**

```python
import frappe
from frappe.tests.utils import FrappeTestCase
from hrms.vn_payroll.setup_mvl import ensure_mvl_defaults


class TestSetupMVL(FrappeTestCase):
	def test_creates_components_and_structure(self):
		ensure_mvl_defaults()
		for c in ("Lương theo công", "Phụ cấp ăn trưa", "Thuế TNCN (nộp thay)",
				  "BHXH - NLĐ (nộp thay)", "BHXH - Công ty"):
			self.assertTrue(frappe.db.exists("Salary Component", c), c)
		self.assertTrue(frappe.db.exists("Salary Structure", "MVL Việt Nam"))
		self.assertTrue(frappe.db.exists("Custom Field", "Salary Structure Assignment-custom_salary_type"))

	def test_idempotent_and_non_destructive(self):
		ensure_mvl_defaults()
		frappe.db.set_single_value("MVL Payroll Settings", "lunch_rate_per_day", 40_000)
		ensure_mvl_defaults()  # chay lai
		self.assertEqual(frappe.db.get_single_value("MVL Payroll Settings", "lunch_rate_per_day"), 40_000)
```

- [ ] **Step 2:** Run harness → FAIL (no `ensure_mvl_defaults`).

- [ ] **Step 3:** Implement `ensure_mvl_defaults()`: tạo component (nếu chưa có), structure, custom fields
  (`create_custom_fields`), và **chỉ seed bậc thuế/gross-up khi settings trống** (không ghi đè). Statistical
  cho Q/S/R (do_not_include_in_total, statistical_component). Component "Phụ cấp ăn trưa" `is_tax_applicable=0`.

- [ ] **Step 4:** Run harness → PASS. Commit.

```bash
git add hrms/vn_payroll/setup_mvl.py hrms/vn_payroll/test_setup_mvl.py
git commit -m "feat(hr): ensure_mvl_defaults — components + structure + custom fields SSA"
```

---

### Task 5: Cầu Salary Slip — gọi engine, gán component + net_pay

**Files:**
- Create: `hrms/vn_payroll/salary_slip_hook.py` — `apply_mvl(doc, method=None)`
- Modify: `hrms/hooks.py` — `doc_events["Salary Slip"]["validate"]`
- Test: `hrms/vn_payroll/test_salary_slip_mvl.py`

**Interfaces:**
- Consumes: `compute_mvl`, `config_from_settings`, custom fields SSA.
- Produces: `apply_mvl(doc)` — nếu slip dùng structure "MVL Việt Nam": đọc SSA + payment_days/total_working_days
  → engine → set component amount + net_pay/gross_pay + custom fields (U, R).

- [ ] **Step 1: Write the failing test** (tích hợp: build NV + SSA + attendance đủ tháng → slip)

```python
import frappe
from frappe.tests.utils import FrappeTestCase, change_settings
from frappe.utils import getdate
from erpnext.setup.doctype.employee.test_employee import make_employee
from hrms.vn_payroll.setup_mvl import ensure_mvl_defaults


class TestSalarySlipMVL(FrappeTestCase):
	@change_settings("Payroll Settings", {"payroll_based_on": "Attendance"})
	def test_chinh_thuc_full_month(self):
		ensure_mvl_defaults()
		emp = make_employee("mvl_ft@codes.com", company="Miyano")
		# SSA: F=base=25tr, chinh thuc, BHXH=25tr, 1 phu thuoc, dang ky giam tru
		frappe.get_doc({
			"doctype": "Salary Structure Assignment", "employee": emp, "company": "Miyano",
			"salary_structure": "MVL Việt Nam", "from_date": "2099-06-01", "base": 25_000_000,
			"custom_salary_type": "Chính thức", "custom_bhxh_salary": 25_000_000,
			"custom_dependents": 1, "custom_register_personal_deduction": 1,
		}).submit()
		# thang 6/2099 khong holiday list -> total_working_days = 30; cham cong du 30 ngay X
		for d in range(1, 31):
			att = frappe.get_doc({"doctype": "Attendance", "employee": emp,
				"attendance_date": f"2099-06-{d:02d}", "custom_attendance_code": "X"})
			att.insert(); att.submit()

		ss = frappe.new_doc("Salary Slip"); ss.employee = emp; ss.salary_structure = "MVL Việt Nam"
		ss.start_date = "2099-06-01"; ss.end_date = "2099-06-30"
		ss.insert()  # validate goi apply_mvl

		comp = {r.salary_component: r.amount for r in ss.earnings + ss.deductions}
		self.assertEqual(comp["Lương theo công"], 25_000_000)   # 30/30 cong
		# net = K = I + J (an mac dinh = payment_days = 30 ngay -> J = 30*35000)
		self.assertEqual(ss.net_pay, 25_000_000 + 30 * 35_000)
```

- [ ] **Step 2:** Run harness → FAIL (apply_mvl chưa gắn / component 0).

- [ ] **Step 3:** Implement `apply_mvl(doc)`:
  - Bỏ qua nếu `doc.salary_structure != "MVL Việt Nam"`.
  - Lấy SSA hiệu lực (`get_assignment`) → base + custom fields.
  - `lunch_days = custom_lunch_days_override or doc.payment_days`.
  - `compute_mvl(MVLInput(...), config_from_settings())`.
  - Gán amount cho từng component (tìm theo tên trong `doc.earnings`/`doc.deductions`).
  - NET: `doc.gross_pay = doc.net_pay = r.K`; GROSS: theo nhánh riêng. Set custom `custom_taxable_income=U`, `custom_ins_company=R`.
  - Wire `hooks.py`: `doc_events = {..., "Salary Slip": {"validate": "hrms.vn_payroll.salary_slip_hook.apply_mvl"}}`.

- [ ] **Step 4:** Run harness → PASS. Kiểm rò rỉ. Commit.

```bash
git add hrms/vn_payroll/salary_slip_hook.py hrms/vn_payroll/test_salary_slip_mvl.py hrms/hooks.py
git commit -m "feat(hr): cau Salary Slip MVL — engine -> component + net_pay"
```

---

### Task 6: Đóng gói — fixtures + after_migrate + phiếu lương

**Files:**
- Modify: `hrms/hooks.py` — `after_migrate` thêm `ensure_mvl_defaults`; `fixtures` thêm components/structure/settings/custom fields.
- Create: `hrms/hr/print_format/phieu_luong_mvl/` — phiếu lương VN (I, J, K, Q, S, R, T, U).
- Test: `hrms/vn_payroll/test_fixtures_sync.py` — filter fixtures khớp doctype thật.

**Interfaces:**
- Consumes: mọi task trước.
- Produces: cài app / migrate là có sẵn cấu hình MVL; phiếu lương in được.

- [ ] **Step 1: Write the failing test** (đồng bộ filter — theo mẫu `test_setup_vn_defaults`)

```python
import frappe
from frappe.tests.utils import FrappeTestCase
from hrms import hooks


class TestMVLFixturesSync(FrappeTestCase):
	def test_custom_field_filter_covers_all_ssa_fields(self):
		live = set(frappe.get_all("Custom Field",
			filters={"dt": "Salary Structure Assignment", "fieldname": ["like", "custom_%"]}, pluck="name"))
		exported = set()
		for f in hooks.fixtures:
			if isinstance(f, dict) and f.get("dt") == "Custom Field":
				exported |= set(f["filters"]["name"][1])
		self.assertTrue(live <= exported, f"thieu trong fixtures: {live - exported}")
```

- [ ] **Step 2:** Run → FAIL (SSA custom fields chưa có trong filter).

- [ ] **Step 3:** Thêm vào `hooks.py`: `after_migrate` += `"hrms.vn_payroll.setup_mvl.ensure_mvl_defaults"`;
  `fixtures` += Salary Component (filter theo 5 tên), Salary Structure "MVL Việt Nam", MVL Payroll Settings,
  và các Custom Field `Salary Structure Assignment-custom_*`. Tạo print format Jinja phiếu lương.

- [ ] **Step 4:** Run → PASS. Commit.

```bash
git add hrms/hooks.py hrms/hr/print_format/phieu_luong_mvl hrms/vn_payroll/test_fixtures_sync.py
git commit -m "feat(hr): dong goi MVL vao app — fixtures + after_migrate + phieu luong"
```

---

### Task 7: E2E + nhập số liệu 6 NV thật (cần dữ liệu từ HR)

**Files:** (không code mới — cài + seed trên `miyano`)

- [ ] **Step 1:** Cài toàn bộ lên `miyano` bằng `reload_doc` + `ensure_mvl_defaults()` (chưa migrate — cổng ask-first).
- [ ] **Step 2:** **STOP — xin số liệu 6 NV** (F, loại lương, G, số phụ thuộc, đăng ký giảm trừ). KHÔNG tự bịa.
- [ ] **Step 3:** Tạo SSA cho 6 NV; sinh Salary Slip tháng 6 + 7/2026 (đã chấm công đủ).
- [ ] **Step 4:** Đối chiếu net_pay với công thức doc thủ công cho ít nhất 1 NV; render phiếu lương.
- [ ] **Step 5:** Chạy full suite + kiểm rò rỉ. Cập nhật memory.

---

## Notes
- Deploy chuẩn cần `bench --site miyano migrate` (re-sync fixtures = cổng ask-first) + `bench build` cho JS.
- GROSS (loại `GROSS`) hiện thực nhánh tối thiểu ở Task 5; Miyano hiện trả toàn NET nên ưu tiên thấp.
