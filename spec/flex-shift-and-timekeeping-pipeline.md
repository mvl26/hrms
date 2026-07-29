# Spec — Giờ làm linh hoạt + hoàn thiện tuyến chấm công → lương

Trạng thái: **Approved (design)** — 2026-07-29. Nhánh: `feat/skip-attendance-diag`.
Liên quan: [[project-attendance-code-timekeeping]], [[project-auto-morning-afternoon]],
[[project-timekeeping-logic-2026-07]], [[project-timekeeping-payroll-state]], [[project-vn-payroll-mvl]].

## 1. Vấn đề

### 1.1 Ca cứng cắt mất giờ làm của người đi muộn về muộn

Nhân viên vào 11:00, ra 19:30 (8,5h − 1,5h trưa = **7h làm thật**). Hệ thống ghi **5h** và chấm
**1/2K → nửa công, nửa còn lại "nghỉ không lương"**.

Nguyên nhân gốc — `Attendance.apply_vn_half_day_classifier` chỉ cộng phần giờ **nằm trong khung ca
cứng** 08:00–17:30 (`hrms/hr/doctype/attendance/attendance.py`, đoạn `overlap_hours`):

- sáng 11:00–12:00 = 1h · chiều 13:30–17:30 = 4h → **5h**; toàn bộ 17:30–19:30 bị bỏ.
- độ phủ buổi sáng 1,25h/4h = 31% < 50% → kết luận "nghỉ sáng" → mã `1/2K`, status `Half Day` +
  loại nghỉ "Nghỉ không lương", chỉ **0,5 công**.

Tái hiện (không ghi DB, `apply_vn_half_day_classifier` + `apply_attendance_code_bridge` trong console):

```
in 11:00 / out 19:30, Ca Hành Chính
  → working_hours = 5.0 | mã = 1/2K
  → status = Half Day | leave_type = Nghỉ không lương | half_day_status = Present | work_credit = 0.5
```

### 1.2 Mã NN mơ hồ, và ngày nghỉ có checkin bị chấm vắng

- `NN` ("Làm nửa ngày, hưởng lương", category Công, `work_fraction` 0,5) không nói **nửa còn lại nghỉ
  vì gì**, nên report phải quy nửa đó thành **Vắng**
  (`hrms/hr/report/monthly_attendance_report/monthly_attendance_report.py`, nhánh `rest`).
  **Không có bản ghi nào trên site dùng NN.**
- Bộ phân loại **không biết khái niệm ngày nghỉ**. Auto-attendance có bỏ qua ngày lễ/T7/CN
  (`should_mark_attendance` = False — đã kiểm trên 11/07 và 12/07), nhưng nếu ngày nghỉ *có* bản ghi
  (nhập tay, Yêu cầu chấm công, hoặc bật `mark_auto_attendance_on_holidays`) thì nó đem khung
  08:00–17:30 ra chấm. Tái hiện trên T7 11/07:

```
09:00–12:00 → 1/2K      14:00–16:00 → 1/2K      12:15–13:15 → V (đi làm mà bị chấm VẮNG)
```

### 1.3 Tuyến chấm công → lương thiếu bước soát, và bước chốt không có hiệu lực

Quy trình mong muốn: `checkin → sinh công → soát công (HR sửa) → chốt công → sang lương`.

| Bước | hrms có gì | Đánh giá |
|---|---|---|
| 1. Checkin | Employee Checkin + geofence + `skip_attendance_diag` | Đủ |
| 2. Sinh công | `process_auto_attendance` (`hourly_long`) + cầu nối mã công | Đủ, đang vá (§1.1–1.2) |
| 3. **Soát công** | **không có gì** | **Thiếu** |
| 4. Chốt công | Bảng Công Tháng (submittable, có ký) | Có hình thức, **không hiệu lực** |
| 5. Sang lương | Salary Slip đọc thẳng `tabAttendance` | Chạy, nhưng **không đi qua bước 4** |

Bằng chứng:

- Auto-attendance **submit ngay** (`attendance.submit()` trong `mark_attendance`); 262/262 bản ghi
  trên site đang `docstatus=1`.
- **Không field nào có `allow_on_submit`**, kể cả 5 custom field Miyano → HR sửa một ngày công phải
  **Cancel → Amend**. Thực tế **0/262 bản ghi từng được amend**.
