# Implementation Plan: Phiếu lương Miyano theo loại (mẫu 09/2026)

> Danh sách việc: `docs/tasks/plan-miyano-payslip-types-todo.md`. Nguồn: mẫu `docs/Salary_template_clean.xlsx`,
> quy tắc 06/2026 `docs/Cong_thuc_tinh_luong_MVL.md`, spec `docs/spec/vn-payroll-mvl.md`.

## Overview

Mỗi dòng của mẫu bảng lương 09/2026 là một loại phiếu lương (Chính thức, Thử việc, Bán thời gian;
Khoán và Chuyên gia không có dòng mẫu, giữ quy tắc 06/2026). Mục tiêu: đủ component cho từng loại, đúng từng con số của mẫu trên
phiếu, báo cáo, file Excel và bút toán. Kiến trúc MVL giữ nguyên: engine thuần `hrms/vn_payroll/mvl.py`
tính số, hook `salary_slip_hook.apply_mvl` ghi số lên component, mỗi loại lương một Salary Structure.

## Hiện trạng (kiểm 2026-10-30)

Chạy 6 dòng mẫu qua engine với tham số đang có trên site: 5/6 dòng khớp mọi cột (≤ 1đ do làm tròn).

| Dòng mẫu      | Loại                                              | Số liệu                        | Component còn thiếu                                               |
| --------------- | -------------------------------------------------- | -------------------------------- | ------------------------------------------------------------------- |
| 1 Nguyen Van A  | Chính thức, đủ phụ cấp                       | ✅                               | điện thoại, xăng xe, KPCĐ                                      |
| 2 Tran Thi B    | Chính thức                                       | ✅                               | KPCĐ                                                               |
| 3 Truong Xuan C | Chính thức + KPI                                 | ✅                               | Thưởng KPI (đang phải gộp vào Tiền thưởng), KPCĐ          |
| 4 To Phuong D   | Thử việc 0,85                                    | ❌ tính bảo hiểm khi có G    | điện thoại, xăng xe, KPI                                        |
| 5 Pham Van E    | Chính thức, G < F                                | ✅                               | KPCĐ                                                               |
| 6 Nguyen Kim G  | Bán thời gian, có đăng ký giảm trừ (1 NPT) | ✅ nhưng do trùng hợp (O = 0) | Thưởng Lễ/Tết; giảm trừ không hiện trên phiếu / báo cáo |
| —              | Bán thời gian, không đăng ký giảm trừ      | ✅ (10% / 20%)                   | Thưởng Lễ/Tết                                                   |
| —              | Khoán / Chuyên gia                               | ❌ trừ gia cảnh nếu tick      | Thưởng Lễ/Tết                                                   |

Dòng 6 khớp chỉ vì 5,5tr nhỏ hơn giảm trừ: engine đang trừ gia cảnh rồi khấu trừ 10% (lai giữa hai cách).
Thu nhập 20tr có đăng ký thì engine ra 500.000, còn cách của mẫu (lũy tiến) ra 236.842.

Báo cáo `MVL Salary Register` thiếu cột Tiền thưởng (I + J ≠ K khi có thưởng), thiếu KPCĐ, và đang dùng bố cục cột 06/2026.

## Architecture Decisions

- **Engine giữ một input `bonus` = tổng mọi khoản HR nhập** (Lễ/Tết, KPI, điện thoại, xăng xe). Mẫu xử
  lý thuế 4 khoản này giống hệt nhau: cùng vào O, cùng vào S, chỉ J được loại. Tách input là YAGNI; tách
  chỉ cần ở component, để hiện được từng cột.
- **Cả 4 khoản nhập qua Additional Salary** (native, Payroll Entry tự nhận). Điện thoại / xăng xe dùng
  Additional Salary *định kỳ* (`is_recurring`, from/to date). Không thêm custom field SSA, vì đó là DDL
  chỉ chạy được bằng migrate trên site thật, và harness rollback không chịu được DDL.
- **Chặn theo loại nằm trong engine**, không dựa vào việc cấu trúc thiếu component. Bảo hiểm và KPCĐ chỉ
  tính cho `Chính thức`. Hiện nay engine tính rồi cấu trúc giấu đi, nhưng con số vẫn lọt vào U và vào
  khoản gương chi phí.
