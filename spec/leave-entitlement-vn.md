# Spec: Định mức phép năm VN (WS3) — cấp phép 12 ngày cộng dồn tháng + thâm niên (Điều 113/114)

> Status: **APPROVED scope 2026-07-16** (3 quyết định chốt qua Q&A; xem `docs/audit-roadmap-2026-07-16.md`
> Đợt B). Đây là "WS3, spec riêng" đã hoãn từ `spec/vn-holiday-and-symbol-standardization.md`
> (quyết định #1, dòng 35 + Out-of-scope dòng 230).

## Objective

Hiện **không nhân viên nào có số dư phép**: "Nghỉ phép năm" có `is_earned_leave = 0`, site không có
Leave Policy / Leave Policy Assignment / Leave Period / Leave Allocation nào → scheduler cấp phép của
upstream là no-op, và vì `allow_negative = 0` nhân viên **không tự nộp Leave Application phép năm được**
(PWA lẫn Desk). Nghỉ bù (Compensatory Leave Request) cũng không submit được vì thiếu Leave Period.

Spec này cấp **định mức phép năm đúng Điều 113/114 BLLĐ 2019** bằng chính máy móc upstream
(earned leave + Leave Policy/Period/Assignment), qua helper on-demand idempotent — **không doctype
mới, không sửa logic upstream, không đụng payroll**.

**Success:**
1. Chạy 1 lệnh/năm → mọi nhân viên active có Leave Policy Assignment + Leave Allocation "Nghỉ phép
   năm" với định mức `12 + floor(số_năm_thâm_niên / 5)` ngày, cộng dồn ~1 ngày/tháng.
2. Nhân viên vào giữa năm được cấp đúng phần tháng đã qua (upstream pro-rata) và tiếp tục cộng dồn.
3. Leave Application "Nghỉ phép năm" submit được khi còn số dư; Compensatory Leave Request submit
   được (có Leave Period + Holiday List).
4. Không carry-forward: số dư dư cuối năm hết hạn theo kỳ cấp (stock ledger expiry).
5. Payroll bất biến: gate invariance hiện có vẫn xanh (allocation không đụng
   `status`/`leave_type`/`half_day_status`).

## Quyết định chốt (2026-07-16)

1. **Cách cấp = cộng dồn 1 ngày/tháng** (earned leave, `earned_leave_frequency = "Monthly"`) — đúng
   tinh thần Điều 113 (chưa đủ năm hưởng theo tỷ lệ), dùng scheduler sẵn có.
2. **Không carry-forward** — `is_carry_forward = 0` giữ nguyên; phép dư hết hạn cuối kỳ cấp.
3. **Thâm niên (Điều 114): +1 ngày / đủ 5 năm làm việc**, mốc = `Employee.date_of_joining`,
   tính tại ngày bắt đầu kỳ cấp (01/01 của năm). Cài đặt bằng **Leave Policy theo bậc**
   ("VN Phép năm 12 ngày", "… 13 ngày", …) — máy móc stock 100%, không hook.
4. **Helper on-demand, KHÔNG chạy trong migrate** (tạo dữ liệu giao dịch → ask-first trên prod,
   cùng quy ước với `create_vn_holiday_list`).
5. Phạm vi ERP đã chốt ở roadmap: chỉ công + `payment_days` — spec này KHÔNG đụng lương.

## Cơ chế upstream (đã điều tra — không giả định)

- **Scheduler**: `hrms/hr/utils.py:346 allocate_earned_leaves()` chạy `daily_long`
  (`hooks.py:248`). Chỉ xét Leave Type `is_earned_leave = 1`; với mỗi Leave Allocation **có link
  Leave Policy Assignment/Policy** (utils.py:354), đến kỳ (`check_effective_date`, tần suất
  Monthly + `allocate_on_day`) thì cộng `annual_allocation / 12` (pro-rata theo tháng,
  `get_monthly_earned_leave` utils.py:426, làm tròn theo `leave_type.rounding`), **cap tại
  `annual_allocation`** (utils.py:403-408).
- **Leave Policy Assignment** (`leave_policy_assignment.py:139-149`): với earned leave, allocation
  ban đầu = số phép của **các tháng đã qua** trong kỳ (`get_leaves_for_passed_period`) → go-live
  giữa năm tự đúng. `assignment_based_on = "Leave Period"` lấy `effective_from/to` từ Leave Period.
- **Hết hạn số dư**: `process_expired_allocation` chạy `daily_long` (hooks.py:246) — không
  carry-forward thì số dư chết cùng `to_date` của allocation. Stock.
- Fixtures filter ở `hooks.py:379-397` đã chứa "Nghỉ phép năm" → sửa flags trong
  `leave_type.json` sẽ được re-sync mỗi migrate (đây là **sửa Leave Type đang có** = mục ask-first
  của CLAUDE.md — được duyệt trong checkpoint build này cho dev; prod ký riêng ở Đợt A/deploy).

## Thiết kế

### 1. Fixture: bật earned leave cho "Nghỉ phép năm" (`hrms/fixtures/leave_type.json`)

```json
"is_earned_leave": 1,
"earned_leave_frequency": "Monthly",
"rounding": "0.5",
"allocate_on_day": "Last Day"   // đã là giá trị hiện tại
```

Các flag khác giữ nguyên (`is_lwp = 0`, `is_carry_forward = 0`, `allow_negative = 0`).
7 Leave Type còn lại **không đổi**.

### 2. Helper mới `hrms/setup_vn_leave.py` (on-demand, idempotent)

```python
entitlement_for(employee, on_date) -> int
    # 12 + floor(năm_thâm_niên_tại_on_date / 5); thâm niên từ date_of_joining

create_leave_period(year, company) -> name
    # "VN {company} {year}": 01/01→31/12, is_active=1; create-if-missing

assign_annual_leave(year, company, employees=None, dry_run=False) -> report dict
    # với mỗi nhân viên active (hoặc danh sách truyền vào):
    #   n = entitlement_for(emp, 01/01/year)
    #   ensure Leave Policy "VN Phép năm {n} ngày" (leave_policy_details: Nghỉ phép năm = n, submit)
    #   nếu chưa có Leave Policy Assignment cho (emp, leave_period): tạo
    #     (assignment_based_on="Leave Period") + submit + grant_leave_alloc_for_employee()
    #   đã có rồi → skip (idempotent); trả về dict per-employee {created|skipped|error}
```

Chạy: `bench --site <s> execute hrms.setup_vn_leave.assign_annual_leave --kwargs "{'year': 2026, 'company': 'Miyano'}"`.
Nhân viên mới vào giữa năm → HR chạy lại lệnh (chỉ tạo cho người thiếu) hoặc tạo tay 1 LPA.

### 3. Không carry-forward

Không code gì thêm — `is_carry_forward = 0` + allocation `to_date = 31/12` là đủ (stock expiry).
Sang năm mới HR chạy `assign_annual_leave(year+1, …)`.

## Điều KHÔNG làm (giữ additive)

- Không auto-chạy trong `after_migrate`/scheduler riêng — cấp phép là quyết định HR mỗi năm.
- Không sửa `allocate_earned_leaves` / Leave Policy Assignment / Leave Application.
- Không đụng Salary Slip, không đổi `payroll_based_on`.
- Không xử lý: nghỉ lễ trùng CN nghỉ bù, BHXH 75/100%, encashment khi thôi việc (Điều 113 k3) —
  ngoài phạm vi, đã ghi ở roadmap.

## Tech stack / Commands

Frappe/ERPNext HRMS v15, Python controllers + fixtures JSON. Test qua **rollback harness** console
(KHÔNG `bench run-tests` trên `miyano`).

```bash
cd /home/miyano/frappe-bench
bench --site miyano migrate    # sync fixture leave_type sau khi sửa JSON
bench --site miyano execute hrms.setup_vn_leave.assign_annual_leave --kwargs "{'year': 2026, 'company': 'Miyano'}"
```

## Project structure

```
hrms/fixtures/leave_type.json        (sửa — Nghỉ phép năm: is_earned_leave/frequency/rounding)
hrms/setup_vn_leave.py               (mới — entitlement_for / create_leave_period / assign_annual_leave)
hrms/tests/test_setup_vn_leave.py    (mới — unit + integration qua harness)
spec/leave-entitlement-vn.md         (spec này)
tasks/plan-leave-entitlement-and-identity.md
```

## Testing strategy (rollback harness)

1. **entitlement_for**: thâm niên <5 năm → 12; đủ 5 → 13; đủ 10 → 14; DOJ giữa năm không đổi bậc.
2. **create_leave_period**: tạo đúng from/to; idempotent.
3. **assign_annual_leave**: tạo policy đúng bậc (12/13), LPA submit + allocation ban đầu = số tháng
   đã qua (pin `frappe.flags.current_date`); chạy lại → 0 bản ghi mới (idempotent); nhân viên mới
   → chạy lại chỉ thêm người thiếu.
4. **Accrual**: gọi thẳng `allocate_earned_leaves()` với `frappe.flags.current_date` = cuối tháng
   → allocation +1.0 (bậc 12); cap tại annual_allocation.
5. **Unlock Leave Application**: nhân viên có allocation nộp đơn "Nghỉ phép năm" 1 ngày → submit OK;
   Attendance sinh ra mang mã P (bridge reverse — regression).
6. **Unlock Compensatory Leave Request**: dựng Holiday List (helper `create_vn_holiday_list`) +
   Attendance Present ngày lễ + Leave Period → CLR submit OK, allocation "Nghỉ bù" được cộng.
7. **Payroll gate**: chạy lại `test_attendance_code_payroll_invariance` — xanh nguyên vẹn.
8. Fixtures↔hooks filter sync test hiện có vẫn xanh.

## Boundaries

- **Always:** helper idempotent, additive, `git revert` được; test qua rollback harness; stage đúng file.
- **Ask first:** chạy `assign_annual_leave`/`create_leave_period` trên **prod**; deploy fixture
  Leave Type đã sửa lên prod (re-sync đổi Leave Type thật — gộp vào gate Đợt A/T2);
  mọi thay đổi thêm vào Leave Type khác.
- **Never:** auto-cấp phép trong migrate; sửa logic upstream; đụng payroll; nới test để "cho xanh".

## Open questions

Không còn — 3 quyết định sản phẩm đã chốt 2026-07-16. (Encashment khi thôi việc: ngoài phạm vi,
ghi nhận ở roadmap nếu HR cần sau.)