- Không có danh sách "cần xem xét": không cờ bất thường, không màn hình gom ngày nghi vấn.
  `employee_attendance_tool` là công cụ *chấm hàng loạt theo ngày*, không phải soát.
- Bảng Công Tháng tự ghi trong docstring: "**NEVER writes to Attendance**" — ảnh chụp thuần.
- Salary Slip đọc `tabAttendance docstatus=1` trực tiếp ở **4 chỗ**:
  `calculate_lwp_ppl_and_absent_days_based_on_attendance`, `get_half_absent_days`,
  `_get_marked_attendance_days` (`payroll/doctype/salary_slip/salary_slip.py`) và
  `paid_work_days_between` (`vn_payroll/salary_slip_hook.py`). **Không hề đọc Bảng Công Tháng.**

⇒ Chốt và ký xong vẫn sửa Attendance được, lương đổi theo, bảng đã ký đứng im — **hai con số lệch
nhau mà hệ thống không cảnh báo**. Site đang có 2 bảng đã chốt (T6, T7) + 12 phiếu lương đã submit;
chúng khớp nhau chỉ vì chưa ai sửa gì sau khi chốt.

## 2. Bằng chứng đo trên site (2026-07-29)

- 212 bản ghi Attendance có in/out; **206 Present, cả 206 đều net ≥ 8h** → luật "đủ 8h" **không lấy
  mất công của ai** trên dữ liệu hiện có.
- 6 bản ghi `1/2K` đều đúng 08:00–12:00 (net 4,0h) — nửa buổi thật, không phải oan.
- **Chưa ai check-in sau 09:00** → tình huống §1.1 là dự phòng cho quy định mới, chưa có dữ liệu sai
  cần dọn.
- 0 checkin và 0 Attendance rơi vào ngày nghỉ.
- `payroll_based_on = Attendance`; Holiday List "VN Miyano 2026" (116 ngày, gồm T7 + CN) gán cho cả
  6 nhân viên, công ty và Ca Hành Chính.

## 3. Quyết định (user chốt 2026-07-29)

1. Giờ linh hoạt theo mô hình **ca trượt theo giờ vào**, biên **±3h**, ngoài biên thì **kẹp**.
2. **Nghỉ trưa cố định 12:00–13:30** theo đồng hồ (không trượt).
3. Áp dụng cho **toàn bộ Ca Hành Chính**.
4. Đủ công = làm **đúng số giờ tối thiểu, không dung sai**; thiếu giờ → **`1/2X`** (nửa công).
5. **Bỏ `NN`**. `1/2X` dùng cho chấm tự động; `1/2K` chỉ còn cho **đơn nghỉ không lương nửa ngày đã duyệt**.
6. Ngày nghỉ có checkin: **không tự chấm gì cả, nhưng cấm tuyệt đối việc đánh vắng**.
7. Bước soát công: **màn hình soát dạng lưới**.
8. Nối lương: **khoá kỳ + đối soát bằng máy** (không sửa công thức lương).
9. Làm **gộp một spec**, triển khai theo 4 giai đoạn.

## 4. GĐ1 — Sinh công đúng

### 4.1 Cấu hình mới trên Shift Type (custom field, qua fixtures)

| Field | Kiểu | Mặc định | Nhãn |
|---|---|---|---|
| `custom_flexible_shift` | Check | 0 | Giờ làm linh hoạt |
| `custom_flex_band_minutes` | Int | 180 | Biên trượt tối đa (phút) |
| `custom_min_work_hours` | Float | 8 | Số giờ làm tối thiểu để đủ công |

`custom_min_work_hours` **bắt buộc** khi `custom_split_half_day` bật (validate trên Shift Type).

**Gỡ bỏ** (luật giờ thay thế hoàn toàn luật phủ-50%): `custom_half_day_min_fraction`,
`custom_half_day_grace_minutes` — xoá khỏi `fixtures/custom_field.json` và bộ lọc `fixtures` trong
`hooks.py` (test `test_setup_vn_defaults.py` bắt hai nơi phải khớp nhau).

### 4.2 Thuật toán thay thế trong `apply_vn_half_day_classifier`

Các chốt chặn hiện có giữ nguyên (thiếu shift/in/out → thoát; đã có mã nhập tay → thoát; `On Leave`
hoặc có `leave_type` → thoát; ca không bật `custom_split_half_day` → thoát), **thêm một chốt mới**:

