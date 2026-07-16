# Plan Đợt A — Deploy prod VN timekeeping stack (runbook có cổng sign-off)

> Status: **READY — chờ sign-off từng bước.** Theo `docs/audit-roadmap-2026-07-16.md` (ưu tiên
> A → B → C đã chốt). Đợt này **không có code mới** — chỉ đưa những gì đã build + test xanh trên
> dev vào site có dữ liệu thật. Mọi bước đánh dấu **[GATE]** là ask-first: dừng, xin sign-off,
> rồi mới chạy. "Prod" = instance mang dữ liệu HR/lương thật (bản dev `miyano` trên bench này
> gần trống — 10 nhân viên, 0 salary slip; xem `spec/vn-holiday-and-symbol-standardization.md:73-75`).

## Nguyên tắc xuyên suốt

- **Payroll-invariance:** trước và sau mỗi bước đụng dữ liệu, chụp baseline
  `payment_days / absent_days / leave_without_pay` của toàn bộ Salary Slip đã submit — phải
  **byte-identical** (trừ bước nào có sign-off nói khác).
- Mỗi bước có backup DB riêng (`bench --site <prod> backup`) trước khi chạy.
- Rollback: bước 2 (rename) **không git-revert được** trên dữ liệu thật → chỉ khôi phục bằng backup;
  các bước còn lại revert/xóa được.

## Tasks

- [ ] **T0 (dev, không gate): Verify JS geofence trên browser** — mục treo cuối của
  `tasks/plan-geofence-and-defaults.md`.
  - Acceptance: (a) Shift Location: click bản đồ set lat/long + vòng tròn bán kính vẽ lại theo
    `checkin_radius`; (b) Employee Checkin: overlay vòng tròn geofence + điểm check-in, read-only.
  - Verify: thao tác trực tiếp trên Desk dev (`bench start` + Chrome), theo steps trong plan geofence.
  - Files: không đổi code (chỉ verify); nếu lỗi → fix riêng.

- [ ] **T1 [GATE ①]: Chụp baseline payroll trên prod**
  - Acceptance: file CSV/JSON lưu `name, employee, start_date, payment_days, absent_days,
    leave_without_pay, gross_pay, net_pay` của mọi Salary Slip docstatus=1; đếm khớp tổng số slip.
  - Verify: `bench --site <prod> execute` query đếm + checksum file; lưu kèm backup DB.
  - Files: script one-off (scratch, không commit vào app).

- [ ] **T2 [GATE ②]: Merge & migrate prod** — một lần `bench migrate` chạy trọn: patch rename
  English (Monthly Attendance Sheet / Business Trip / custom_work_credit…), sync fixtures
  (8 Leave Type — gồm "Nghỉ phép năm" earned-leave, 14 Attendance Code, 12 custom field —
  gồm 2 field định danh Employee), `backfill_attendance_codes` (display-only),
  `ensure_defaults` (workflow Business Trip + role COO).
  - Prereq (cần approval riêng): merge `feat/skip-attendance-diag` → `version-15`, deploy code
    lên prod.
  - Acceptance: migrate sạch không traceback; doctype cũ đã rename còn nguyên số bản ghi;
    fixtures đủ đếm (8/14/10); backfill chỉ điền `custom_*_code`/`custom_work_credit`.
  - Verify: chạy lại query baseline T1 → **byte-identical**; mở 1 Bảng Công Tháng + 1 Business
    Trip cũ trên Desk xem form/print còn đúng; `bench build --app hrms` nếu asset đổi.
  - Files: không (chạy vận hành).