- **Thuế part time theo cờ `custom_register_personal_deduction` có sẵn trên SSA** (chốt 2026-10-30, D1).
  Không thêm field mới:

  | Bán thời gian                                 | Giảm trừ        | Thuế                                            |
  | ----------------------------------------------- | ----------------- | ------------------------------------------------ |
  | cư trú + có đăng ký (HĐLĐ từ 3 tháng) | như Chính thức | quy đổi bậc → lũy tiến (như mẫu dòng 6) |
  | cư trú, không đăng ký                     | 0                 | O/0,9 × 10% (06/2026)                           |
  | không cư trú                                 | 0, bỏ qua cờ    | O/0,8 × 20% (06/2026)                           |

  Khoán / Chuyên gia: luôn không giảm trừ.
- **Không đổi tên** component cũ (`Tiền thưởng` = Lễ/Tết) và không đổi tên field engine (`MVLResult.I…U`);
  đổi tên = migration phiếu và GL cũ. Chữ cột của mẫu mới chỉ nằm ở nhãn báo cáo.
- **Component mới phải có TK GL ngay trong task tạo ra nó.** Thiếu TK thì `make_accrual_jv_entry` của
  Payroll Entry báo "Please set account" (đã dính 2026-07-28).

## Dependency Graph

```
MVL Payroll Settings.union_fee_rate ──┐
                                      ▼
                 engine mvl.py (chặn BH/giảm trừ, KPCĐ X)
                                      │
setup_mvl: component + cấu trúc + TK GL ─┤
                                      ▼
            salary_slip_hook (đọc khoản HR nhập, ghi component, gương chi phí)
                                      │
             ┌────────────────────────┼─────────────────────────┐
             ▼                        ▼                         ▼
  báo cáo MVL Salary Register  phiếu in Phiếu lương MVL   bút toán Payroll Entry
             │
             ▼
     file Excel salary_xlsx
```

## Ràng buộc chung (mọi task)

- **KHÔNG** `bench --site miyano run-tests`. Test chạy qua harness rollback theo
  `docs/tasks/plan-attendance-exempt.md` mục "Chạy test (harness rollback)". Thêm `"Salary Structure Assignment", "Additional Salary"` vào `WATCH`. Một task chỉ xong khi có `RESULT: OK` + `HARNESS_NO_LEAK`.
- Mốc đỏ có sẵn: `test_salary_slip_mvl` đỏ 9 test (2026-10-13). Ghi mốc trước Task 1; chỉ test mới đỏ mới là hồi quy.
- Không commit / không tạo nhánh (Git rule trong `CLAUDE.md`).
- ruff sạch trên file đã sửa: `~/.cache/pre-commit/repo5reog86s/py_env-python3.12/bin/ruff check <files>`.
- Không migrate / không đụng TK GL trên site khi chưa ký duyệt (xem các checkpoint).

## Task List

### Phase 1: Sửa công thức sai (rủi ro cao → làm trước)

#### Task 1: Phiếu Thử việc không bao giờ có bảo hiểm

**Description:** Engine chỉ tính R (BH công ty) và S (BH NLĐ) cho loại `Chính thức`. Phiếu Thử việc có
`custom_bhxh_salary > 0` phải ra như dòng 4 của mẫu: R = S = 0, U không cộng S, gương chi phí = Q.

**Acceptance criteria:**

- [ ] Dòng 4 mẫu (Thử việc, F = G = 10tr, 20 ngày ăn, thưởng 2tr): I = 8.500.000, K = 11.200.000, R = S = 0, U = 10.500.000.
- [ ] Phiếu Thử việc trên Salary Slip (harness): gương "Chi phí thuế & BHXH DN nộp thay" = Thuế TNCN.
- [ ] Phiếu Chính thức giữa kỳ (hệ số pha trộn từ thử việc) vẫn đóng BH trên trọn G, như hiện nay.

**Verification:**

