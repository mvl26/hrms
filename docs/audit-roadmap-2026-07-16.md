# Đánh giá hiện trạng & lộ trình HRMS Miyano — 2026-07-16

> Status: **APPROVED 2026-07-16 (program level).** Kết quả audit toàn diện 5 mảng
> (công, check-in, nghỉ phép, lương, nhân sự) trên branch `feat/skip-attendance-diag`, đối chiếu
> spec/plan trong repo + code thực tế. **Quyết định đã chốt (2026-07-16):**
>
> 1. **Thứ tự ưu tiên: A → B → C.**
> 2. **Phạm vi lương: ERP chỉ quản công + `payment_days`** — thuế TNCN + BHXH tiếp tục tính
>    ngoài hệ thống. → **Đợt D bị loại khỏi lộ trình.** (Đợt C vẫn cần: nghỉ lễ có lương và
>    chốt `payroll_based_on` đều ảnh hưởng trực tiếp `payment_days`.)
> 3. **Nhân sự: chỉ thêm trường định danh** (CCCD, số sổ BHXH, MST cá nhân) — không build
>    doctype HĐLĐ. → **Đợt E thu hẹp**, additive, chạy song song được.
>
> Còn mở: carry-forward phép năm (chốt khi brainstorm spec Đợt B); weekly-off CN hay T7+CN
> (chốt khi tạo Holiday List prod ở Đợt A).

## 1. Kết luận nhanh

| Mảng | Đủ chức năng? | Đúng? | Ghi chú |
|---|---|---|---|
| **Công (chấm công mã VN)** | ✅ Đủ trên dev | ✅ 110–128 test xanh, payroll-invariant | **Chưa deploy prod** (sign-off gate) |
| **Check-in / geofence** | ✅ Gần đủ | ⚠️ 3 giới hạn cần biết (mục 4) | Còn 1 mục verify JS trên browser |
| **Nghỉ phép** | ⚠️ Nửa | Lớp ký hiệu/bridge hoàn chỉnh; **lớp định mức phép trống hoàn toàn** | Nhân viên không có số dư phép → không tự nộp đơn được |
| **Lương** | ❌ Phần VN chưa có | Bất biến lương được bảo vệ tốt, nhưng chưa có logic lương VN nào | Thuế TNCN, BHXH/BHYT/BHTN, lễ có lương: đều chưa |
| **Nhân sự** | ⚠️ Stock | Thiếu trường định danh VN + quản lý HĐLĐ | Onboarding/appraisal/recruitment = stock nguyên bản |

## 2. Hiện trạng chi tiết theo mảng

### 2.1 Công (mã công / bảng công) — HOÀN CHỈNH trên dev

Đã build và test xanh toàn bộ (chuỗi commit tới `79fdf4b`):

- 14 Attendance Code (X, NN, P, 1/2P, Ô, Cô, TS, T, NB, K, 1/2K, V, CT, N) + bridge 2 chiều
  `Attendance.before_validate` (`hrms/hr/doctype/attendance/attendance.py:118-186`), payroll-neutral
  có gate (`test_attendance_code_payroll_invariance.py`, 3 test).
- Bảng Công Tháng (nay là `Monthly Attendance Sheet`) submittable + print VN; báo cáo
  `Monthly Attendance Report` với marker `-` (ngày nghỉ) / `NL` (lễ).
- Phase 4: classifier sáng/chiều tự động, giờ net trừ trưa, gate theo cờ `custom_split_half_day`
  trên Shift Type (5 custom field).
- WS1: helper `hrms/setup_vn_holiday.py::create_vn_holiday_list` (on-demand, idempotent).
- Đổi tên English toàn bộ doctype/field VN-romanized (dev đã migrate sạch, 128 test).
- Working-hours report + dashboard (`hrms/hr/working_hours.py`).
- Skip-attendance recovery on cancel/delete (`attendance.py:199-218, 408-413`) + tool chẩn đoán
  `hrms/skip_attendance_diag.py`.

**Còn thiếu:** toàn bộ bước **deploy prod** (mục 3). PWA chưa hiển thị mã công (chỉ Desk) — nhỏ, tùy chọn.

### 2.2 Check-in / geofence — GẦN ĐỦ

- Enforcement là **chặn cứng server-side** (`employee_checkin.py:93-127`,
  `CheckinRadiusExceededError`) khi HR Settings `allow_geolocation_tracking` bật + Shift Assignment
  có `shift_location` với `checkin_radius > 0`.
- Miyano thêm: endpoint `get_checkin_geofence`, overlay vòng tròn trên Employee Checkin, click-to-set
  trên Shift Location.
- PWA (`CheckInPanel.vue`) có gửi geolocation; bị chặn thì chỉ biết qua error toast — không có
  preview geofence phía client.

