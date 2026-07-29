# Spec: Tự động chấm công sáng/chiều + giờ net loại nghỉ trưa (1 bản ghi/ngày) — Phase 4

> Status: **DRAFT for approval (Phase 1 / SPECIFY).** Nối tiếp bộ mã-công đã ship
> (`spec/attendance-code-timekeeping.md` — "Phase 4: Morning/afternoon refinement" đã hoãn, nay làm).
> Độc lập với `spec/vn-holiday-and-symbol-standardization.md` (WS1/WS2 — đã có plan, build được ngay).
> **Đụng payroll → không plan/implement tới khi được duyệt + ký sign-off.**

## Objective

Chấm công auto hiện tại để **1 ca cả ngày** (VD 08:00–17:30) và tính giờ từ *lần chấm đầu → lần chấm cuối*,
nên **giờ công "ăn" luôn giờ nghỉ trưa** ("tính lố giờ trưa") và **không xác định được** nhân viên đi làm
**sáng / chiều / cả ngày**. Nhân viên chỉ chấm **2 lần/ngày** (vào đầu giờ, ra cuối giờ) nên không thể suy
giờ trưa từ dấu chấm.

Feature này: giữ **1 bản ghi Attendance/ngày** nhưng thêm **bộ phân loại sáng/chiều** đọc giờ vào/ra + lịch
ca (cấu hình được) để:
1. **Loại giờ nghỉ trưa** khỏi giờ công (tính theo *độ phủ* cửa sổ sáng + chiều, không trừ phẳng).
2. **Tự set `custom_morning_code`/`custom_afternoon_code`** → **bridge sẵn có** ra `status` (Present/Half
   Day/Absent) + `custom_cong` (1 / 0.5 / 0) + `half_day_status`.

**Success:** một ca bật chế độ tách-buổi thì auto-attendance cho ra: làm cả 2 buổi → **cả ngày** (X, công
1); chỉ 1 buổi → **nửa ngày** (công 0.5); không buổi nào đủ → **vắng**; và **giờ net = giờ sáng + giờ
chiều** (không có giờ trưa). Chứng minh được: với cùng input giờ vào/ra, kết quả status/công **giống hệt**
như nhân viên nhập tay đúng bản chất; và lượng chênh payroll so với cách ngưỡng cũ là **có chủ đích** (đúng
luật nửa ngày), được đo + ký duyệt.

## Locked decisions (2026-07-14)

1. **Mã sáng/chiều QUYẾT ĐỊNH công/status** (không chỉ hiển thị). Chỉ làm 1 buổi → Half Day, công 0.5.
   → **đụng payroll**: qua cổng bất biến (so nhập-tay-đúng) + ký duyệt + **chạy song song 1 tháng**.
2. **Quy tắc "có làm một buổi" = độ phủ ≥ 50% cửa sổ buổi** (+ ân hạn nhỏ vào muộn/ra sớm). **Cấu hình
   được** (`min_fraction` mặc định 0.5, `grace_minutes` mặc định 15).
3. **Giữ 1 Attendance/ngày** (không tách 2 ca vật lý → không đụng duplicate/overlap; giữ mô hình đã chốt).
4. **Cấu hình trên Shift Type** (custom fields, mặc định khi cài, chỉnh được). Chỉ ca **bật cờ** mới chạy
   bộ phân loại → **không đổi hành vi ca khác, không vỡ test upstream**.
5. **Móc vào `Attendance.before_validate`** (file `attendance.py` của repo — nơi bridge đã sống): gọi bộ
   phân loại **trước** `apply_attendance_code_bridge()`. **Không** cần `override_doctype_class`, không
   monkeypatch `calculate_working_hours`/`get_attendance`.
6. **Giờ net loại trưa = độ phủ** (overlap của `[in_time, out_time]` với cửa sổ sáng/chiều), **KHÔNG trừ
   phẳng 1.5h**. (Trừ phẳng sẽ làm sai các test upstream 08:00–09:30 → 0h.)

## Bối cảnh kỹ thuật (đã điều tra phiên này — không giả định)

- **Status chốt TRƯỚC khi có doc Attendance:** `ShiftType.get_attendance` (`shift_type.py:204-216`) so
  `total_working_hours` (thô, gồm trưa) với `working_hours_threshold_for_absent`/`_half_day` → trả
  Absent/Half Day/Present. Muốn để **mã sáng/chiều** quyết định status thì phải chạy **trong
  `before_validate` trước bridge** (bridge forward `_apply_codes_forward` set status từ mã).