- [ ] `run_test.sh hrms.vn_payroll.tests.test_mvl` → test mới `test_template_row4_probation` xanh, các test 06/2026 vẫn xanh.
- [ ] `run_test.sh hrms.vn_payroll.tests.test_salary_slip_mvl` → `test_probation_slip_has_no_insurance_even_with_bhxh_salary` xanh, không vượt mốc đỏ.

**Dependencies:** None
**Files likely touched:** `hrms/vn_payroll/mvl.py` (hằng `INSURED_TYPES = ("Chính thức",)`), `hrms/vn_payroll/tests/test_mvl.py`, `hrms/vn_payroll/tests/test_salary_slip_mvl.py`
**Estimated scope:** S

#### Task 2: Thuế part time theo cờ đăng ký giảm trừ; Khoán / Chuyên gia không trừ gia cảnh

**Description:** Engine rẽ nhánh Bán thời gian theo bảng ở Architecture Decisions: cư trú + đăng ký thì
đi đường Chính thức (N, quy đổi bậc, lũy tiến); còn lại N = 0 và khấu trừ 10% / 20% như cũ. Khoán /
Chuyên gia luôn N = 0. Cấu trúc Bán thời gian thêm `Giảm trừ bản thân` + `Tổng giảm trừ gia cảnh` để
phiếu và báo cáo hiện được giảm trừ.

**Acceptance criteria:**

- [ ] Dòng 6 mẫu (Bán thời gian F = 5tr, 22/22, Lễ/Tết 500k, cư trú, có đăng ký, 1 NPT): K = 5.500.000, N = 21.700.000, O = 0, Q = 0, U = 5.500.000.
- [ ] Bán thời gian F = 20tr cư trú: có đăng ký, 0 NPT → Q = 236.842; không đăng ký → Q = 2.222.222; không cư trú có tick → N = 0, Q = 5.000.000.
- [ ] Chuyên gia / Khoán có tick → N = 0. Ví dụ 06/2026 (Vũ Văn Tiến Tuyền, Koshioka Hiroshi) không đổi.

**Verification:**

- [ ] `run_test.sh hrms.vn_payroll.tests.test_mvl` → `test_template_row6_parttime_registered`, `test_parttime_tax_follows_registration_flag`, `test_khoan_chuyen_gia_ignore_family_deduction` xanh.
- [ ] `run_test.sh hrms.vn_payroll.tests.test_setup_mvl` (bảng component của cấu trúc Bán thời gian) xanh.

**Dependencies:** None (cùng file với Task 1 nên làm nối tiếp)
**Files likely touched:** `hrms/vn_payroll/mvl.py`, `hrms/vn_payroll/setup_mvl.py` (`STRUCTURES`), `hrms/vn_payroll/tests/test_mvl.py`, `hrms/vn_payroll/tests/test_setup_mvl.py`
**Estimated scope:** S

### Checkpoint A: Sau Task 1–2

- [ ] `test_mvl`, `test_salary_slip_mvl`, `test_sheet_gate`, `hrms.tests.test_payroll_gate` không có đỏ mới.
- [ ] **Bất biến:** tính lại 6 phiếu nháp T7/2026 trên site (`run_method("validate")`, không lưu,
  `frappe.conf.hrms_enforce_sheet_gate = 0`) → `net_pay` + Thuế TNCN y như trước. (SSA hiện tại:
  Thử việc G = 0; 2 Bán thời gian đều không tick đăng ký, 1 người không cư trú → kỳ vọng không đổi.)

### Phase 2: Khoản thu nhập HR nhập

#### Task 3: Mọi loại phiếu nhận được Thưởng (Lễ/Tết) và báo cáo hiện cột này

**Description:** Thêm `Tiền thưởng` vào cấu trúc Bán thời gian / Khoán / Chuyên gia. Hook cộng **mọi**
row của component HR nhập (Additional Salary + gõ tay). Báo cáo thêm cột "Thưởng (Lễ/Tết)", sửa lỗi I + J ≠ K.

**Acceptance criteria:**

