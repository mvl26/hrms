# Plan: Định mức phép năm VN (Đợt B) + trường định danh Employee (Đợt E)

> Specs: `spec/leave-entitlement-vn.md` + `spec/employee-vn-identity-fields.md` (scope approved
> 2026-07-16). Branch: `feat/skip-attendance-diag`. Test qua **rollback harness** console
> (KHÔNG `bench run-tests` trên `miyano`). Mỗi task: RED → GREEN → regression → commit riêng.
> Deploy prod KHÔNG thuộc plan này (gộp vào gate Đợt A — `tasks/plan-prod-deploy.md`).

## Tasks (theo thứ tự phụ thuộc)

- [x] **T1: Bật earned leave cho "Nghỉ phép năm" (fixture)** *(dev-site migrate = bước deploy user tự chạy — permission gate chặn tự động, đúng ask-first)*
  - Acceptance: `leave_type.json` — Nghỉ phép năm có `is_earned_leave=1`,
    `earned_leave_frequency="Monthly"`, `rounding="0.5"`, `allocate_on_day="Last Day"`;
    7 type còn lại không đổi; sau `bench --site miyano migrate` bản ghi dev phản ánh flags mới.
  - Verify: test mới `test_annual_leave_is_earned_leave` (đọc fixture JSON + DB record) xanh qua
    harness; test sync fixtures↔filter hiện có vẫn xanh.
  - Files: `hrms/fixtures/leave_type.json`, `hrms/tests/test_setup_vn_leave.py` (mới).
  - **Lưu ý gate:** sửa Leave Type đang có = ask-first theo CLAUDE.md → được duyệt cho dev tại
    checkpoint plan này; prod ký riêng ở Đợt A/T2.

- [x] **T2: `hrms/setup_vn_leave.py` — `entitlement_for` + `create_leave_period`**
  - Acceptance: `entitlement_for`: <5 năm→12, đủ 5→13, đủ 10→14 (mốc `date_of_joining`, tính tại
    01/01 của năm); `create_leave_period(year, company)` tạo "VN {company} {year}" 01/01→31/12
    `is_active=1`, idempotent (chạy 2 lần → 1 bản ghi).
  - Verify: unit tests qua harness (nhân viên test DOJ giả lập các bậc thâm niên).
  - Files: `hrms/setup_vn_leave.py` (mới), `hrms/tests/test_setup_vn_leave.py`.

- [ ] **T3: `assign_annual_leave(year, company, employees=None, dry_run=False)`**
  - Acceptance: với nhân viên active — ensure Leave Policy "VN Phép năm {n} ngày" (submit) đúng bậc;
    tạo + submit Leave Policy Assignment (`assignment_based_on="Leave Period"`) + grant → Leave
    Allocation ban đầu = số phép các tháng đã qua (pin `frappe.flags.current_date`); đã có LPA cho
    kỳ đó → skip; trả dict báo cáo per-employee; `dry_run=True` không ghi gì.
  - Verify: harness tests — bậc 12 + 13 cùng lúc; idempotent (lần 2 = 0 created); thêm nhân viên
    mới rồi chạy lại → chỉ thêm 1.
  - Files: `hrms/setup_vn_leave.py`, `hrms/tests/test_setup_vn_leave.py`.

- [ ] **T4: Accrual tháng + cap + không carry-forward**
  - Acceptance: gọi `allocate_earned_leaves()` với `frappe.flags.current_date` = cuối tháng kế →
    allocation +1.0 (bậc 12); tổng không vượt `annual_allocation`; allocation `to_date=31/12`,
    `carry_forward=0`.
  - Verify: harness tests (pin date, gọi scheduler function trực tiếp — pattern upstream).
  - Files: `hrms/tests/test_setup_vn_leave.py`.

- [ ] **T5: Unlock flows — Leave Application + Compensatory Leave Request + payroll gate**
  - Acceptance: (a) nhân viên có allocation nộp + submit Leave Application "Nghỉ phép năm" 1 ngày
    → OK, Attendance sinh mã P (regression bridge); (b) dựng Holiday List test
    (`create_vn_holiday_list`) + Attendance Present ngày lễ + Leave Period → Compensatory Leave
    Request submit OK, allocation "Nghỉ bù" +1; (c) chạy lại
    `test_attendance_code_payroll_invariance` — xanh nguyên vẹn.
  - Verify: harness — 2 test integration mới + suite invariance cũ.
  - Files: `hrms/tests/test_setup_vn_leave.py`.

- [ ] **T6 (Đợt E): 2 custom field định danh trên Employee**
  - Acceptance: `custom_citizen_id` (Số CCCD) + `custom_social_insurance_no` (Số sổ BHXH), Data,
    trong Personal tab sau `marital_status`; fixtures JSON + hooks filter sync; dịch
    "Tax ID"→"MST cá nhân" trong `vi.csv`; sau migrate field hiện trên form Employee.
  - Verify: harness test — 2 Custom Field tồn tại đúng thuộc tính; test sync filter mở rộng xanh;
    set/get giá trị trên Employee test.
  - Files: `hrms/fixtures/custom_field.json`, `hrms/hooks.py`, `hrms/translations/vi.csv`,
    `hrms/tests/test_setup_vn_defaults.py` (hoặc test fixture tương ứng).

- [ ] **T7: Docs + tick plan**
  - Acceptance: tick checkbox plan này; cập nhật `docs/audit-roadmap-2026-07-16.md` (Đợt B/E → BUILT
    on dev, chờ deploy Đợt A); ghi chú lệnh vận hành năm mới vào plan prod-deploy (sau T3 thêm bước
    `assign_annual_leave` prod).
  - Verify: đọc lại; commit docs riêng.
  - Files: `tasks/plan-leave-entitlement-and-identity.md`, `docs/audit-roadmap-2026-07-16.md`,
    `tasks/plan-prod-deploy.md`.

## Rủi ro & xử lý

- **Sửa Leave Type live khi migrate dev**: chỉ flags earned-leave; không đụng `is_lwp`/carry-forward
  → payroll-neutral (gate T5c chứng minh). Prod: gộp sign-off Đợt A.
- **Scheduler dev**: không phụ thuộc — test gọi thẳng `allocate_earned_leaves()`; vận hành thật dựa
  `daily_long` sẵn có.
- **Leave Policy trùng tên giữa công ty**: tên policy chứa số ngày, không chứa company — chấp nhận
  (policy dùng chung được giữa company; assignment mới gắn employee/company).
