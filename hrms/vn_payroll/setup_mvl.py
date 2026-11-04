# Copyright (c) 2026, Miyano Việt Nam.
"""Đóng gói cấu hình lương MVL vào app: tạo Salary Component + Salary Structure + custom fields +
seed tham số mặc định. Idempotent, KHÔNG ghi đè giá trị HR đã sửa (self-heal mỗi migrate).

Thiết kế payslip NET: lương theo công (I) + phụ cấp ăn (J) là Earning → gross = K. Thuế (Q) và BHXH
NLĐ (S) là Deduction `do_not_include_in_total` → hiện trên phiếu nhưng KHÔNG trừ vào net (công ty nộp
thay) ⇒ net_pay = K tự nhiên. BHXH công ty (R) + thu nhập kê khai (U) lưu ở custom field của slip.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from hrms.vn_payroll.mvl import default_config

# Mọi cột tiền của bảng lương MVL là một Salary Component (auto-sinh trong cấu trúc). Chỉ Lương theo
# công (I) + Phụ cấp ăn (J) là khoản THẬT cộng vào lương; còn lại do_not_include_in_total → hiện trên
# lưới phiếu để đọc đủ như bảng lương nhưng KHÔNG làm sai tổng (thuế/BHXH do công ty nộp thay).
# (tên, loại, is_tax_applicable, do_not_include_in_total)
COMPONENTS = [
	("Lương ngày công", "Earning", 0, 1),  # F — mức lương/công (tham chiếu)
	("Lương đóng BHXH", "Earning", 0, 1),  # G
	("Lương theo công", "Earning", 1, 0),  # I — thật, cộng lương
	("Phụ cấp ăn trưa", "Earning", 0, 0),  # J — thật, miễn thuế
	("Tiền thưởng", "Earning", 1, 0),  # Thưởng (Lễ/Tết), HR nhập — thật, chịu thuế, cộng lương
	# mẫu 09/2026 cột K, L, M — HR nhập (Additional Salary; điện thoại / xăng xe dạng định kỳ), chịu thuế
	("Hỗ trợ điện thoại", "Earning", 1, 0),
	("Hỗ trợ xăng xe", "Earning", 1, 0),
	("Thưởng KPI", "Earning", 1, 0),
	# GƯƠNG CHI PHÍ (hạch toán): đưa thuế TNCN + BHXH công ty nộp thay vào Nợ 6421 của bút toán accrual,
	# KHÔNG cộng net (dnit=1). = Q + S + R. Cân đối để 334 (phải trả NLĐ) ra đúng net K. Xem COMPONENT_ACCOUNT_NUMBERS.
	("Chi phí thuế & BHXH DN nộp thay", "Earning", 0, 1),
	("Tổng thu nhập", "Earning", 0, 1),  # K
	("Thu nhập quy đổi", "Earning", 0, 1),  # O
	("Thu nhập tính thuế", "Earning", 0, 1),  # P
	("Thu nhập chịu thuế kê khai", "Earning", 0, 1),  # U
	("Giảm trừ bản thân", "Deduction", 0, 1),  # L
	("Tổng giảm trừ gia cảnh", "Deduction", 0, 1),  # N
	("Thuế TNCN (nộp thay)", "Deduction", 0, 1),  # Q — công ty nộp thay
	("BHXH - NLĐ (nộp thay)", "Deduction", 0, 1),  # S
	("BHXH - Công ty", "Deduction", 0, 1),  # R
	("KPCĐ - Công ty", "Deduction", 0, 1),  # mẫu 09/2026 cột X — công ty chịu, không trừ net
]
EARNINGS = [c[0] for c in COMPONENTS if c[1] == "Earning"]
DEDUCTIONS = [c[0] for c in COMPONENTS if c[1] == "Deduction"]
# Khoản THẬT cộng vào net (NET mode). GROSS thêm Thuế/BHXH NLĐ vào deduction — xử lý ở apply_mvl.
REAL_EARNINGS = (
	"Lương theo công",
	"Phụ cấp ăn trưa",
	"Hỗ trợ điện thoại",
	"Hỗ trợ xăng xe",
	"Thưởng KPI",
	"Tiền thưởng",
)
# Component HR TỰ NHẬP theo kỳ (gõ trên phiếu hoặc Additional Salary) — engine đọc chứ KHÔNG ghi đè.
# Mẫu 09/2026 tính thuế mọi khoản này như nhau (vào O, chịu thuế), nên engine nhận TỔNG của chúng.
# "Tiền thưởng" = cột Thưởng (Lễ/Tết) của mẫu; giữ tên cũ vì phiếu và bút toán đã dùng.
HR_ENTERED_COMPONENTS = ("Tiền thưởng", "Hỗ trợ điện thoại", "Hỗ trợ xăng xe", "Thưởng KPI")

# MỖI LOẠI lương = MỘT Salary Structure riêng, gắn cho NV tương ứng. Thành phần mỗi cấu trúc chỉ gồm
# đúng các cột XUẤT HIỆN cho loại đó trên bảng Excel: NET toàn thời gian (chính thức/thử việc) có đủ ăn
# trưa + giảm trừ (+ BHXH cho chính thức); parttime & khoán tối giản (không ăn, không BHXH, không giảm
# trừ). Loại lương suy TỪ cấu trúc (apply_mvl) nên HR chỉ cần gán đúng cấu trúc, không chọn loại tay.
# GROSS bị BỎ: engine chưa hiện thực nhánh GROSS (P/Q về 0) → phiếu sai âm thầm. Miyano trả TOÀN NET.
# {tên cấu trúc: (loại lương, [earnings], [deductions])}
_PARTTIME_LIKE = [
	"Lương ngày công",
	"Lương theo công",
	"Tiền thưởng",  # Thưởng (Lễ/Tết) — mẫu 09/2026 dòng 6
	"Chi phí thuế & BHXH DN nộp thay",  # gương chi phí cho bút toán accrual (= Q, parttime/chuyên gia không BHXH)
	"Tổng thu nhập",
	"Thu nhập quy đổi",
	"Thu nhập tính thuế",
	"Thu nhập chịu thuế kê khai",
]
STRUCTURES = {
	"Chính thức": (
		"Chính thức",
		[
			"Lương ngày công",
			"Lương đóng BHXH",
			"Lương theo công",
			"Phụ cấp ăn trưa",
			"Hỗ trợ điện thoại",
			"Hỗ trợ xăng xe",
			"Thưởng KPI",
			"Tiền thưởng",
			"Chi phí thuế & BHXH DN nộp thay",  # gương chi phí (= Q+S+R) cho bút toán accrual
			"Tổng thu nhập",
			"Thu nhập quy đổi",
			"Thu nhập tính thuế",
			"Thu nhập chịu thuế kê khai",
		],
		[
			"Giảm trừ bản thân",
			"Tổng giảm trừ gia cảnh",
			"Thuế TNCN (nộp thay)",
			"BHXH - NLĐ (nộp thay)",
			"BHXH - Công ty",
			"KPCĐ - Công ty",
		],
	),
	"Thử việc": (
		"Thử việc",
		[
			"Lương ngày công",
			"Lương theo công",
			"Phụ cấp ăn trưa",
			"Hỗ trợ điện thoại",
			"Hỗ trợ xăng xe",
			"Thưởng KPI",
			"Tiền thưởng",
			"Chi phí thuế & BHXH DN nộp thay",  # gương chi phí = 0: thử việc tự chịu thuế, không BHXH
			"Tổng thu nhập",
			"Thu nhập quy đổi",
			"Thu nhập tính thuế",
			"Thu nhập chịu thuế kê khai",
		],
		# thử việc không đóng BHXH; Thuế TNCN là khoản trừ THẬT (NLĐ tự chịu — mẫu 10/2026, apply_mvl)
		["Giảm trừ bản thân", "Tổng giảm trừ gia cảnh", "Thuế TNCN (nộp thay)"],
	),
	# Bán thời gian: cư trú + đăng ký giảm trừ → giảm trừ + lũy tiến như chính thức; còn lại khấu trừ 10%
	# (cư trú) / 20% (không cư trú) — chọn qua cờ trên SSA. Có cột giảm trừ để phiếu hiện được N.
	"Bán thời gian": (
		"Bán thời gian",
		_PARTTIME_LIKE,
		["Giảm trừ bản thân", "Tổng giảm trừ gia cảnh", "Thuế TNCN (nộp thay)"],
	),
	# Khoán: trọn gói, KHÔNG khấu trừ thuế, nhưng VẪN kê khai thu nhập chịu thuế U (= K; bảng lương
	# 10/2026 dòng 22, HR chốt 2026-11-04). Gương chi phí = 0 (Q=0) nhưng vẫn có để cấu trúc đồng nhất
	# (bút toán ra Nợ 6421 = I / Có 334 = I).
	"Khoán": (
		"Khoán",
		[
			"Lương ngày công",
			"Lương theo công",
			"Tiền thưởng",
			"Chi phí thuế & BHXH DN nộp thay",
			"Tổng thu nhập",
			"Thu nhập quy đổi",
			"Thu nhập tính thuế",
			"Thu nhập chịu thuế kê khai",
		],
		["Thuế TNCN (nộp thay)"],
	),
	# Chuyên gia: thù lao trọn gói, khấu trừ 10%.
	"Chuyên gia": ("Chuyên gia", _PARTTIME_LIKE, ["Thuế TNCN (nộp thay)"]),
}
STRUCTURE_NAMES = tuple(STRUCTURES)
_TYPE_TO_STRUCTURE = {row[0]: name for name, row in STRUCTURES.items()}

# ---- HẠCH TOÁN (bút toán accrual lương qua Payroll Entry) ----
# Chỉ các component dưới đây vào bút toán (map TK GL per company); MỌI component khác bị loại khỏi JV
# (do_not_include_in_accounts=1 — chúng chỉ là cột hiển thị/tham chiếu, đưa vào sẽ nhân trùng).
# Mô hình NET gross-up (doc §9): Nợ 6421 = I+J+phụ cấp+thưởng + (Q+S+R+KPCĐ) ; Có 3335 = Q ;
# Có 3383 = S+R ; Có 3382 = KPCĐ ; phần dư của JV về Có 334 (payroll payable) = K = net thực trả.
# TK theo account_number VAS của Miyano.
COMPONENT_ACCOUNT_NUMBERS = {
	"Lương theo công": "6421",  # chi phí nhân viên quản lý (Nợ)
	"Phụ cấp ăn trưa": "6421",
	"Tiền thưởng": "6421",
	"Hỗ trợ điện thoại": "6421",
	"Hỗ trợ xăng xe": "6421",
	"Thưởng KPI": "6421",
	"Chi phí thuế & BHXH DN nộp thay": "6421",  # gương chi phí thuế/BHXH nộp thay (Nợ)
	"Thuế TNCN (nộp thay)": "3335",  # thuế TNCN phải nộp (Có)
	"BHXH - NLĐ (nộp thay)": "3383",  # BHXH phải nộp (Có)
	"BHXH - Công ty": "3383",
	"KPCĐ - Công ty": "3382",  # kinh phí công đoàn phải nộp (Có); chi phí đã nằm trong gương 6421
}
# Danh sách loại lương (giữ cho custom field Select trên SSA — chỉ để hiển thị, apply_mvl suy từ cấu trúc)
SALARY_TYPES = "\n".join(row[0] for row in STRUCTURES.values())


def salary_type_of(structure: str) -> str | None:
	"""Loại lương của một Salary Structure MVL; None nếu không phải cấu trúc MVL (slip đi đường Frappe)."""
	row = STRUCTURES.get(structure)
	return row[0] if row else None


def structure_for_type(salary_type: str) -> str:
	"""Tên Salary Structure ứng với loại lương (một-một) — dùng khi tạo SSA/slip. Mặc định chính thức."""
	return _TYPE_TO_STRUCTURE.get(salary_type, "Chính thức")


def ensure_components():
	for name, ctype, taxable, do_not_include in COMPONENTS:
		if frappe.db.exists("Salary Component", name):
			# self-heal: engine điền amount khi validate, nên component KHÔNG được biến mất khi = 0
			frappe.db.set_value("Salary Component", name, "remove_if_zero_valued", 0)
			continue
		frappe.get_doc(
			{
				"doctype": "Salary Component",
				"salary_component": name,
				"salary_component_abbr": None,
				"type": ctype,
				"is_tax_applicable": taxable,
				"do_not_include_in_total": do_not_include,
				"depends_on_payment_days": 0,  # engine đã tính theo công, không để Frappe prorate lại
				"remove_if_zero_valued": 0,  # giữ lại dù amount = 0 → apply_mvl mới có row để điền
				"description": "Tự sinh cho lương MVL (đừng xoá).",
			}
		).insert(ignore_permissions=True)


def ensure_structures():
	"""Tạo/đồng bộ MỖI cấu trúc lương MVL với đúng tập component của loại đó (idempotent, additive).

	Mỗi loại lương một Salary Structure riêng; chỉ thêm component còn thiếu, không gỡ (giữ chỉnh tay của
	HR). Submit để dùng được trong Salary Structure Assignment.
	"""
	company = frappe.defaults.get_defaults().get("company") or frappe.db.get_value("Company", {}, "name")
	if not company:
		return  # cài app trước setup wizard → chưa có Company; để after_migrate tạo cấu trúc khi đã có
	for name, (_stype, earnings, deductions) in STRUCTURES.items():
		if not frappe.db.exists("Salary Structure", name):
			frappe.get_doc(
				{
					"doctype": "Salary Structure",
					"name": name,
					"company": company,
					"is_active": "Yes",
					"payroll_frequency": "Monthly",
				}
			).insert(ignore_permissions=True)

		doc = frappe.get_doc("Salary Structure", name)
		changed = False
		for table, comps in (("earnings", earnings), ("deductions", deductions)):
			present = {r.salary_component for r in doc.get(table)}
			for comp in comps:
				if comp not in present:
					doc.append(table, {"salary_component": comp, "amount": 0})
					changed = True
		if changed:
			if doc.docstatus == 1:
				doc.db_set("docstatus", 0)  # cho phép sửa rồi submit lại
			doc.flags.ignore_validate_update_after_submit = True
			doc.save(ignore_permissions=True)
			doc.db_set("docstatus", 1)  # submit để dùng trong Salary Structure Assignment


# Tham số KHÔNG phải tiền (không làm Salary Component được): hệ số E, số phụ thuộc M, loại lương.
# Mọi cột TIỀN (F,G,K,L,N,O,P,Q,R,S,U) là Salary Component. Số công H = payment_days native.
def _slip_breakdown_fields():
	ro = {"read_only": 1}

	def f(fieldname, label, fieldtype, after):
		return {"fieldname": fieldname, "label": label, "fieldtype": fieldtype, "insert_after": after, **ro}

	return [
		{
			"fieldname": "custom_mvl_section",
			"fieldtype": "Section Break",
			"label": "Chi tiết lương MVL",
			"insert_after": "net_pay",
		},
		f("custom_salary_type", "Loại lương", "Data", "custom_mvl_section"),
		f("custom_coefficient", "Hệ số lương (E)", "Float", "custom_salary_type"),
		f("custom_dependents_slip", "Số người phụ thuộc (M)", "Int", "custom_coefficient"),
		f("custom_lunch_days", "Số ngày ăn trưa", "Int", "custom_dependents_slip"),
		# buổi ăn giữ lại (không nộp quỹ canteen) — phụ cấp ăn trưa vẫn trả đủ, chỉ để tab Ăn trưa đọc
		f("custom_lunch_kept_days", "Số buổi giữ lại tiền ăn", "Int", "custom_lunch_days"),
	]


# Custom field tiền cũ (nay đã chuyển thành Salary Component) → gỡ khỏi phiếu khi migrate/execute.
OBSOLETE_SLIP_FIELDS = [
	"custom_base_salary",
	"custom_bhxh_salary_slip",
	"custom_gross_income",
	"custom_personal_deduction",
	"custom_total_deduction",
	"custom_converted_income",
	"custom_taxable_income_gross",
	"custom_taxable_income",
	"custom_ins_company",
	"custom_mvl_col1",
	"custom_mvl_col2",
]


# Mô tả hiển thị dưới các ô MVL. Một nguồn cho cả lúc tạo field lẫn lúc đồng bộ: site đã cài thì
# guard của `ensure_custom_fields` không chạy lại `create_custom_fields`, nên đổi luật mà chỉ sửa chữ
# trong danh sách field thì HR vẫn đọc hướng dẫn cũ (`sync_field_descriptions`).
FIELD_DESCRIPTIONS = {
	("Salary Structure Assignment", "custom_bhxh_salary"): (
		"Chỉ Chính thức đóng BHXH và KPCĐ theo mức này; loại khác bỏ qua ô này. Để trống → không đóng."
	),
	("Salary Structure Assignment", "custom_register_personal_deduction"): (
		"Tick → được giảm trừ bản thân. Với Bán thời gian cư trú, tick còn chuyển sang giảm trừ gia cảnh"
		" + thuế lũy tiến như chính thức; bỏ tick → khấu trừ 10%. Khoán / Chuyên gia bỏ qua ô này."
	),
	("Salary Structure Assignment", "custom_lunch_days_override"): (
		"Để trống → dùng số công thực tế (payment_days)."
	),
	("Salary Structure Assignment", "custom_is_resident"): (
		"Chỉ dùng cho Bán thời gian: tick = cư trú → theo ô Đăng ký giảm trừ (lũy tiến hoặc khấu trừ 10%);"
		" bỏ tick = không cư trú / người nước ngoài → khấu trừ 20%."
	),
}


def ssa_help(fieldname: str) -> str:
	return FIELD_DESCRIPTIONS[("Salary Structure Assignment", fieldname)]


def sync_field_descriptions():
	"""Đưa mô tả của field đã tồn tại về `FIELD_DESCRIPTIONS`. Chỉ ghi metadata (không DDL) → an toàn
	mỗi lần migrate và trong test."""
	changed = set()
	for (doctype, fieldname), text in FIELD_DESCRIPTIONS.items():
		name = f"{doctype}-{fieldname}"
		row = frappe.db.get_value("Custom Field", name, ["name", "description"], as_dict=True)
		if row and row.description != text:
			frappe.db.set_value("Custom Field", name, "description", text)
			changed.add(doctype)
	for doctype in changed:
		frappe.clear_cache(doctype=doctype)


def ensure_custom_fields():
	# create_custom_fields / delete đều chạy ALTER TABLE (DDL) → ImplicitCommitError trong transaction
	# của test. Guard: đã đúng trạng thái (mọi field MỚI có + field tiền cũ đã gỡ) thì thôi. Chỉ đụng schema
	# khi chưa đúng → chạy lúc migrate/execute (ngoài test); test dựa vào migrate đã dọn sẵn.
	# Guard liệt kê MỌI field mới nhất (kể cả custom_is_resident) → thêm field sau này là tự self-heal khi
	# migrate (create_custom_fields idempotent: cập nhật field có + tạo field thiếu + đồng bộ options Select).
	ready = (
		frappe.db.exists("Custom Field", "Salary Slip-custom_lunch_days")
		and frappe.db.exists("Custom Field", "Salary Structure Assignment-custom_is_resident")
		and not frappe.db.exists("Custom Field", "Salary Slip-custom_base_salary")
	)
	if ready:
		return
	for fn in OBSOLETE_SLIP_FIELDS:
		frappe.delete_doc_if_exists("Custom Field", f"Salary Slip-{fn}")
	create_custom_fields(
		{
			"Salary Structure Assignment": [
				{
					"fieldname": "custom_mvl_section",
					"fieldtype": "Section Break",
					"label": "Cấu hình lương MVL",
					"insert_after": "base",
				},
				{
					"fieldname": "custom_salary_type",
					"fieldtype": "Select",
					"label": "Loại lương",
					"options": SALARY_TYPES,
					"default": "Chính thức",
					"insert_after": "custom_mvl_section",
				},
				{
					"fieldname": "custom_bhxh_salary",
					"fieldtype": "Currency",
					"label": "Lương đóng BHXH (G)",
					"description": ssa_help("custom_bhxh_salary"),
					"insert_after": "custom_salary_type",
				},
				{
					"fieldname": "custom_dependents",
					"fieldtype": "Int",
					"label": "Số người phụ thuộc",
					"insert_after": "custom_bhxh_salary",
				},
				{
					"fieldname": "custom_register_personal_deduction",
					"fieldtype": "Check",
					"label": "Đăng ký giảm trừ bản thân",
					"description": ssa_help("custom_register_personal_deduction"),
					"insert_after": "custom_dependents",
				},
				{
					"fieldname": "custom_lunch_days_override",
					"fieldtype": "Int",
					"label": "Số ngày ăn (nếu khác số công)",
					"description": ssa_help("custom_lunch_days_override"),
					"insert_after": "custom_register_personal_deduction",
				},
				{
					"fieldname": "custom_is_resident",
					"fieldtype": "Check",
					"default": "1",
					"label": "Cá nhân cư trú",
					"description": ssa_help("custom_is_resident"),
					"insert_after": "custom_lunch_days_override",
				},
			],
			"Salary Slip": _slip_breakdown_fields(),
		},
		ignore_validate=True,
	)


def ensure_settings():
	"""Seed tham số + biểu thuế/gross-up vào tab "Lương Miyano (VN)" của Payroll Settings CHỈ khi chưa
	có (không ghi đè giá trị HR đã sửa).

	Chỉ lưu khi thật sự seed: chạy mỗi migrate, mà lưu Payroll Settings là chạy cả `on_update` của
	upstream (property setter làm tròn + xoá cache toàn site) — không có lý do làm vậy khi chẳng đổi gì."""
	s = frappe.get_single("Payroll Settings")
	if not s.meta.has_field("personal_deduction"):
		return  # meta chưa đồng bộ (chưa migrate doctype) — lần migrate sau sẽ seed
	cfg = default_config()
	changed = False
	if not s.personal_deduction:
		changed = True
		s.personal_deduction = cfg.personal_deduction
		s.dependent_deduction = cfg.dependent_deduction
		s.lunch_rate_per_day = cfg.lunch_rate
		s.insurance_company_rate = cfg.ins_company
		s.insurance_employee_rate = cfg.ins_employee
		s.probation_coefficient = cfg.probation_coef
	if not s.tax_brackets:
		changed = True
		for threshold, rate, subtract in cfg.tax_brackets:
			s.append(
				"tax_brackets",
				{
					"threshold_upto": None if threshold == float("inf") else threshold,
					"rate": rate * 100,
					"subtract": subtract,
				},
			)
	if not s.grossup_brackets:
		changed = True
		for threshold, subtract, divisor in cfg.grossup_brackets:
			s.append(
				"grossup_brackets",
				{
					"threshold_upto": None if threshold == float("inf") else threshold,
					"subtract": subtract,
					"divisor": divisor,
				},
			)
	# Seed KPCĐ khi CHƯA CÓ dòng nào — không dùng `if not s.union_fee_rate`: số 0 là HR cố ý không thu.
	if s.meta.has_field("union_fee_rate") and not frappe.db.sql(
		"select 1 from `tabSingles` where doctype = %s and field = 'union_fee_rate'", s.doctype
	):
		s.union_fee_rate = cfg.union_fee_rate
		changed = True
	if changed:
		s.save(ignore_permissions=True)


PRINT_FORMAT = "Phiếu lương MVL"


def ensure_default_print_format():
	"""Đặt "Phiếu lương MVL" làm print format mặc định của Salary Slip → nút In hiện phiếu đủ thành
	phần thay vì mẫu chuẩn của Frappe (chỉ có lưới earnings/deductions)."""
	if not frappe.db.exists("Print Format", PRINT_FORMAT):
		return  # print format là standard doc, đồng bộ khi migrate/reload — chưa có thì bỏ qua
	existing = frappe.db.get_value(
		"Property Setter", {"doc_type": "Salary Slip", "property": "default_print_format"}, "name"
	)
	if existing:
		frappe.db.set_value("Property Setter", existing, "value", PRINT_FORMAT)
		return
	frappe.get_doc(
		{
			"doctype": "Property Setter",
			"doctype_or_field": "DocType",
			"doc_type": "Salary Slip",
			"property": "default_print_format",
			"value": PRINT_FORMAT,
			"property_type": "Data",
		}
	).insert(ignore_permissions=True)


def ensure_component_accounts():
	"""Map Salary Component → Tài khoản GL (per company) cho bút toán accrual lương + loại các cột hiển thị
	khỏi JV (do_not_include_in_accounts). Idempotent; tự bỏ qua company chưa có TK tương ứng (cài ngoài
	Miyano) → an toàn, không dựng bút toán sai. Chạy khi migrate/execute (thao tác DML, không DDL)."""
	company = frappe.defaults.get_defaults().get("company") or frappe.db.get_value("Company", {}, "name")
	if not company:
		return

	# Cột hiển thị/tham chiếu (không có trong COMPONENT_ACCOUNT_NUMBERS) → loại khỏi bút toán; component
	# hạch toán → giữ trong bút toán (do_not_include_in_accounts=0).
	accounted = set(COMPONENT_ACCOUNT_NUMBERS)
	for name, *_ in COMPONENTS:
		frappe.db.set_value(
			"Salary Component", name, "do_not_include_in_accounts", 0 if name in accounted else 1
		)

	# Salary Slip COPY cờ do_not_include_in_accounts TỪ detail row của Salary Structure (không từ component
	# master) khi tạo phiếu → phải đồng bộ cờ lên cả row cấu trúc, nếu không cột hiển thị vẫn lọt vào JV.
	for sname in STRUCTURE_NAMES:
		for r in frappe.get_all(
			"Salary Detail",
			filters={"parent": sname, "parenttype": "Salary Structure"},
			fields=["name", "salary_component"],
		):
			frappe.db.set_value(
				"Salary Detail",
				r.name,
				"do_not_include_in_accounts",
				0 if r.salary_component in accounted else 1,
			)

	for comp, acct_num in COMPONENT_ACCOUNT_NUMBERS.items():
		account = frappe.db.get_value(
			"Account", {"account_number": acct_num, "company": company, "is_group": 0}, "name"
		)
		if not account:
			continue  # company không có TK VAS này → bỏ qua (self-heal khi cài site khác)
		if frappe.db.exists("Salary Component Account", {"parent": comp, "company": company}):
			continue
		doc = frappe.get_doc("Salary Component", comp)
		doc.append("accounts", {"company": company, "account": account})
		doc.flags.ignore_permissions = True
		doc.save()


def ensure_mvl_defaults():
	"""Điểm vào duy nhất: gọi khi after_install / after_migrate và trong test."""
	ensure_components()
	ensure_custom_fields()
	sync_field_descriptions()
	ensure_structures()
	ensure_component_accounts()
	ensure_settings()
	ensure_default_print_format()