- [ ] Dòng 6 mẫu (Bán thời gian có đăng ký, Lễ/Tết 500k qua Additional Salary): net 5.500.000, Q = 0, U = 5.500.000. Khoán có Lễ/Tết → Q vẫn = 0.
- [ ] Hai row `Tiền thưởng` trên một phiếu (1tr + 2tr) → Tổng thu nhập tăng 3tr.
- [ ] Báo cáo có cột `holiday_bonus` ngay trước Tổng thu nhập, có trong dòng TỔNG CỘNG; phiếu cũ không có row → 0.

**Verification:**

- [ ] `run_test.sh hrms.vn_payroll.tests.test_setup_mvl` (bảng component theo cấu trúc) xanh.
- [ ] `run_test.sh hrms.vn_payroll.tests.test_salary_slip_mvl` → `test_template_row6_parttime_holiday_bonus`, `test_khoan_holiday_bonus_untaxed`, `test_bonus_rows_are_summed` xanh.
- [ ] `run_test.sh hrms.payroll.report.mvl_salary_register.test_mvl_salary_register` xanh.

**Dependencies:** Task 2
**Files likely touched:** `hrms/vn_payroll/setup_mvl.py` (`STRUCTURES`, `HR_ENTERED_COMPONENTS` thay `BONUS_COMPONENT`), `hrms/vn_payroll/salary_slip_hook.py` (`hr_entered_amount(doc) -> float` thay `_bonus_amount`), `hrms/payroll/report/mvl_salary_register/mvl_salary_register.py`, 3 file test tương ứng
**Estimated scope:** M

#### Task 4: Thưởng KPI, Hỗ trợ điện thoại, Hỗ trợ xăng xe

**Description:** Tạo 3 component Earning chịu thuế, cộng net (`is_tax_applicable=1`, `do_not_include_in_total=0`).
Thêm vào cấu trúc Chính thức + Thử việc, vào `REAL_EARNINGS`, `HR_ENTERED_COMPONENTS`, và map TK 6421.
Điện thoại / xăng xe nhập bằng Additional Salary định kỳ; KPI bằng Additional Salary từng kỳ. Báo cáo thêm 3 cột.

**Acceptance criteria:**

- [ ] Dòng 1 mẫu (F = G = 30tr, 2 NPT, ăn 1tr, điện thoại 500k + xăng 2tr định kỳ, Lễ/Tết 1tr): K = 34.500.000, Q = 294.737, U = 36.944.737 (chưa tính KPCĐ).
- [ ] Dòng 3 mẫu (KPI 500k): K = 12.130.000, U = 12.550.000.
- [ ] `make_accrual_jv_entry` của Payroll Entry chạy được với 3 component mới (không lỗi "Please set account").

**Verification:**

- [ ] `run_test.sh hrms.vn_payroll.tests.test_salary_slip_mvl` → `test_template_row1_allowances_via_recurring_additional_salary`, `test_template_row3_kpi` xanh.
- [ ] `run_test.sh hrms.vn_payroll.tests.test_setup_mvl` → `test_accounting_components_mapped_to_gl_account` (mở rộng) xanh.
- [ ] Báo cáo: cột `phone`, `fuel`, `kpi_bonus` đúng vị trí, có tổng.

**Dependencies:** Task 3
**Files likely touched:** `hrms/vn_payroll/setup_mvl.py`, `hrms/payroll/report/mvl_salary_register/mvl_salary_register.py`, `hrms/vn_payroll/tests/test_salary_slip_mvl.py`, `hrms/vn_payroll/tests/test_setup_mvl.py`
**Estimated scope:** M

### Checkpoint B: Sau Task 3–4

- [ ] Cả `hrms.vn_payroll.tests` + 2 module test của report: không đỏ mới, `HARNESS_NO_LEAK`.
- [ ] HR/kế toán duyệt D2 + D5 và mapping TK 6421 cho 3 component mới.

### Phase 3: KPCĐ

#### Task 5: KPCĐ trên phiếu Chính thức

**Description:** `MVL Payroll Settings.union_fee_rate` (Float, mặc định 0,02). Engine thêm `MVLConfig.union_fee_rate`
và `MVLResult.X = ROUND(G × rate)`, chỉ cho `INSURED_TYPES`. Component `KPCĐ - Công ty` (Deduction,
`do_not_include_in_total=1`) trong cấu trúc Chính thức; gương chi phí = Q + S + R + X.