```
nếu attendance_date nằm trong Holiday List của nhân viên → thoát (không tự chấm mã)
```

Rồi:

```
offset = 0
nếu custom_flexible_shift:
    band   = custom_flex_band_minutes hoặc 180 phút
    offset = kẹp(in_time − (ngày + start_time), −band, +band)

w_start, w_end = start_time + offset, end_time + offset
l_start, l_end = custom_lunch_start (12:00), custom_lunch_end (13:30)

net = overlap(in..out, w_start..w_end)
    − overlap(in..out, max(w_start, l_start)..min(w_end, l_end))
working_hours = round(net, 2)

min_h = custom_min_work_hours hoặc 8
net ≥ min_h  → mã "X"      (1 công)
net > 0      → mã "1/2X"   (0,5 công)
ngược lại    → mã "V"      (vắng)
```

Công thức `net` viết dạng "khung trừ phần trưa giao với khung" nên **đúng với mọi offset**, kể cả khi
khung ca trượt ra khỏi giờ trưa — không phụ thuộc giả định nửa sáng/nửa chiều.

Với biên ±3h và trưa 12:00–13:30: khung ca luôn bắt đầu ≤ 11:00 và kết thúc ≥ 14:30 ⇒ giờ trưa luôn
nằm trọn trong khung ⇒ luôn trừ đủ 1,5h.

Giờ làm **ngoài khung ca trượt không được cộng** — đó là chủ ý: làm thêm không tự biến thành công.

### 4.3 Mã công

Thêm `1/2X` vào `fixtures/attendance_code.json`:

| Trường | Giá trị |
|---|---|
| `code` / `name` | `1/2X` |
| `code_name` | Làm nửa ngày (thiếu giờ) |
| `category` | Công |
| `work_fraction` | 0.5 |
| `is_paid` | 1 |
| `maps_to_status` | Half Day |
| `leave_type` | (trống) |

`1/2X` cùng hình dạng với `NN` (Công / 0,5 / Half Day / không loại nghỉ) nên **thừa hưởng nguyên
đường đi đã chạy thật của `NN`**, gồm 3 chặng — đã đọc kỹ code, không suy đoán:

1. `_apply_codes_forward` (mã đơn, sáng = chiều) đặt `status = "Half Day"`, `leave_type = None`,
   `half_day_status = "Present"`, `custom_work_credit = 0.5`, `custom_attendance_code = "1/2X"`.
2. `check_leave_record` (`attendance.py:442-445`) thấy `Half Day` mà **không có Leave Application**
   → ép `half_day_status = "Absent"`.
3. `restore_code_driven_half_day_status` **không** hoàn tác, vì nhánh đó đòi mã phải **có**
   `leave_type` — `1/2X` thì không.

Kết cục `half_day_status = "Absent"` ⇒ payroll trừ đúng 0,5 công qua `get_half_absent_days`.
Test GĐ1 phải khoá cứng cả ba chặng này, vì payroll phụ thuộc vào chặng 2 chứ không phải chặng 1.

**Xoá `NN`** khỏi fixtures. Nhánh "nửa còn lại của mã Công → Vắng" trong report **giữ nguyên**, nay
phục vụ `1/2X`; cập nhật lại chú thích và `test_monthly_attendance_report.py` (đang dùng `NN`).

### 4.4 Cấu hình site

`Ca Hành Chính.begin_check_in_before_shift_start_time`: 60 → **180 phút**, nếu không thì lượt chấm
05:00–07:00 rơi ngoài cửa sổ gắn ca (`get_actual_start_end_datetime_of_shift`) và giờ "làm sớm" bị mất.
`allow_check_out_after_shift_end_time` đang 240 ≥ 180 → giữ nguyên. **Cần ký duyệt trước khi chạy.**

## 5. GĐ2 — Soát công

### 5.1 Màn hình

Desk page **Soát công tháng** (`hrms/hr/page/attendance_review/`): lưới nhân viên × ngày, dựng từ
`get_sheet_rows` — **dùng chung đúng nguồn suy diễn với report và Bảng Công Tháng**, không dựng logic
thứ hai.

Cờ bất thường (ô tô đỏ, tính trong `anomaly_flags`):