- **Giờ + in/out + mã đáp xuống doc ở** `mark_attendance_and_link_log` (`employee_checkin.py:282-297`),
  gọi `.submit()` → `Attendance.before_validate` → `apply_attendance_code_bridge` chạy. Bản ghi auto có
  `status` nhưng chưa có mã → bridge đi nhánh **reverse** (suy mã từ status). Bộ phân loại của ta chạy
  **trước** sẽ set mã sáng/chiều → bridge đi nhánh **forward** (mã → status), thay cho reverse.
- **`calculate_working_hours`** (`employee_checkin.py:332-389`) trả `(total_hours, in_time, out_time)`;
  `in_time` = giờ chấm đầu, `out_time` = giờ chấm cuối (mọi chế độ). Với 2 lần chấm + "First Check-in and
  Last Check-out" → `total_hours = out - in` (gồm trưa).
- **`working_hours.py::compute_net_hours`** (`:17-31`, `LUNCH_BREAK_HOURS=1.5`) **chỉ dùng cho dashboard**,
  không ghi ngược Attendance. Cần **hoà giải** để không trừ trưa 2 lần (mục "Dashboard" bên dưới).
- **Gating test-safe:** test upstream `test_shift_type.py` dùng chấm 08:00–09:30 (không phủ [12:00,13:30])
  và assert status theo ngưỡng. Bộ phân loại **chỉ chạy khi ca bật `custom_split_half_day`** (các ca test
  không bật) → status/giờ của chúng **không đổi** → test xanh. Overlap-based (không trừ phẳng) là điều kiện
  bắt buộc để an toàn.
- **Chưa có `doc_events` cho Attendance/Employee Checkin**, Attendance **không** trong
  `override_doctype_class`. Custom fields `custom_morning_code`/`custom_afternoon_code` (Link → Attendance
  Code) đã có sẵn (fixtures).

## Config model — custom fields trên `Shift Type` (fixtures, mặc định khi cài)

| field | type | default | ý nghĩa |
|---|---|---|---|
| `custom_split_half_day` | Check | 0 | Bật chấm công tách buổi (VN) cho ca này. **Chỉ khi = 1** bộ phân loại mới chạy. |
| `custom_lunch_start` | Time | `12:00:00` | Bắt đầu nghỉ trưa. Cửa sổ **sáng = [start_time, lunch_start]**. |
| `custom_lunch_end` | Time | `13:30:00` | Kết thúc nghỉ trưa. Cửa sổ **chiều = [lunch_end, end_time]**. |
| `custom_half_day_min_fraction` | Float | 0.5 | Độ phủ tối thiểu của một buổi để tính "có làm buổi". |
| `custom_half_day_grace_minutes` | Int | 15 | Ân hạn vào muộn/ra sớm: kẹp `in_time`/`out_time` về mép cửa sổ nếu lệch ≤ grace. |

- Ranh giới buổi **tái dùng `Shift Type.start_time`/`end_time`** + 2 mốc trưa → khớp lịch Miyano
  (08:00–12:00 / 13:30–17:30) mà không thêm field giờ buổi.
- Deploy qua `fixtures/custom_field.json` (thêm 5 field) + đồng bộ filter `hooks.py`. Mặc định set trong
  JSON custom field; ca hiện có nhận default khi migrate.

## Classifier design — `Attendance.apply_vn_half_day_classifier()` (mới, trong `attendance.py`)

Gọi ở đầu `before_validate`, **trước** `apply_attendance_code_bridge()`. Bỏ qua (return sớm) nếu **bất kỳ**:
- không có `self.shift`, hoặc ca không bật `custom_split_half_day`;
- đã có mã nhập tay (`custom_attendance_code`/`custom_morning_code`/`custom_afternoon_code`) → tôn trọng
  người nhập;
- thiếu `self.in_time` hoặc `self.out_time` (ngày vắng/nghỉ → để bridge reverse + luồng absent xử lý);
- `self.status` là `On Leave` (ngày nghỉ phép từ Leave Application — không phải đi làm).

Ngược lại, tính (thời gian trong ngày `attendance_date`):

```
morning  = [start_time, lunch_start]         # VD 08:00–12:00
afternoon = [lunch_end, end_time]            # VD 13:30–17:30
# ân hạn: kẹp in về morning.start nếu in ≤ morning.start + grace; kẹp out về end nếu out ≥ end - grace
cover_m = overlap([in, out], morning)  / duration(morning)      # 0..1
cover_a = overlap([in, out], afternoon) / duration(afternoon)   # 0..1
worked_m = cover_m >= min_fraction
worked_a = cover_a >= min_fraction
net_hours = overlap([in, out], morning) + overlap([in, out], afternoon)   # giờ trưa tự loại
```