**Acceptance criteria:**

- [ ] Dòng 1 / 2 / 5 mẫu: X = 600.000 / 200.000 / 160.000; net và thuế không đổi so với Task 4.
- [ ] Thử việc / Khoán: X = 0. Settings đặt 0 → X = 0, và `ensure_settings` không ghi đè số 0 đó.
- [ ] `ensure_settings` chỉ seed 0,02 khi `tabSingles` chưa có dòng `union_fee_rate`.

**Verification:**

- [ ] `run_test.sh hrms.vn_payroll.tests.test_mvl` + `test_settings` + `test_salary_slip_mvl` xanh.
- [ ] Nạp schema trên dev bằng `frappe.reload_doc("hr", "doctype", "mvl_payroll_settings")`. Single không có bảng riêng nên đây là DML.

**Dependencies:** Task 1
**Files likely touched:** `hrms/hr/doctype/mvl_payroll_settings/mvl_payroll_settings.json`, `hrms/vn_payroll/settings.py`, `hrms/vn_payroll/mvl.py`, `hrms/vn_payroll/setup_mvl.py`, `hrms/vn_payroll/salary_slip_hook.py` (+ test)
**Estimated scope:** M

#### Task 6: KPCĐ vào báo cáo và bút toán

**Description:** Map `KPCĐ - Công ty` → TK 3382 (đã có trên site: `3382 - Kinh phí công đoàn - M`), cho
nó vào JV (`do_not_include_in_accounts=0`). Báo cáo thêm cột `union_fee` "KPCĐ" sau BH NLĐ.

**Acceptance criteria:**

- [ ] Bút toán accrual của một phiếu Chính thức: Có 3382 = X, Nợ 6421 tăng đúng X, JV cân.
- [ ] Báo cáo có cột KPCĐ có tổng; phiếu không phải Chính thức ra 0.

**Verification:**

- [ ] `run_test.sh hrms.vn_payroll.tests.test_setup_mvl` (mapping + `test_accounting_excludes_display_components_from_jv`) xanh.
- [ ] `run_test.sh hrms.payroll.report.mvl_salary_register.test_mvl_salary_register` xanh.

**Dependencies:** Task 5
**Files likely touched:** `hrms/vn_payroll/setup_mvl.py`, `hrms/payroll/report/mvl_salary_register/mvl_salary_register.py` (+ 2 test)
**Estimated scope:** S

### Checkpoint C: Sau Task 5–6

- [ ] Bất biến lặp lại trên 6 phiếu T7/2026: net + thuế y như Checkpoint A; chỉ gương chi phí của phiếu Chính thức tăng đúng 2% × G.
- [ ] Kế toán duyệt D3 (KPCĐ 3382).

### Phase 4: Đầu ra theo mẫu + nghiệm thu

#### Task 7: Báo cáo và file Excel theo bố cục mẫu A–Z

**Description:** Nhãn cột báo cáo copy nguyên văn hàng 8 của mẫu, giữ fieldname cũ (thứ tự đầy đủ ở dưới).
Excel: tiêu đề "BẢNG LƯƠNG", và ở dòng `HEADER_ROW - 1` ghi "Số công làm việc chuẩn:" tại cột Hệ số
lương + số công tại cột `worked_days`. Khi cột STT thay Mã NV thì vị trí ra đúng E7 / H7 như mẫu. Số
công lấy từ key `standard_days` (= `total_working_days`) trên mỗi dòng báo cáo; key này không phải cột.

```
Mã NV · Họ tên · Loại Hợp đồng · Loại Hợp đồng (Status) · Hệ số lương · Lương tháng · Lương đóng BHXH ·
Số công làm việc · Lương thực tế · Phụ cấp ăn trưa · Hỗ trợ điện thoại · Hỗ trợ xăng xe, đi lại · Thưởng KPI ·
Thưởng (Lễ/Tết) · Lương thực lĩnh chưa trừ thuế TNCN, BHXH · Giảm trừ bản thân · Số người phụ thuộc ·
Tổng các khoản giảm trừ · Thu nhập làm căn cứ quy đổi · Thu nhập tính thuế · Thuế TNCN/PIT ·
Bảo hiểm công ty trả · Bảo hiểm NLĐ trả · KPCĐ · Thực lĩnh sau khi trừ TNCN, BHXH · Thu nhập chịu thuế
```

