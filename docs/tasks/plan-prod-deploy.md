# Plan Đợt A — Deploy prod VN timekeeping stack (runbook có cổng sign-off)

> Status: **READY — chờ sign-off từng bước.** Theo `docs/audit-roadmap-2026-07-16.md` (ưu tiên
> A → B → C đã chốt). Đợt này **không có code mới** — chỉ đưa những gì đã build + test xanh trên
> dev vào site có dữ liệu thật. Mọi bước đánh dấu **[GATE]** là ask-first: dừng, xin sign-off,
> rồi mới chạy. "Prod" = instance mang dữ liệu HR/lương thật (bản dev `miyano` trên bench này
> gần trống — 10 nhân viên, 0 salary slip; xem `docs/spec/vn-holiday-and-symbol-standardization.md:73-75`).

## Nguyên tắc xuyên suốt

- **Payroll-invariance:** trước và sau mỗi bước đụng dữ liệu, chụp baseline
  `payment_days / absent_days / leave_without_pay` của toàn bộ Salary Slip đã submit — phải
  **byte-identical** (trừ bước nào có sign-off nói khác).
- Mỗi bước có backup DB riêng (`bench --site <prod> backup`) trước khi chạy.
- Rollback: bước 2 (rename) **không git-revert được** trên dữ liệu thật → chỉ khôi phục bằng backup;
  các bước còn lại revert/xóa được.

## Tasks

- [ ] **T0 (dev, không gate): Verify JS geofence trên browser** — mục treo cuối của
  `docs/tasks/plan-geofence-and-defaults.md`. **Chỉ còn phần nhìn/tương tác — anh phải tự làm trên Chrome
  của anh** (Chrome của trợ lý nằm ở máy khác, không nối được tới site này).
  - Acceptance: (a) Shift Location: click bản đồ set lat/long + vòng tròn bán kính vẽ lại theo
    `checkin_radius`; (b) Employee Checkin: overlay vòng tròn geofence + điểm check-in, read-only.
  - **Đã kiểm tĩnh (2026-07-22), loại trừ hết các lỗi kiểm được ngoài browser:**
    `ShiftLocation.set_geolocation` có `@frappe.whitelist()` (JS `frm.call` gọi được);
    `hrms.fetch_geolocation` + `hrms.add_shift_tools_button_to_form` có thật và nằm trong bundle đã
    build hiện hành (`dist/js/hrms.bundle.*.js`, không cần `bench build` lại);
    hợp đồng server mà map JS dựa vào (vẽ lại vòng tròn khi đổi `checkin_radius`/toạ độ, xoá vòng
    tròn khi radius = 0) nay đã có test — 2 test mới trong `test_employee_checkin.py`, đã mutation-test.
  - **Điều kiện tiên quyết:** `allow_geolocation_tracking` đang = **0** → các field bản đồ bị
    `hide_field` nên KHÔNG thấy map. Bật tạm rồi trả về sau khi verify:
    ```bash
    bench --site miyano set-config -g allow_geolocation_tracking 1   # hoặc sửa trong HR Settings
    # ... verify trên Desk ...
    bench --site miyano execute frappe.client.set_value --kwargs \
      "{'doctype':'HR Settings','name':'HR Settings','fieldname':'allow_geolocation_tracking','value':0}"
    ```
    Lưu ý: bật cờ này cũng bật chặn check-in ngoài geofence phía server (chính là quyết định T5).
  - Các bước bấm: mở `/app/shift-location/new`, đặt `checkin_radius` = 300 → click 1 điểm trên bản đồ
    → `latitude`/`longitude` phải tự điền và vòng tròn vẽ ra; sửa `checkin_radius` = 500 → vòng tròn
    phải to lên. Rồi mở 1 `Employee Checkin` có toạ độ → thấy vòng tròn + điểm, không sửa được.
  - Files: không đổi code (chỉ verify); nếu lỗi → fix riêng.

- [ ] **T1 [GATE ①]: Chụp baseline payroll trên prod**
  - Acceptance: file CSV/JSON lưu `name, employee, start_date, payment_days, absent_days,
    leave_without_pay, gross_pay, net_pay` của mọi Salary Slip docstatus=1; đếm khớp tổng số slip.
  - Chạy: `bench --site <prod> execute hrms.payroll_gate.capture_payroll_baseline --kwargs
    "{'path': '/tmp/payroll-baseline.json'}"` → in ra số slip + checksum SHA-256; lưu file kèm backup DB.
  - Verify: sau T2 chạy `hrms.payroll_gate.compare_payroll_baseline` với đúng file đó → `identical=True`.
  - Files: `hrms/payroll_gate.py` (đã build + test 2026-07-22).

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
  - Verify: `bench --site <prod> execute hrms.payroll_gate.classifier_delta --kwargs
    "{'year': 2026, 'month': <tháng chạy song song>, 'shift': '<tên ca>'}"` — replay check-in thật của
    từng ngày qua đúng hàm ngưỡng upstream (`ShiftType.get_attendance`) rồi so `status`/`half_day_status`/
    `leave_type` với Attendance đang lưu. Chỉ chấp nhận `verdict = "no-delta"`; `"inconclusive"` nghĩa là
    KHÔNG ngày nào replay được (chấm tay, không có check-in) → chưa kiểm chứng được gì, không phải đạt.
    Chỉ mở rộng sang các ca khác sau sign-off tiếp.
  - Files: `hrms/payroll_gate.py` (đã build + test 2026-07-22).

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