**Còn thiếu / giới hạn:** (a) verify JS map trên browser (mục treo duy nhất của plan geofence);
(b) `allow_geolocation_tracking` cố ý để tắt mặc định — muốn enforcement trên site thật phải bật tay;
(c) chỉ check **location của assignment đầu tiên** — nhân viên đa địa điểm chưa phủ hết.

### 2.3 Nghỉ phép — LỚP KÝ HIỆU XONG, LỚP ĐỊNH MỨC TRỐNG

Đã có: 8 Leave Type VN fixtures (`hrms/fixtures/leave_type.json`) bridge đủ với 14 mã công; Leave
Application → Attendance tự sinh mã đúng.

**Trống hoàn toàn (đã hoãn có chủ đích — WS3, spec chưa viết):**

1. **Không có Leave Policy / Leave Policy Assignment / Leave Period / Leave Allocation nào** —
   "Nghỉ phép năm" có `is_earned_leave = 0` nên scheduler cấp phép tháng của upstream là no-op.
2. Hệ quả vận hành: `allow_negative = 0` → nhân viên **không thể tự nộp Leave Application phép năm**
   (số dư 0) qua PWA/Desk; hiện chỉ chạy được nhờ HR nhập mã công trực tiếp (bridge chỉ warn,
   không chặn).
3. **Điều 113/114 BLLĐ**: 12 ngày/năm cộng dồn tháng, +1 ngày/5 năm thâm niên, carry-forward —
   chưa có gì; thâm niên upstream không hỗ trợ (cần custom).
4. **Compensatory Leave Request (nghỉ bù) không submit được**: yêu cầu Leave Period (chưa có) +
   Attendance ngày lễ trên Holiday List thật (chưa tạo trên prod). NB hiện chỉ là ký hiệu chấm công.
5. Điều 115 (cưới 3 ngày, tang 3 ngày…): mã N có, nhưng không có cap/allocation — kiểm soát bằng
   kỷ luật HR.

### 2.4 Lương — PHẦN VN CHƯA CÓ GÌ TRONG CODE

- Fork **không có custom code lương** nào; chỉ có gate test invariance. 2 custom field
  (`so_nguoi_phu_thuoc`, `ma_chinh_sach_bhxh` — baked vào fork erpnext/hrms) **không formula nào đọc**.
- **Chưa có:** thuế TNCN lũy tiến VN + giảm trừ gia cảnh, BHXH/BHYT/BHTN (10.5% NLĐ / 21.5% NSDLĐ),
  lương tối thiểu vùng, `hrms/regional/vietnam` (chỉ có india + UAE).
- **Nghỉ lễ có lương**: hoãn theo quyết định #6 (spec WS1/WS2) với trình tự bắt buộc:
  Holiday List đúng → **chẩn đoán salary slip prod thật** → sửa tối thiểu qua gate + ký duyệt.
  Nút thắt kỹ thuật: `include_holidays_in_total_working_days` là **một cờ chung** cho cả CN lẫn lễ.
- Salary Structure/Slip = dữ liệu site trên prod (dev có 0 bản ghi) — chưa audit được config thật.

### 2.5 Nhân sự — STOCK, THIẾU LỚP VN

- Employee: **không có CCCD, số sổ BHXH, MST cá nhân** (chỉ passport + `tax_id` generic +
  2 field chính sách BHXH). 
- **Không có doctype hợp đồng lao động** (thử việc / xác định / không xác định thời hạn, chuỗi gia
  hạn, phụ lục) — upstream chỉ có `contract_end_date` + Employment Type là field phân loại.
- Onboarding/offboarding, appraisal, recruitment: stock nguyên bản, chưa đụng.
- Business Trip (Công Tác) + workflow COO: hoàn chỉnh.

## 3. Đã build xong nhưng CHƯA deploy prod (tất cả ask-first / sign-off)

Theo thứ tự an toàn đề xuất:

1. **(dev) Verify JS geofence trên browser** — mục treo duy nhất không dính prod.
2. **Prod: migrate đổi tên English** — patch rename đã viết sẵn, replay qua `bench migrate`;
   `rename_doc` trên dữ liệu thật **không git-revert được** → sign-off riêng.
3. **Prod: deploy fixtures** (8 Leave Type, 14 Attendance Code, custom fields) + backfill mã công
   (patch đã có, payroll-proof) + Bảng Công Tháng / Business Trip / print formats.
4. **Prod: tạo Holiday List VN 2026** (`create_vn_holiday_list`) + HR nhập tay Tết/Giỗ Tổ;
   chốt weekly-off (CN hay T7+CN).
5. **Prod: bật `custom_split_half_day` trên 1 ca** + chạy song song 1 tháng + đo delta payroll —
   gate cứng theo plan Phase 4.
6. **Prod: bật `allow_geolocation_tracking`** nếu muốn chặn check-in ngoài vùng (quyết định vận hành).

## 4. Lỗ hổng & rủi ro đáng chú ý (ngoài các gap chức năng)