**Acceptance criteria:**

- [ ] Danh sách nhãn báo cáo == danh sách trên.
- [ ] File Excel: ô A5 "BẢNG LƯƠNG", H7 = 22 cho kỳ 09/2026; dòng TỔNG CỘNG có cả cột Thưởng (Lễ/Tết) (mẫu gốc thiếu `N15`).
- [ ] Kỳ không có phiếu vẫn ra tờ ký được, không ghi dòng công chuẩn.

**Verification:**

- [ ] `run_test.sh hrms.payroll.report.mvl_salary_register.test_mvl_salary_register` → `test_columns_follow_template_09_2026` xanh.
- [ ] `run_test.sh hrms.payroll.report.mvl_salary_register.test_salary_xlsx` → `test_title_is_bang_luong`, `test_standard_days_sits_above_worked_days_column` xanh.
- [ ] Mở file xuất bằng LibreOffice, so mắt với mẫu.

**Dependencies:** Task 4, Task 6
**Files likely touched:** `hrms/payroll/report/mvl_salary_register/mvl_salary_register.py`, `hrms/vn_payroll/salary_xlsx.py`, 2 file test cạnh report
**Estimated scope:** M

#### Task 8: Phiếu in "Phiếu lương MVL" hiện đủ khoản

**Description:** Html của print format đang liệt kê component cứng. Thêm điện thoại, xăng xe, KPI,
Lễ/Tết (sau Phụ cấp ăn trưa) và KPCĐ (cạnh BHXH công ty); dòng = 0 thì ẩn theo cách đang làm.

**Acceptance criteria:**

- [ ] Mọi tên trong `REAL_EARNINGS` và `KPCĐ - Công ty` có trong html.
- [ ] In phiếu dòng 1 mẫu: thấy đủ 4 khoản thu nhập + KPCĐ, Thực lĩnh 34.500.000.

**Verification:**

- [ ] `run_test.sh hrms.vn_payroll.tests.test_packaging` → `test_print_format_lists_every_paid_component` xanh.
- [ ] `frappe.get_print("Salary Slip", <phiếu harness>, "Phiếu lương MVL")` ra `$SCRATCH/slip.html`, xem bằng trình duyệt.

**Dependencies:** Task 4, Task 5
**Files likely touched:** `hrms/hr/print_format/phieu_luong_mvl/phieu_luong_mvl.json`, `hrms/vn_payroll/tests/test_packaging.py`
**Estimated scope:** S

#### Task 9: Nghiệm thu E2E 6 dòng mẫu + cập nhật spec

**Description:** Script ở scratchpad, chạy trong rollback. Tạo 6 NV + SSA + Additional Salary đúng 6 dòng
mẫu, Payroll Entry kỳ 09/2026 → tạo phiếu → submit → `make_accrual_jv_entry` → `build_workbook`. Rồi ghi
D1–D5 vào spec và bảng tra nhanh §6 của tài liệu công thức.

**Acceptance criteria:**

- [ ] Mỗi phiếu khớp mẫu cột I…Z (≤ 1đ): dòng 1 net 34.500.000 / thuế 294.737 / KPCĐ 600.000 / U 36.944.737; dòng 2 U 12.050.000; dòng 3 U 12.550.000; dòng 4 U 10.500.000; dòng 5 U 11.840.000; dòng 6 U 5.500.000.
- [ ] Bút toán cân: Nợ 6421 = Σ(K + Q + S + R + X), Có 3335 = ΣQ, Có 3383 = Σ(S + R), Có 3382 = ΣX, Có 334 = ΣK.
- [ ] `docs/spec/vn-payroll-mvl.md` có mục "Mẫu 09/2026" + D1–D5; `docs/Cong_thuc_tinh_luong_MVL.md` §6 có cột phụ cấp / KPCĐ.

**Verification:**

