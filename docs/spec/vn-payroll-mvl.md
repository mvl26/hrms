# Spec: Tính lương MVL (Miyano Việt Nam) — NET gross-up theo chấm công

> Status: **APPROVED (SPECIFY)** — 2026-07-24. Nguồn công thức: `docs/Cong_thuc_tinh_luong_MVL.md`
> (trích nguyên trạng từ `3. MVL_Bang luong 06.2026_Lan final.xlsx`). Nối tiếp bộ chấm công VN đã ship.

## Objective

Sinh Salary Slip đúng công thức lương Miyano: trả **NET** (công ty gross-up nộp thay thuế TNCN + BH
phần NLĐ), số ngày công lấy từ hệ thống chấm công đã xây. Cấu hình chuẩn **đóng gói vào app** (tự có
khi cài), **sửa được trên giao diện**. Số liệu riêng từng nhân viên nhập trên UI.

**Kết nối chấm công (thành quả các phần trước):**
- `H7` (công chuẩn tháng) = `total_working_days` của Salary Slip (suy từ Holiday List: T6/2026 = 22, khớp `$H$7=22`).
- `H` (công thực tế) = `payment_days` (đã trừ Không lương, Vắng, ngày ngoài biên chế).

## Locked decisions (2026-07-24)

1. **Engine Python thuần** (`hrms/vn_payroll/mvl.py`) hiện thực Bước 1–9 + biểu thuế + gross-up +
   phân nhánh loại nhân sự. KHÔNG dùng formula component (native chỉ cho int/float/round/ceil/floor).
2. **Cấu hình mỗi NV = custom fields trên Salary Structure Assignment** (native, versioned theo
   `from_date`, Payroll Entry chạy được). Không tạo doctype hồ sơ lương riêng.
3. **Tham số chuẩn = Single DocType `MVL Payroll Settings`** (sửa trên UI): giảm trừ, ăn trưa, tỷ lệ
   BH, biểu thuế, biểu gross-up. Đóng gói bằng `ensure_defaults` (self-heal mỗi migrate).
4. **Payslip NET:** `net_pay = thực lĩnh T = K = I + J`. Q/S/R là **statistical component** (chi phí
   công ty nộp thay, hiện trên slip để kê khai, KHÔNG trừ vào tiền NV nhận). Loại GROSS thì Q+S trừ thật.
5. **Đóng gói:** Salary Components + Salary Structure "MVL Việt Nam" + custom fields + settings mặc
   định qua fixtures/`ensure_defaults`. Sửa được trên UI, re-sync mỗi migrate (không ghi đè giá trị NV).

## Data model

### `MVL Payroll Settings` (Single) — tham số chuẩn, sửa trên UI
- `personal_deduction` = 15.500.000 (giảm trừ bản thân/tháng)
- `dependent_deduction` = 6.200.000 (mỗi người phụ thuộc/tháng)
- `lunch_rate_per_day` = 35.000
- `insurance_company_rate` = 0.215 · `insurance_employee_rate` = 0.105
- `probation_coefficient` = 0.85 (hệ số lương thử việc)
- `tax_brackets` (child table: threshold, rate, subtract) — 5 bậc lũy tiến
- `grossup_brackets` (child table: threshold, subtract, divisor) — 5 bậc quy đổi NET→gross

### Custom fields trên `Salary Structure Assignment`
- `custom_salary_type` (Select): `Chính thức` | `Thử việc` | `Parttime cư trú` | `Parttime nước ngoài`
  | `Parttime cam kết 08` | `Khoán` | `GROSS`
- `custom_bhxh_salary` (Currency) = G, lương đóng BHXH (trống → không đóng BH)
- `custom_dependents` (Int) = M, số người phụ thuộc
- `custom_register_personal_deduction` (Check) = có đăng ký giảm trừ bản thân (L)
- `custom_lunch_days_override` (Int) = số ngày ăn nếu khác payment_days (trống → = payment_days)
- (`base` của SSA = F, lương ngày công.)

### Salary Components (fixtures)
| Component | Type | Vai trò |
|---|---|---|
| Lương theo công | Earning | I |
| Phụ cấp ăn trưa | Earning | J (miễn thuế) |
| Thuế TNCN (nộp thay) | Deduction, statistical (NET) | Q |
| BHXH - NLĐ (nộp thay) | Deduction, statistical (NET) | S |
| BHXH - Công ty | statistical | R |

## Engine — `hrms/vn_payroll/mvl.py`

Hàm thuần, không đụng DB (nhận input là dict/dataclass), để test theo đúng ví dụ số trong doc:

```
compute_mvl(salary_type, F, E, G, dependents, register_personal_deduction,
            lunch_days, standard_days H7, worked_days H, settings) -> MVLResult
```

Trả `MVLResult(I, J, K, N, O, P, Q, R, S, T, U)`.