1. **`payroll_based_on = 'Leave'` (site hiện tại) vs mã K**: đường Leave chỉ đọc Leave Application —
   mã `K`/`1/2K` nhập tay **không kèm đơn** sẽ **không trừ lương** (âm thầm). Gate invariance hiện chỉ
   pin đường `'Attendance'`. → Cần chốt cấu hình chuẩn (đổi sang Attendance? hay bắt buộc đơn nghỉ
   không lương?) trong đợt chẩn đoán payroll.
2. **Nhân viên không có số dư phép** → Leave Application self-service tắc (mục 2.3.2).
3. **Nghỉ bù không có đường cấp bù** (mục 2.3.4).
4. Geofence chỉ check assignment location đầu tiên (mục 2.2c).
5. Docs/memory nói "7 Leave Type / 13 mã" — thực tế là **8 / 14** (mã N thêm 2026-07-14);
   `CLAUDE.md:76` cần cập nhật.

## 5. Lộ trình đề xuất (mỗi đợt = 1 spec riêng theo quy trình)

| Đợt | Nội dung | Giá trị | Rủi ro | Phụ thuộc |
|---|---|---|---|---|
| **A. Deploy prod những gì đã xây** | Mục 3, tuần tự 1→6, mỗi bước sign-off | Đưa toàn bộ 3 tuần công việc vào sử dụng thật | Trung (rename + fixtures trên data thật) | — |
| **B. WS3 — Định mức phép năm** — ✅ **BUILT dev 2026-07-16** (`spec/leave-entitlement-vn.md`, 126 test xanh; carry-forward = KHÔNG) | Leave Period + Leave Policy theo bậc + accrual tháng (`is_earned_leave`) + thâm niên +1/5năm; Compensatory Leave Request đã mở khóa (test E2E) | Nhân viên tự nộp đơn phép, số dư đúng luật | Còn lại: chạy `assign_annual_leave` trên prod (gộp Đợt A) | A (Holiday List cho nghỉ bù) |
| **C. Payroll đợt 1 — chẩn đoán + nghỉ lễ có lương** | Chẩn đoán salary slip prod; chốt `payroll_based_on` (rủi ro #1); sửa tối thiểu để lễ = công hưởng lương qua gate invariance | Lương tháng đúng quyết định #3 (lương cố định ÷ ngày làm việc thực) | **Cao** (đụng số lương) — trình tự đã khóa ở quyết định #6 | A (Holiday List prod) |
| **D. Payroll đợt 2 — lương VN đầy đủ** | Thuế TNCN lũy tiến + giảm trừ (11tr/4.4tr), BHXH/BHYT/BHTN, lương tối thiểu vùng — dạng Salary Component/Income Tax Slab fixtures (ưu tiên config, không fork code) | Tính lương hoàn toàn trong ERP | Cao | C; **cần chốt phạm vi** (hiện BHXH tính ngoài hệ thống) |
| **E. Nhân sự VN (thu hẹp)** — ✅ **BUILT dev 2026-07-16** (`spec/employee-vn-identity-fields.md`) | Custom fields Employee: Số CCCD + Số sổ BHXH; MST = `tax_id` sẵn có (+bản dịch). Không HĐLĐ (đã quyết định loại) | Hồ sơ nhân sự đủ định danh VN | Còn lại: deploy prod (fixtures, gộp Đợt A/T2) | — |

**Thứ tự đã chốt: A → B → C** (+ E thu hẹp chạy song song; D loại bỏ). A là điều kiện của cả B lẫn C
và không cần code mới; B mở khóa self-service ngay; C phải đi sau khi có Holiday List thật trên prod.

## 6. Quyết định đã chốt (2026-07-16) + câu hỏi còn mở

Đã chốt: (1) ưu tiên **A → B → C**; (2) lương **chỉ công + payment_days trong ERP**, thuế/BHXH tính
ngoài → bỏ đợt D; (3) nhân sự **chỉ trường định danh**, không doctype HĐLĐ → đợt E thu hẹp.

Còn mở (không chặn Đợt A):

1. **Carry-forward phép năm (đợt B):** phép không dùng hết có chuyển sang năm sau không, hạn chót
   (VD 31/03)? → chốt khi brainstorm spec B.
2. **Weekly-off (đợt A, bước Holiday List):** Miyano nghỉ CN hay T7+CN? → chốt trước khi chạy
   `create_vn_holiday_list` trên prod.
3. **Geofence enforcement (đợt A, bước cuối):** có bật `allow_geolocation_tracking` trên prod không?

## 7. Housekeeping (nhỏ, làm ngay được)

- Commit việc di chuyển `SPEC.md`/`hrms.png` → `docs/` (đang là deleted + untracked trên working tree).
- Commit `hrms/demo_data.py` + `docs/demo-test-scenarios.md` (demo tháng 9/2026 — đang untracked).
- Cập nhật `CLAUDE.md` 7→8 Leave Type, 13→14 mã công; tick checkbox các plan đã xong
  (3 plan có status DONE nhưng checkbox chưa tick).