- [ ] Script in `E2E_OK` + `HARNESS_NO_LEAK`. (Gotcha: Payroll Entry cần set tay `payroll_payable_account` + `cost_center`.)
- [ ] Toàn bộ `hrms.vn_payroll.tests` + 2 module report + `hrms.tests.test_payroll_gate`: không đỏ mới so với mốc.

**Dependencies:** Task 1–8
**Files likely touched:** `docs/spec/vn-payroll-mvl.md`, `docs/Cong_thuc_tinh_luong_MVL.md` (script E2E ở `$SCRATCH`, không vào repo)
**Estimated scope:** M

### Checkpoint: Hoàn tất

- [ ] Mọi acceptance criteria đạt; ruff sạch; báo cáo danh sách file đổi (không commit).
- [ ] Người duyệt xem lại toàn bộ thay đổi trước khi triển khai.

### Triển khai lên `miyano` (ask-first, không nằm trong lượt tự động)

1. Ký duyệt D1–D5 + TK GL (6421 cho 3 khoản mới, 3382 cho KPCĐ).
2. `bench --site miyano migrate`: field settings, component, cấu trúc, TK, phiếu in.
3. User restart app (supervisor; Claude không restart được).
4. HR tạo Additional Salary định kỳ (điện thoại / xăng xe) cho người có phụ cấp; KPI và Lễ/Tết mỗi kỳ.

## Risks and Mitigations

| Risk                                                                                                            | Impact | Mitigation                                                                                              |
| --------------------------------------------------------------------------------------------------------------- | ------ | ------------------------------------------------------------------------------------------------------- |
| `miyano` là site thật; test rò dữ liệu                                                                   | High   | Chỉ harness rollback + `HARNESS_NO_LEAK`; không DDL trong harness (không thêm custom field SSA)   |
| Component mới thiếu TK → Payroll Entry không dựng được bút toán                                       | High   | Map TK ngay trong Task 4 / 6; Task 9 chạy `make_accrual_jv_entry` thật                              |
| Đổi engine làm lệch phiếu hiện có                                                                        | High   | Bất biến 6 phiếu T7/2026 ở Checkpoint A và C                                                       |
| Hai Additional Salary cùng component, cùng kỳ, đều `overwrite_salary_structure_amount=1` → Frappe chặn | Med    | Ghi vào hướng dẫn HR; test hai row ở Task 3 dùng một Additional Salary + một row gõ tay        |
| 9 test đỏ có sẵn trong `test_salary_slip_mvl` che hồi quy                                                | Med    | Ghi mốc trước Task 1, so danh sách tên test chứ không so số lượng                             |
| HR tick "Đăng ký giảm trừ" cho part time HĐ dưới 3 tháng → thuế thấp hơn mức khấu trừ 10%       | Med    | Ghi rõ trong hướng dẫn HR: chỉ tick khi HĐLĐ từ 3 tháng và NV đã nộp đăng ký giảm trừ |
| Phiên khác chạy `run-tests` trên miyano gây deadlock/nhiễu                                              | Low    | Chạy lại; không chạy hai harness cùng lúc                                                         |

## Open Questions (cần HR/kế toán chốt)

- ~~**D1:** dòng 6 là loại gì~~ → **Đã chốt 2026-10-30:** dòng 6 là Bán thời gian; thuế part time theo cờ đăng ký giảm trừ (bảng ở Architecture Decisions).
- **D2:** Điện thoại và xăng xe **chịu thuế**, mức cố định tháng, không chia theo công (theo mẫu)?
- **D3:** KPCĐ = 2% × G, chỉ Chính thức, công ty chịu, Nợ 6421 / Có 3382?
- **D4:** Tiền ăn trưa nằm trong thực lĩnh (Y = O như mẫu); phần "Nộp quỹ canteen" không đưa vào hệ thống?
- **D5:** Cả 4 khoản (Lễ/Tết, KPI, điện thoại, xăng xe) nhập bằng Additional Salary, thay vì ô nhập trên SSA?

**Ngoài phạm vi:** trần lương đóng BH (20 × lương cơ sở / 20 × lương tối thiểu vùng), tách BH sang
3383 / 3384 / 3386, lương GROSS, quỹ canteen, đóng BH theo tháng khi chuyển chính thức giữa kỳ.