**Bước lõi (mục 2 của doc):**
- I = ROUND(F × E / H7 × H, 0) — với `Khoán`: I = F (không nhân công).
- J = lunch_days × 35.000 (loại parttime/khoán/GROSS: J = 0).
- K = I + J
- N = (register ? 15.500.000 : 0) + 6.200.000 × dependents
- O = MAX(K − N − J, 0)
- **P (quy đổi NET→gross)** theo loại:
  - NET fulltime/thử việc: biểu 5 bậc grossup trên O (Bước 6).
  - Parttime cư trú / Khoán: P = ROUND(O / 0.9, 0).
  - Parttime nước ngoài: P = ROUND(O / 0.8, 0).
  - Parttime cam kết 08: P = 0.
- **Q (thuế):**
  - NET fulltime/thử việc: biểu lũy tiến 5 bậc trên P (Bước 7).
  - Parttime cư trú / Khoán: Q = ROUND(P × 10%, 0).
  - Parttime nước ngoài: Q = ROUND(P × 20%, 0).
  - Cam kết 08: Q = 0.
- R = ROUND(G × 21.5%, 0); S = ROUND(G × 10.5%, 0) (G trống → 0).
- T (thực lĩnh) = K; U (kê khai) = K + Q + S − J.
- **GROSS** (loại `GROSS`): bỏ gross-up, thuế tính thẳng trên (thu nhập − giảm trừ − BH NLĐ);
  T = GROSS − Q − S. (Ưu tiên thấp — Miyano hiện trả toàn NET.)

**Hệ số E** suy từ `custom_salary_type`: Thử việc → `probation_coefficient` (0.85), còn lại → 1.

## Integration — Salary Slip

`Salary Slip.validate` (doc_event hoặc override): nếu salary structure = "MVL Việt Nam":
1. Đọc SSA custom fields + `base` (F).
2. Lấy H7 = total_working_days, H = payment_days (Frappe đã tính từ Attendance).
3. Gọi `compute_mvl(...)`.
4. Gán amount cho từng component (I, J, Q, S, R).
   - **NET:** `gross_pay = net_pay = K` (= I + J). Q/S/R là statistical → hiện trên slip nhưng KHÔNG
     trừ vào net (đúng: NV nhận đủ K). Thu nhập kê khai U lưu ở custom field, không phải `gross_pay`.
   - **GROSS:** `gross_pay = tổng thu nhập`, Q+S là deduction thật, `net_pay = gross − Q − S = T`.
5. Lưu U (kê khai), R, chi tiết vào custom fields slip để in phiếu lương + kê khai.

Không đụng logic `get_working_days_details` (payment_days) đã có — chỉ tiêu thụ kết quả.

## Testing

- **Engine (bắt buộc, oracle = doc):**
  - Tạ Trường Xuân (chính thức): F=25tr, H=22/22, ăn 21 ngày, 1 phụ thuộc → I=25tr, K=25.735tr,
    O=3.3tr, Q=173.684, R=5.375tr, S=2.625tr, T=25.735tr.
  - Nguyễn Yến Chi (thử việc E=0.85): F=13.5tr, H=11.5/22 → I=5.998.295, T=6.313.295, thuế=0.
  - Parttime cư trú: O=10tr → P=11.111.111, Q=1.111.111.
  - Parttime nước ngoài: O=3tr → P=3.750.000, Q=750.000.
  - Cam kết 08: Q=0. Khoán 30tr NET → P=33.333.333, Q=3.333.333.
  - Biểu thuế/gross-up từng bậc: ca biên (O đúng ngưỡng 9.5tr/27.5tr…, P đúng 10tr/30tr…).
- **Integration:** slip cho 1 NV chính thức → component + net_pay khớp engine; đổi payment_days → I đổi đúng.
- **Fixtures/settings:** `ensure_defaults` tạo đủ component + settings, idempotent; sửa UI không bị migrate ghi đè.
- Chạy qua **harness rollback** (không `run-tests` trên miyano). Kiểm rò rỉ sau mỗi lượt.

## Packaging & deploy

- Custom fields + Salary Components + Salary Structure + `MVL Payroll Settings` mặc định: export qua
  `fixtures` (đồng bộ filter trong `hooks.py`) + `ensure_defaults` self-heal (không ghi đè giá trị đã sửa).
- Deploy chuẩn = `bench migrate` (re-sync fixtures = cổng ask-first). Dev cài bằng `reload_doc` + seed.

## Out of scope (đợt này)

- Bảng kê thuế/BHXH nộp cơ quan, hạch toán GL chi tiết (SUMIF theo TK 6421/6411) — doc mục 4, để sau.
- Payroll Entry hàng loạt tự động — build slip đơn trước, hàng loạt sau khi engine chuẩn.
- Quyết toán thuế năm, giảm trừ luỹ kế nhiều kỳ.
- Nhập số liệu 6 NV thật = việc của HR trên UI (spec chỉ dựng hệ thống + test theo doc).