| Cờ | Điều kiện |
|---|---|
| `SINGLE_PUNCH` | ngày có Attendance nhưng < 2 lượt chấm gắn vào |
| `SHORT_HOURS` | mã `1/2X` (net < số giờ tối thiểu) |
| `NO_RECORD` | ngày làm việc, không nghỉ lễ, không có Attendance |
| `CHECKIN_ON_HOLIDAY` | ngày nghỉ nhưng có Employee Checkin |
| `ABSENT` | mã `V` |

HR sửa mã ngay trên ô, lưu hàng loạt, **mỗi lần sửa bắt buộc nhập lý do**.

### 5.2 Đường ghi duy nhất

`hrms/hr/attendance_review.py`:

- `get_review_grid(filters)` — lưới + cờ bất thường.
- `apply_correction(attendance, code, reason)` — nạp doc, đặt mã, chạy lại cầu nối, `db_set` các
  field payroll, ghi nhật ký. Quyền: HR Manager / HR User.
- `apply_corrections_bulk(rows)` — gọi vòng qua `apply_correction`, một transaction.

**Không** mở `allow_on_submit` trên form Attendance: giữ đúng **một cửa ghi** để mọi thay đổi đều
qua kiểm tra khoá kỳ và đều để lại vết.

### 5.3 Nhật ký điều chỉnh công

Doctype mới `Attendance Correction Log` (nhãn VN "Nhật ký điều chỉnh công"), không submittable, chỉ
đọc sau khi tạo: `attendance`, `employee`, `attendance_date`, `old_code`/`new_code`,
`old_status`/`new_status`, `old_half_day_status`/`new_half_day_status`, `old_leave_type`/`new_leave_type`,
`reason` (bắt buộc), `corrected_by`, `corrected_on`.

## 6. GĐ3 — Chốt công có hiệu lực

`hrms/hr/period_lock.py::is_period_locked(employee, date)` — có Bảng Công Tháng `docstatus=1` phủ
ngày đó cho công ty (và phòng ban, nếu bảng có phòng ban) của nhân viên.

Gắn vào `doc_events["Attendance"]`: chặn `on_update_after_submit`, `on_cancel`, và chặn ngay trong
`apply_correction`. Muốn sửa kỳ đã chốt → phải **huỷ bảng chốt**, việc huỷ để lại vết qua `docstatus`.

Bảng Công Tháng `before_submit`: cảnh báo (không chặn) nếu vẫn còn ô mang cờ bất thường chưa xử lý.

**Auto-attendance phải BỎ QUA kỳ đã chốt, không được ném lỗi.** Phát hiện khi build: bảng T7/2026
được chốt giữa tháng trong khi tháng chưa hết, nên chốt chặn ở `before_insert` làm
`process_auto_attendance` ném lỗi và **giết cả job cho mọi nhân viên còn lại**. Vì vậy
`ShiftType.should_mark_attendance` và `get_dates_for_attendance` đều hỏi `is_period_locked` và bỏ
qua trong im lặng — khoá nghĩa là "không đụng nữa", không phải "hỏng".

## 7. GĐ4 — Nối lương với bảng đã chốt

**Không sửa một dòng công thức lương nào.** Vì GĐ3 đã đóng băng kỳ, Attendance không thể lệch khỏi
bảng ⇒ bảng là bản quyền lực, Attendance là kho đông lạnh của nó.

`hrms/vn_payroll/sheet_gate.py`, gắn vào `doc_events["Salary Slip"]["validate"]` (additive, revert được):

1. **Chặn khi chưa chốt** — kỳ lương phải có Bảng Công Tháng đã chốt phủ hết nhân viên của phiếu.
2. **Đối soát bằng máy** — lấy số công của nhân viên từ bảng đã chốt, so với `payment_days` /
   `absent_days` mà controller vừa tính từ Attendance; lệch → `throw` kèm bảng so sánh hai bên.

**Công thức đối soát — đã chốt bằng dữ liệu thật (2026-07-29):**

```
payment_days  ==  cột "Tổng công" của nhân viên trong bảng đã chốt
```

Đo trên 12 phiếu lương thật T6+T7/2026: **10/12 khớp tuyệt đối**. Hai phiếu còn lại
(HR-EMP-00002, cả hai tháng) lệch **đúng 0,5** — và đó là **lệch thật, không phải sai công thức**:

> Ngày 05/06 mã `1/2P` (nghỉ phép năm nửa ngày, **có lương**, có Leave Application đã duyệt) lại
> mang `half_day_status = "Absent"`, nên `get_half_absent_days` trừ 0,5 của **nửa ngày phép có
> lương**. Bảng công đã ký ghi 20,5 công, phiếu lương đã trả 20,0. Nhân viên vừa bị trừ quỹ phép
> vừa bị trừ nửa ngày lương cho cùng một nửa ngày.

`restore_code_driven_half_day_status` hiện chỉ chữa trường hợp mã công **không** có đơn nghỉ; ngày
đi qua đường Leave Application (đường bình thường) vẫn bị. Cổng đối soát **chặn đúng 2 phiếu này**
và test khoá hiện trạng lại, để khi sửa lỗi đó thì con số về 0 một cách có chủ đích.
**Việc sửa nằm ngoài phạm vi spec này** — nó đụng cầu nối payroll nên cần cổng ký riêng.

Cổng **TẮT mặc định**; bật bằng site config `hrms_enforce_sheet_gate: 1` sau khi 2 phiếu lệch trên
được xử lý — bật khi còn phiếu lệch thì không ai lập được lương.

## 8. Bất biến & rủi ro

**Bất biến lương phải chứng minh trước khi merge:**

- `offset = 0` ⇒ khung ca y hệt hôm nay.
- 206/206 ngày Present hiện có net ≥ 8h ⇒ vẫn `X`, không mất công nào.
- 6 ngày `1/2K` (4,0h) → `1/2X`: cả hai đều trừ 0,5 ⇒ `payment_days` không đổi.
- 12 phiếu lương T6/T7: `payment_days` / `absent_days` / `leave_without_pay` **bằng nhau trước–sau**.

**Rủi ro đã nêu và user vẫn chọn giữ:**

- Ngưỡng đúng 8h **không dung sai**: máy chấm thật ra 08:00:15 / 17:29:40 → net 7,99h → `1/2X`.
  `working_hours` làm tròn 2 chữ số nên có sẵn ~±18 giây co giãn, ngoài ra không có. Đường thoát:
  `custom_min_work_hours` chỉnh được (đặt 7,9) — không phải sửa code.
- Khoá kỳ sẽ chặn cả những sửa đổi hợp lệ đến muộn (đơn nghỉ duyệt sau khi chốt) → buộc phải huỷ
  bảng chốt. Đây là chủ ý.

## 9. Kiểm thử

**Tuyệt đối không `bench --site miyano run-tests`.** Dùng harness rollback (`frappe.flags.in_test`,
monkeypatch `frappe.db.commit`, savepoint mỗi test, `frappe.db.rollback()` ở `finally`).

- GĐ1: offset dương/âm/bằng 0/bị kẹp; ví dụ 11:00–19:30 → 7h + `1/2X`; 11:00–20:30 → 8h + `X`;
  cờ linh hoạt tắt → hành vi y hệt bản cũ; ngày nghỉ → không tự chấm.
- GĐ1 fixtures: `1/2X` có mặt, `NN` biến mất, `hooks.py` khớp JSON.
- GĐ2: `apply_correction` cập nhật đúng status phái sinh, ghi nhật ký, thiếu lý do → chặn;
  `anomaly_flags` cho từng loại cờ.
- GĐ3: sửa/huỷ Attendance trong kỳ đã chốt → chặn; huỷ bảng chốt → mở lại.
- GĐ4: kỳ chưa chốt → chặn tạo phiếu; bảng lệch Attendance → chặn kèm bảng so sánh; 12 phiếu thật
  vẫn qua.
- Cổng bất biến: `test_payroll_gate` + so sánh trước–sau trên toàn bộ dữ liệu T6/T7.

## 10. Triển khai — các cổng cần ký duyệt

1. `bench --site miyano migrate` (doctype mới + custom field).
2. Đồng bộ fixtures: **bỏ `NN`**, thêm `1/2X`, thêm/gỡ field Shift Type.
3. `Ca Hành Chính`: `begin_check_in_before_shift_start_time` 60 → 180.
4. `Ca Hành Chính`: bật `custom_flexible_shift`, đặt `custom_min_work_hours = 8`.
5. Bật khoá kỳ (GĐ3) và cổng lương (GĐ4) — sau khi bộ đối soát chạy sạch trên T6/T7.

Mục 3–5 đổi hành vi trên site production ⇒ **hỏi trước từng bước**, không chạy tự động.