Set mã + giờ:
- `worked_m and worked_a` → cả ngày: `custom_morning_code = custom_afternoon_code = "X"`.
- `worked_m and not worked_a` → sáng: `custom_morning_code = "X"`, `custom_afternoon_code = "V"`.
- `not worked_m and worked_a` → chiều: `custom_morning_code = "V"`, `custom_afternoon_code = "X"`.
- không buổi nào → vắng: để `custom_attendance_code = "V"` (cả ngày Absent).
- `self.working_hours = round(net_hours, 2)`.

Sau đó `apply_attendance_code_bridge()` (forward) dựng `status`/`leave_type`/`half_day_status`/`custom_cong`
từ mã: `X|X` → Present, công 1; `X|V` → Half Day, `half_day_status=Absent`, công 0.5; `V|V`/`V` → Absent,
công 0. **Đây đúng là kết quả nhập-tay-đúng** → bridge vốn payroll-invariant giữ nguyên tính chất đó.

> Ghi chú "V" cho nửa vắng: `X|V` khớp ngữ nghĩa NN (làm nửa ngày hưởng lương, nửa kia vắng không lương) —
> cùng ra Half Day + `half_day_status=Absent`. Có thể chọn hiển thị `X/V` (rõ buổi) hoặc gộp `NN` — **chốt
> khi review** (Open Question #2).

## Payroll impact & invariance

- Đây là **thay đổi có chủ đích** cách auto-attendance chấm status: người chỉ làm 1 buổi chuyển từ
  "Present-do-đủ-ngưỡng-giờ-thô" sang **Half Day** (đúng luật). → **KHÔNG** phải thay đổi trung tính.
- **Gate bắt buộc:** test chứng minh với cùng `(in_time, out_time, ca)`, đường **code path** (qua classifier
  + bridge) cho `status`/`half_day_status`/`custom_cong` **giống hệt** đường **nhập tay** tương ứng (VD
  làm sáng → nhập tay Half Day + half_day_status Absent). Cộng một test **đo chênh** so với hành vi ngưỡng
  cũ trên vài kịch bản (cả ngày / chỉ sáng / chỉ chiều / vắng) để HR thấy rõ tác động.
- **Chạy song song 1 tháng** (bật cờ trên ca thử, đối chiếu bảng công cũ vs mới) trước khi bật đại trà.
- **Không** đụng `salary_slip.py`, `get_attendance`, `calculate_working_hours`.

## Dashboard net-hours (hoà giải, tránh trừ trưa 2 lần)

`working_hours.py::compute_net_hours` đang trừ **phẳng 1.5h** cho ngày Present. Sau feature này, Attendance
của ca tách-buổi đã lưu `working_hours` = **net** (đã loại trưa). Sửa `compute_net_hours` để **ưu tiên dùng
`working_hours` đã lưu** (net) cho các bản ghi này thay vì `out-in` − 1.5 (nếu không sẽ đúng-tình-cờ khi
trưa = 1.5h, sai khi cấu hình khác). Với bản ghi **không** tách-buổi, giữ nguyên hành vi cũ. Có test.

## Commands

```bash
cd /home/miyano/frappe-bench
bench --site miyano migrate            # nạp 5 custom field Shift Type + fixtures
# Bật thử trên một ca: set custom_split_half_day=1, lunch 12:00/13:30, rồi chạy:
bench --site miyano execute hrms.hr.doctype.shift_type.shift_type.process_auto_attendance_for_all_shifts
# Test: rollback console harness (monkeypatch frappe.db.commit→noop; savepoint/rollback mỗi test)
```

## Project structure (files)

```
hrms/hr/doctype/attendance/attendance.py                 (thêm apply_vn_half_day_classifier + gọi ở before_validate)
hrms/fixtures/custom_field.json                          (+5 field Shift Type) + hooks.py filter đồng bộ
hrms/hr/working_hours.py                                 (compute_net_hours: ưu tiên working_hours net đã lưu)
hrms/hr/doctype/attendance/test_vn_half_day_classifier.py    (mới — unit + gate + net-hours)
hrms/payroll/doctype/salary_slip/test_attendance_code_payroll_invariance.py  (thêm kịch bản sáng/chiều)
spec/auto-morning-afternoon-attendance.md               (spec này)
```

## Code style

Match repo: helper nhỏ có docstring nêu "why"; guard sớm (return khi không đủ điều kiện); tính overlap
bằng `frappe.utils` (getdate/get_time/time_diff_in_hours); tab indent; ASCII tên method (không `_` đầu —
GOTCHA `__getattr__`); tái dùng bridge thay vì tự set status.

## Testing strategy (rollback harness — NEVER `bench run-tests` trên `miyano`)

- **Gate (bất biến vs nhập tay):** với `(in,out)` = cả ngày / chỉ sáng / chỉ chiều, so `status`/
  `half_day_status`/`custom_cong` của classifier+bridge **==** nhập tay tương ứng. Mở rộng
  `test_attendance_code_payroll_invariance.py` với kịch bản nửa-ngày-sáng.
- **Classifier unit:** overlap + ngưỡng 50% + ân hạn: `in=08:00,out=17:30`→cả ngày; `in=08:00,out=12:00`→
  sáng; `in=13:30,out=17:30`→chiều; `in=08:00,out=15:00`→(chiều phủ 37.5% < 50%)→sáng; giờ net loại trưa.
- **Gate ca không bật:** ca `custom_split_half_day=0` → classifier **không chạy**, status/giờ y như stock;
  chạy lại `test_shift_type` (nhóm threshold) phải **vẫn xanh**.
- **Dashboard:** `compute_net_hours` dùng `working_hours` net đã lưu cho bản ghi tách-buổi, không trừ 2 lần.

## Boundaries

- **Always:** gate theo `custom_split_half_day`; overlap-based (không trừ phẳng); cổng bất biến vs nhập
  tay trước khi merge; fixtures additive; stage đúng file; test qua harness; revert được bằng `git revert`.
- **Ask first (STOP ký duyệt):** bật `custom_split_half_day` trên ca **prod**; deploy fixtures/field lên
  prod; **mọi** thứ đụng con số lương. Chạy song song 1 tháng trước khi bật đại trà.
- **Never:** sửa `salary_slip.py`/`get_attendance`/`calculate_working_hours`; đổi status stock của ca
  **không** bật cờ; nới lỏng test bất biến; trừ trưa phẳng làm hỏng test upstream; ghi đè mã nhập tay.

## Success Criteria

- [x] 5 custom field Shift Type cài được (mặc định 12:00/13:30/0.5/15/off), đồng bộ hooks filter.
- [x] Ca bật cờ: `in/out` phủ cả 2 buổi → X cả ngày (công 1); chỉ 1 buổi (≥50%) → Half Day (công 0.5);
      không buổi nào → Absent; `working_hours` = giờ net **loại trưa** — 8 unit test xanh.
- [x] **Gate:** classifier+bridge cho status/half_day_status/công **giống hệt** nhập tay đúng bản chất
      (payroll-invariance salary-slip xanh: morning-only == native Half Day).
- [x] Ca **không** bật cờ: `test_shift_type` threshold **vẫn xanh** (29 test — không đổi hành vi upstream).
- [x] Dashboard net-hours không trừ trưa 2 lần (dùng `working_hours` net đã lưu) — 26 test xanh.
- [x] Reversible `git revert`; verify trên dev `miyano` qua harness (**110 test xanh**).
- [ ] **CÒN LẠI (ask-first/sign-off):** đo chênh payroll classifier-vs-ngưỡng-cũ trên ca prod thật +
      **chạy song song 1 tháng** trước khi bật `custom_split_half_day` đại trà.

## Out of scope

- Tách 2 ca vật lý/ngày (multi-shift). Ca xoay/đêm qua nửa đêm. Làm thêm giờ (OT) / phụ cấp ca.
- Suy giờ trưa từ dấu chấm 4 lần (hiện 2 lần) — nếu sau này có chấm trưa, có thể ưu tiên khoảng nghỉ thực.
- Thay đổi WS1 (Holiday List) / WS2 (ký hiệu) — spec khác.

## Open Questions (chốt khi review)

1. **Ân hạn (grace) & ngưỡng:** `min_fraction=0.5`, `grace_minutes=15` ổn chưa? (chỉnh được sau.)
2. **Hiển thị nửa vắng:** buổi không làm hiện **`V`** (→ ô "X/V") hay gộp thành **`NN`** (làm nửa ngày)?
   Ảnh hưởng cách đọc bảng công, không ảnh hưởng payroll.
3. **Giờ vào/ra thực tế của ca prod:** dùng `start_time`/`end_time` của Shift Type (08:00–17:30) làm mép
   sáng/chiều — xác nhận ca prod set đúng khung này.