- [ ] **T3 [GATE ③]: Tạo Holiday List VN trên prod**
  - Chốt trước khi chạy: **weekly-off = CN hay T7+CN** (câu hỏi mở #2 của roadmap).
  - Acceptance: `create_vn_holiday_list(year=2026, company='Miyano', weekly_off_days=…)` tạo list
    ~52 (CN) hoặc ~104 (T7+CN) dòng weekly-off + 5 lễ dương lịch; HR nhập tay Tết Âm lịch (5 ngày)
    + Giỗ Tổ; set làm default holiday list của Company (và Shift Type nếu cần).
  - Verify: idempotent (chạy lại không nhân đôi); nhân viên không set `holiday_list` resolve về
    Company default; Monthly Attendance Report tô "-" (CN) / "NL" (lễ) đúng tháng hiện tại.
  - Files: không (helper đã có: `hrms/setup_vn_holiday.py`).

- [ ] **T3b [GATE ③b]: Cấp định mức phép năm trên prod** *(mới — Đợt B đã build dev 2026-07-16)*
  - Prereq: T2 (fixture Leave Type earned-leave + custom fields đã vào prod qua migrate), T3 (Holiday
    List — cần cho nghỉ bù).
  - Acceptance: `bench --site <prod> execute hrms.setup_vn_leave.assign_annual_leave --kwargs
    "{'year': 2026, 'company': 'Miyano'}"` — chạy `dry_run=True` trước, HR duyệt danh sách bậc
    (12/13/14 ngày theo thâm niên), rồi chạy thật; mọi nhân viên active có allocation.
  - **Lưu ý vận hành (review 2026-07-16):** (a) helper tự chặn nếu chạy TRƯỚC migrate (guard
    earned-leave); (b) **tránh chạy vào ngày cuối tháng** — LPA cấp bù tháng hiện tại + scheduler
    cùng ngày có thể cộng trùng 1 ngày (tự cân bằng cuối năm nhờ cap, nhưng số dư tạm sai);
    (c) allocation/assignment có sẵn trên prod → helper skip có lý do (`skipped_allocation_exists`,
    `draft_exists`…) — đọc report, KHÔNG phải lỗi; (d) số dư bậc thâm niên sẽ lẻ (1.083/tháng) —
    đúng Điều 114, không làm tròn; (e) bậc chốt tại 01/01 kỳ cấp (đủ 5 năm giữa năm → năm sau
    mới lên bậc — đơn giản hóa có chủ đích, spec ghi rõ).
  - Verify: report dict trả về 100% created/skipped, 0 error; vài nhân viên spot-check số dư trên
    Desk; scheduler daily_long sẽ cộng dồn các tháng tiếp theo (không cần cấu hình thêm).
  - Vận hành hằng năm: chạy lại lệnh cho năm mới (idempotent; nhân viên mới vào giữa năm → chạy lại).

- [ ] **T4 [GATE ④ — cứng]: Bật classifier sáng/chiều trên MỘT ca prod + chạy song song 1 tháng**
  - Acceptance: `custom_split_half_day = 1` + cấu hình trưa/ngưỡng/grace trên đúng 1 Shift Type;
    sau 1 tháng: báo cáo delta payroll (payment_days/absent_days/LWP per slip) so với baseline
    hành vi threshold cũ = **0 khác biệt** do classifier gây ra.
  - Verify: script so sánh tháng song song; chỉ mở rộng sang các ca khác sau sign-off tiếp.
  - Files: không.

- [ ] **T5 (quyết định vận hành): bật `allow_geolocation_tracking`?** — nếu muốn chặn check-in
  ngoài geofence (server-side hard block). Cân nhắc giới hạn: chỉ check location của Shift
  Assignment đầu tiên; PWA không có preview vùng cho nhân viên.

## Sau Đợt A

→ **Đợt B**: brainstorm + spec WS3 "Cấp phép năm tự động" (12 ngày + thâm niên Điều 113/114 +
carry-forward — câu hỏi mở #1) — mở khóa Leave Application self-service + Compensatory Leave Request.
→ **Đợt C**: chẩn đoán payroll prod (nghỉ lễ có lương + chốt `payroll_based_on` — rủi ro mã K
không trừ lương trên đường 'Leave').
→ **Đợt E (thu hẹp, song song được)**: custom fields định danh trên Employee (CCCD, số sổ BHXH,
MST cá nhân) — additive, fixtures.
