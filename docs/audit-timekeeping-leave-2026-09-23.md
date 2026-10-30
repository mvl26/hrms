# Báo cáo hiện trạng hệ thống chấm công & nghỉ phép — Miyano HR

> Ngày 2026-09-23 · nhánh `feat/timesheet-and-payroll` @ `b659cbc` · site `miyano`
> Phương pháp: đọc code + spec + plan, và **truy vấn chỉ-đọc** trên site `miyano` (không chạy test,
> không sửa dữ liệu).
>
> **Trạng thái: TÀI LIỆU RÀ SOÁT — chờ review, chưa sửa gì.**
>
> **Rà lại 2026-10-12** (chỉ đọc; không chạy test, không sửa dữ liệu). Code chưa đổi từ ngày viết
> (HEAD `54a6eea` chỉ thêm chính báo cáo này), nên dẫn chứng file:dòng còn hiệu lực; A1–A5 và B2 đã
> được đọc lại tại đúng dòng và mô tả vẫn đúng. Site thì **đã đổi**: các chỗ lỗi thời được sửa tại
> chỗ và đánh dấu *(12/10)*. Mục 3.1, A16–A17, quyết định 7–9 và mục 8 là phần thêm mới. **Mục 8
> nêu báo cáo này đủ và chưa đủ cho việc gì.**
>
> **Build 2026-10-13:** nhóm việc "làm được ngay" đã có code và test — xem **mục 9**.

Báo cáo đi theo bảy nhóm chức năng cần nghiệm thu: **chấm công tự động · tạo chấm công đúng quy tắc
· mã công · số công · số giờ làm việc · nghỉ nửa ngày / một ngày · số ngày ăn trưa**. Thêm hai phần:
nghỉ phép (quỹ phép, loại nghỉ) và tuyến soát → chốt → lương.

---

## 0. Tóm tắt

**Phần đã có khá đầy đủ.** Hệ thống sinh chấm công tự động từ check-in theo **ca trượt ±3h**, đủ 8h
mới được đủ công. Có 17 mã công với cầu nối hai chiều sang trường lương, có cột "Tổng công" (số ngày
được trả lương), và giờ làm thực tế đã trừ giờ trưa. Cờ ăn trưa được tính theo từng ngày và có thể
chọn tay. Nghỉ phép năm tính ngày theo lịch tuần, có đơn nửa ngày, có Yêu cầu chấm công (WFH / quên
chấm / công tác), có Công Tác, có chế độ miễn chấm công, có trang soát công, có khoá kỳ bằng Bảng
Công Tháng, và có cổng đối soát lương. Trong `hrms/` có 1.325 hàm test (đếm `def test_`, gồm cả test
gốc của Frappe HR) *(12/10)*. Đợt rà này **không chạy test**, nên chưa biết bao nhiêu đang xanh (mục 8.3).

**Nhưng hiện chưa thể nghiệm thu "chạy thật", vì bốn việc chặn:**

| #  | Chặn                                                                                                                                                                                                                         | Hậu quả                                                                                                                                                                            |
| -- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| B1 | **Chấm công tự động đứng ở 23/08.** Ca "Ca Hành Chính" có `auto_update_last_sync = 0`, nên `last_sync_of_checkin` không tự tiến. **Scheduler lúc chạy lúc dừng** *(12/10)*: ngày 23/09 ghi nhận tắt; sau đó job HR có chạy trong giờ làm việc, lần cuối 10:50 ngày 12/10 rồi dừng (chi tiết mục 3.1). | 4 nhân viên không miễn chấm công không có bản ghi nào sau 21/08, kể cả V. 2 người miễn chấm công thì **đã được sinh X** tới 09/10 (66 bản ghi) *(12/10)*. Phép năm không cộng dồn vì chưa có Policy Assignment. Job dừng mà không ai được báo. |
| B2 | **Giờ định mức sai từ 14/09.** Patch bỏ ngày nghỉ tuần khỏi Holiday List đã chạy trước khi làm phần tính giờ chuẩn theo ca (plan `work-calendar-single-source`, Task 2).                          | Giờ chuẩn tháng = (số ngày trong tháng − ngày lễ) × 8h. Tháng 8 ra ≈ 248h thay vì ≈ 168h, nên cả công ty hiện "thiếu giờ".                                       |
| B3 | **Chấm một lần trong ngày vẫn được X đủ công** (chỉ bị gắn cờ `SINGLE_PUNCH` trên trang soát công).                                                                                                 | Ví dụ: đến lúc 14:00, quẹt một lần, về không quẹt → vẫn được 1 công. Nếu lần quẹt duy nhất là IN trước 12:00 thì còn được thêm 1 bữa trưa.           |
| B4 | **Cổng bảng lương đang BẬT** (`hrms_enforce_sheet_gate = 1`), nhưng Bảng Công Tháng duy nhất (`BCT-2026-00001`) đã bị huỷ.                                                                           | Không lập được phiếu lương nào cho tới khi có bảng công đã chốt.                                                                                                     |

**Ngoài ra có 17 lỗi / rủi ro** (mục 4), trong đó **5 lỗi làm lệch tiền hoặc công** (A1–A5) và
**2 lỗi phân quyền API** thêm ngày 12/10 (A16–A17), cùng **một số chức năng còn thiếu** để hoàn thiện
(mục 5). Lớn nhất là: đăng ký làm thêm giờ, nghỉ bù, cấp phép tự động hằng năm, cấp quỹ cho các loại
nghỉ theo luật, và màn hình bảng công cá nhân trên app nhân viên.

---

## 1. Kiến trúc tổng thể (một ngày công đi qua đâu)

```
Máy chấm / PWA / API ──► Employee Checkin ──(mỗi giờ, hourly_long)──► Attendance
                          │ cờ geofence              │ status / leave_type / half_day_status  ◄── LƯƠNG chỉ đọc 3 trường này
                          │ cờ "ngoài lịch"          │ Mã công · Mã sáng · Mã chiều · Công · Ăn trưa · giờ làm
                                                     ▲
  Đơn xin nghỉ ─────────────────────────────────────┤  (on submit → On Leave / Half Day + mã P, 1/2P, Ô…)
  Yêu cầu chấm công (quản lý duyệt) ────────────────┤  (W / CT / X)
  Công Tác (COO duyệt) ─────────────────────────────┤  (CT)
  Miễn chấm công (tự sinh) ─────────────────────────┤  (X, custom_auto_filled = 1)
  Mark Attendance / Upload / Soát công (sửa có lý do)┘
                                                     │
                     Báo cáo "Monthly Attendance Report" (bảng chấm công, màu, xuất Excel)
                                                     │
                     Bảng Công Tháng (submit = CHỐT, khoá kỳ) ──► Salary Slip (cổng: payment_days = Tổng công)
```

Nguồn "ngày này có phải ngày làm việc không" = **lịch tuần** (`hrms/hr/work_schedule.py`). Thứ tự
tra: Phân ca → `Employee.default_shift` → mặc định công ty (Work Calendar Settings). Holiday List nay
**chỉ còn ngày lễ**.

Luật lõi: **mã công chỉ để hiển thị**. Lương chỉ đọc `status`, `leave_type` và `half_day_status`.
Mọi đường ghi mã (đơn nghỉ, yêu cầu chấm công, đồng bộ mã) đều `db_set` riêng các trường hiển thị,
không đụng trường lương.

---

## 2. Hiện trạng theo từng chức năng

### 2.1 Chấm công tự động

**Cách chạy.** Job `hourly_long` chạy lần lượt (`hrms/hooks.py:212-218`):

1. `update_last_sync_of_checkin`;
2. `process_auto_attendance_for_all_shifts`;
3. `process_auto_shift_creation`;
4. `attendance_exempt.process_exempt_employees` (chạy sau cùng để không đua với bước chấm vắng).

- **Đọc dấu chấm:** ca đang dùng kiểu *xen kẽ vào/ra*. Dấu đầu = vào, dấu cuối = ra, `log_type`
  không được dùng cho giờ công (`employee_checkin.py:371-428`).
- **Phân loại ngày** (`hrms/hr/doctype/attendance/vn_day_classifier.py`), với ca 08:00–17:30:
  - khung ca **trượt theo giờ vào**, tối đa ±180 phút;
  - nghỉ trưa **cố định** 12:00–13:30;
  - **giờ tính công** = phần có mặt nằm trong khung ca, trừ giờ trưa. ≥ 8h → **X**; > 0 → **1/2X**;
    = 0 → **V**;
  - **giờ làm thực tế** (`working_hours`) = ra − vào − phần trùng giờ trưa, không bị khung ca cắt.
- **Chấm vắng:** ngày làm việc không có bản ghi → **Absent / V**. Trước khi ghi vắng, hệ thống thử
  dựng lại ngày từ Yêu cầu chấm công đã duyệt, và sinh X cho người miễn chấm công
  (`shift_type.py:223-267`). Không chấm ngày nghỉ tuần, ngày lễ, hay ngày trong kỳ đã khoá.
- **Miễn chấm công** (`hrms/hr/attendance_exempt.py`): tự sinh X mọi ngày làm việc, quét lùi 31
  ngày. Không đè ngày nghỉ phép, công tác, hay yêu cầu chấm công. Site đang bật cho **2 người**
  (HR-EMP-00001, HR-EMP-00005).
- **Lỗi khi ghi** (trùng, trước ngày vào làm…): dấu chấm bị gắn `skip_auto_attendance = 1` kèm
  comment lý do. Có công cụ chẩn đoán `hrms/skip_attendance_diag.py` và công cụ dựng lại tháng
  `hrms/rebuild_attendance_from_checkin.py`.

**Cấu hình thật trên site (23/09):**

| Mục                                             | Giá trị                                                                                                    |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------ |
| Ca                                               | "Ca Hành Chính": 08:00–17:30; trưa 12:00–13:30; trượt ±180'; tối thiểu 8h; tách nửa ngày = bật |
| Ngưỡng giờ nửa ngày / vắng (chuẩn Frappe) | 0 / 0 — tắt, thay bằng bộ phân loại Miyano                                                             |
| Đánh dấu đi muộn / về sớm                 | tắt                                                                                                         |
| Chấm công ngày nghỉ                          | tắt                                                                                                         |
| Scheduler                                        | **không ổn định** — xem B1 và mục 3.1 *(12/10)*                                                                                               |
| `auto_update_last_sync`                        | **0** — phải có người hoặc máy chấm đẩy mốc đồng bộ                                      |
| Check-in cuối                                   | 20/08/2026                                                                                                   |
| Phân ca                                         | theo từng tháng, hết hạn 31/08 (nhân viên có`default_shift` nên vẫn được nhận ca)             |
| Geofence                                         | có bản đồ bán kính, nhưng`allow_geolocation_tracking = 0` nên **không cưỡng chế**        |
| Nhân viên đang làm                           | 6 (dữ liệu demo)                                                                                           |

**Test:** `test_vn_day_classifier.py` (19), `test_vn_half_day_classifier.py` (17), `test_shift_type.py`
(35), `test_employee_checkin.py` (34), `test_attendance_exempt.py` (62), `test_timekeeping_e2e.py` (7).

### 2.2 Tạo chấm công đúng quy tắc (các đường nhập tay và luật chặn)

| Đường                                            | Quy tắc hiện có                                                                                                                                                   | Mã sinh ra                                                                                                 |
| --------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Đơn xin nghỉ                                     | Đếm ngày theo lịch tuần (bỏ T7, CN, lễ). Không tạo bản ghi ngày nghỉ. Loại nghỉ bắt buộc có mã công. Nửa ngày bắt buộc chọn Sáng/Chiều.    | P, 1/2P, Ô, Cô, TS, T, NB, K, 1/2K, KH, R1, R2                                                            |
| Yêu cầu chấm công                               | Người duyệt mặc định = quản lý trực tiếp (`reports_to`), tự tạo ToDo; chỉ người duyệt hoặc HR được submit. Bỏ qua ngày đã có đơn nghỉ. | WFH→**W**, On Duty→**CT**, quên chấm / muộn-sớm→**X**; nửa ngày → W/X hoặc W/K |
| Công Tác                                          | Khi COO duyệt, sinh CT cho các ngày làm việc. Đổi X tự sinh (miễn chấm công) thành CT.                                                                   | CT                                                                                                          |
| Mark Attendance / Employee Attendance Tool / Upload | Bỏ ngày ngoài lịch tuần. Suy mã ngược từ status (Present→X, WFH→CT).                                                                                      | X, CT, V…                                                                                                  |
| Soát công tháng (trang desk)                     | Đường sửa duy nhất có kiểm soát: bắt buộc lý do, tôn trọng khoá kỳ, ghi`Attendance Correction Log`.                                                 | Mã được chọn                                                                                           |
| Check-in ngày nghỉ hoặc ngoài giờ              | Chỉ gắn cờ`custom_outside_schedule` (nền cho OT). Không sinh công.                                                                                           | —                                                                                                          |

- **Khoá kỳ** (`hrms/hr/period_lock.py`): submit Bảng Công Tháng thì khoá mọi thay đổi Attendance
  trong kỳ, theo công ty hoặc phòng ban. Chặn ở `before_insert`, `on_update_after_submit` và
  `before_cancel`.
- **Lỗ hổng:** xem A5 (khoá kỳ bị lách) và A7 (Công Tác).

### 2.3 Mã công

17 mã. Đây là dữ liệu thật trên site, khớp fixture `hrms/fixtures/attendance_code.json`:

| Mã          | Ý nghĩa                             | Nhóm          | Status lương             | Loại nghỉ                     | Công (Tổng công) |
| ------------ | ------------------------------------- | -------------- | -------------------------- | ------------------------------- | ------------------- |
| X            | Đi làm đủ công                   | Công          | Present                    | –                              | 1                   |
| 1/2X         | Làm nửa ngày (thiếu giờ)         | Công          | Half Day (nửa kia Absent) | –                              | 0,5                 |
| W            | Làm tại nhà                        | Công          | Work From Home             | –                              | 1                   |
| CT           | Đi công tác                        | Công          | Work From Home             | –                              | 1                   |
| P / 1/2P     | Phép năm / phép nửa ngày         | Phép          | On Leave / Half Day        | Nghỉ phép năm                | 1 / 1               |
| Ô / Cô     | Ốm / chăm con ốm (BHXH trả)       | Ốm            | On Leave                   | Nghỉ ốm / Nghỉ chăm con ốm | 0                   |
| TS           | Thai sản (BHXH trả)                 | Thai sản      | On Leave                   | Nghỉ thai sản                 | 0                   |
| T            | Tai nạn lao động                   | TNLĐ          | On Leave                   | Nghỉ tai nạn lao động       | 1                   |
| NB           | Nghỉ bù                             | Nghỉ bù      | On Leave                   | Nghỉ bù                       | 1                   |
| KH / R1 / R2 | Kết hôn / con kết hôn / tang      | Việc riêng   | On Leave                   | loại tương ứng              | 1                   |
| K / 1/2K     | Không lương cả ngày / nửa ngày | Không lương | On Leave / Half Day        | Nghỉ không lương            | 0 / 0,5             |
| V            | Vắng không lý do                   | Vắng          | Absent                     | –                              | 0                   |

- `-` (ngày nghỉ tuần) và `NL` (ngày lễ) **không phải mã**. Báo cáo suy ra hai ký hiệu này từ lịch.
- **Quy ước token đơn:** nửa ngày nghỉ ghi một token (`1/2P`, `1/2K`). Dạng `A/B` chỉ dùng khi hai
  buổi khác nhau (W/X, W/K).
- **Mã là neo:** mỗi Leave Type gắn đúng một mã, và hai loại không được dùng chung mã. Leave Type
  chưa có mã thì không nộp đơn được (`leave_type_code.py`, `leave_attendance_code.py`).
- **Cầu nối** (`Attendance.before_validate`, `attendance.py:61-72`) chạy theo thứ tự: phân loại giờ
  → mã ↔ status (hai chiều) → cờ ăn trưa. Có nút "Đồng bộ mã công": xem trước rồi mới áp dụng, bỏ
  qua kỳ đã khoá, và ghi log.
- **Test:** `test_attendance_code_bridge.py` (33), `test_attendance_code*.py` (15),
  `test_attendance_code_sync.py` (21), `test_attendance_code_payroll_invariance.py` (3).

### 2.4 Số công

- **Một luật duy nhất**, `paid_credit` (`monthly_attendance_report.py:257-277`): công = phần đi
  làm + phần nghỉ **do công ty trả**. Nghỉ do công ty trả gồm P, T, NB, KH, R1, R2. Không tính
  Ô, Cô, TS (BHXH trả), K và V.
- Cùng luật đó dùng cho trường "Công" trên Attendance, cột **Tổng công** trên báo cáo và Bảng Công
  Tháng, và cổng đối soát lương (`payment_days` phải bằng Tổng công, sai số 0,001).
- Ngày lễ (NL) +1 vào Tổng công. Bản ghi rơi vào ngày nghỉ tuần chỉ hiện ký hiệu, không cộng.
- **Báo cáo** có các cột: Tổng công (in đậm), Phép năm, Ốm/chăm con ốm, Thai sản, TNLĐ, Nghỉ kết
  hôn, Nghỉ riêng, Không lương, Số buổi ăn trưa, TB giờ/ngày. Có tô màu 10 trạng thái, xuất Excel
  (letterhead, chú giải, khối ký) và bản in Bảng Công Tháng.

### 2.5 Số giờ làm việc

- **Giờ làm thực tế** ghi vào `Attendance.working_hours`, tính theo 2.1.
- **Báo cáo "Employee Working Hours"** có giờ vào, giờ ra, tổng giờ, TB giờ/ngày và thẻ tóm tắt.
  Luật đếm ngày: ngày nửa ngày **có nghỉ phép** đếm 0,5 ngày; ngày **1/2X** vẫn đếm 1 ngày (người
  đó có mặt, chỉ thiếu giờ).
- **Giờ định mức và chênh lệch:** đang **SAI** (B2), vì vẫn hằng số 8h/ngày trừ theo Holiday List
  (`hrms/hr/working_hours.py:12`, `:364-398`).
- **Chưa có:** giờ làm thêm (OT), giờ đi muộn / về sớm (đang tắt), tổng giờ theo tuần.
- **Test:** `test_working_hours.py` (36), `test_employee_working_hours.py` (25).

### 2.6 Nghỉ nửa ngày / một ngày

| Trường hợp                                                      | Hiện hành                                                 | Lương        | Công                        |
| ------------------------------------------------------------------ | ----------------------------------------------------------- | -------------- | ---------------------------- |
| Nghỉ phép năm 1 ngày (đơn P)                                 | On Leave + P                                                | trả đủ      | 1                            |
| Nghỉ phép nửa ngày (đơn,`half_day`) + làm buổi còn lại | Half Day,`half_day_status = Present`, mã 1/2P            | trả đủ      | 1                            |
| Nghỉ phép nửa ngày +**không đến** buổi còn lại     | job hằng giờ ghi nửa kia = Absent bằng`set_value`     | trừ 0,5       | **vẫn ghi 1** ⚠ (A2) |
| Không lương nửa ngày (1/2K)                                   | Half Day + Nghỉ không lương                             | trừ 0,5 (LWP) | 0,5                          |
| Đi làm thiếu giờ (1/2X)                                        | Half Day, nửa kia Absent                                   | trừ 0,5       | 0,5                          |
| Nghỉ nhiều ngày có một nửa ngày                             | chuẩn Frappe,**tối đa một nửa ngày mỗi đơn** |                |                              |
| Đơn Thứ Sáu → Thứ Hai                                        | trừ 2 ngày phép (bỏ T7, CN)                             |                |                              |

- Nửa ngày bắt buộc chọn **Sáng/Chiều** (`custom_half_day_period`). Lựa chọn này **được lưu nhưng
  không hiện** ở đâu: Attendance chỉ ghi `1/2P`, còn mã sáng và mã chiều bị xoá. Yêu cầu chấm công
  thì có tôn trọng buổi.
- **Test:** `test_leave_application.py` (39), `test_leave_attendance_code.py` (9),
  `test_half_day_leave_payroll.py` (2), `test_leave_code_on_existing_attendance.py` (6).

### 2.7 Số ngày ăn trưa

Luật (`hrms/vn_payroll/lunch.py`, `effective_lunch_flag`), xét theo thứ tự:

1. Chọn tay **Có** hoặc **Không** thì thắng tuyệt đối. Có thể sửa cả trên ngày đã submit, nhưng
   không sửa được khi kỳ đã khoá.
2. Chỉ mã **X** và **1/2X** mới được ăn trưa. P, CT, W, nghỉ… đều = 0.
3. Có ≥ 2 dấu chấm: vào trước 12:00 **và** ra từ 13:30 trở đi → 1.
4. Ngày tự sinh của người miễn chấm công: chỉ được khi tick "Tự chấm ăn trưa".
5. Nửa ngày mà không đủ 2 dấu → 0.
6. Không có dấu nào (chấm tay, đã công nhận ngày công) → 1.
7. Có đúng 1 dấu thì đọc `log_type`: IN trước 12:00 → 1; OUT từ 13:30 trở đi → 1.

- Số buổi = Σ `custom_lunch`, đưa vào báo cáo, Bảng Công Tháng và phiếu lương (khoản ăn trưa).
- **Test:** `test_lunch_flag.py` (43), `hrms/vn_payroll/tests/test_lunch.py` (36).

### 2.8 Nghỉ phép

**10 loại nghỉ** (fixture `hrms/fixtures/leave_type.json`). Không loại nào cho âm, chuyển năm sau,
hay quy ra tiền.

| Loại                                                     | Mã         | Ai trả                       | Quỹ                                                  |
| --------------------------------------------------------- | ----------- | ----------------------------- | ----------------------------------------------------- |
| Nghỉ phép năm                                          | P, 1/2P     | Công ty                      | Earned leave, cộng hằng tháng                      |
| Nghỉ ốm, Nghỉ chăm con ốm, Nghỉ thai sản           | Ô, Cô, TS | BHXH (`is_ppl`, công ty 0) | quỹ riêng,**không có cơ chế cấp**        |
| Nghỉ tai nạn lao động                                 | T           | Công ty                      | quỹ riêng, không có cơ chế cấp                 |
| Nghỉ bù                                                 | NB          | Công ty                      | chỉ cấp tay (Compensatory Leave Request đã hoãn) |
| Nghỉ kết hôn (tối đa 3), con kết hôn (1), tang (3) | KH, R1, R2  | Công ty                      | quỹ riêng, không có cơ chế cấp                 |
| Nghỉ không lương                                      | K, 1/2K     | –                            | `is_lwp` (không cần quỹ)                         |

- **Quyền phép năm** (`hrms/setup_vn_leave.py`, **chạy tay**): 12 ngày + 1 ngày cho mỗi 5 năm
  thâm niên, chốt tại 1/1. Chia theo tháng cho người vào giữa năm. Không chuyển sang năm sau, hết
  hạn cuối năm.
- **Trên site:** **0 Leave Policy, 0 Leave Period, 0 Policy Assignment.** Toàn bộ 23 allocation đều
  nhập tay (demo): phép năm 12 ngày/người, và các loại khác cũng được cấp tay để test. Nghĩa là
  `assign_annual_leave` **chưa từng chạy**, và job cộng phép hằng tháng không có gì để cộng.
- **Duyệt:** chuẩn Frappe (`leave_approver` trên Employee hoặc Department), có email. **Không có
  người duyệt dự phòng** là quản lý trực tiếp, và không tạo ToDo như Yêu cầu chấm công. Trên site
  chỉ 2/6 nhân viên có `leave_approver`, và **chưa ai có `reports_to`**.
- **App nhân viên (PWA):** có form đơn nghỉ (có chọn Sáng/Chiều) và danh sách. Danh sách loại nghỉ
  chỉ gồm loại **đã có allocation** cộng loại không lương, nên khi chưa cấp quỹ thì nhân viên chỉ
  chọn được phép năm và không lương.
- **Báo cáo:** Employee Leave Balance, Leave Balance Summary và Leave Ledger (chuẩn Frappe, chưa Việt
  hoá mẫu).

### 2.9 Soát công → Chốt công → Lương

1. **Soát công tháng** (trang `attendance_review`): lưới nhân viên × ngày, gắn cờ `SINGLE_PUNCH`,
   `SHORT_HOURS`, `NO_RECORD`, `CHECKIN_ON_HOLIDAY` và `ABSENT`. Sửa qua `apply_correction`, bắt
   buộc lý do, có log.
2. **Chốt:** submit Bảng Công Tháng. Snapshot chỉ-đọc từ Attendance; submit thì khoá kỳ. Còn cờ mở
   thì chỉ **cảnh báo**, không chặn.
3. **Lương:** `sheet_gate` bắt buộc có bảng công đã chốt phủ kỳ lương, và `payment_days` = Tổng công.

---

## 3. Dữ liệu trên site `miyano` (chỉ đọc, 23/09)

- 352 Attendance (tháng 6–8), tất cả đều có mã. 502 check-in; 6 check-in bị `skip_auto_attendance`.
- Phân bố mã: X 261, V 25, CT 17, 1/2X 8, P 5, KH 6, R2 6, TS 6, 1/2P 3, K 3, …
- **Bản ghi lệch cần tính lại:**
  - `HR-ATT-2026-01716` (CT, 14/07): status Present nhưng **Công = 0**. Mã CT phải cho 1 công và
    status WFH.
  - `HR-ATT-2026-01860` (CT, 17/06): **ăn trưa = 1**, được lưu lúc 15:51 ngày 11/09, tức trước bản
    sửa "chỉ X/1/2X" lúc 16:01.
  - 2 bản ghi CT khác cũng mang status Present thay vì Work From Home.
- `Work Calendar Settings`: tuần mặc định của công ty có **7 ngày làm việc** (T2–CN). Chỉ ảnh hưởng
  nhân viên không có ca, nhưng gần như chắc chắn là cấu hình nhầm.
- Còn Holiday List rác `Salary Slip Test Holiday List` (52 ngày) từ test.
- 6 phiếu lương 7/2026 đang nháp. Bảng công duy nhất đã huỷ.

### 3.1 Thay đổi tính đến 12/10 (chỉ đọc, lúc 15:51)

- **Attendance: 352 → 418 đã submit.** 66 bản ghi mới đều là **X tự sinh** (`custom_auto_filled = 1`)
  của 2 người miễn chấm công, cho các ngày 24/08 → 09/10. 40 bản ghi đầu được tạo ngay 23/09 (sau
  lúc báo cáo này lấy số liệu), rồi 2 bản ghi mỗi ngày làm việc.
- **4 nhân viên còn lại dừng ở 21/08.** Không có check-in mới (vẫn 502, lần cuối 20/08),
  `last_sync_of_checkin` vẫn 23/08, nên job chấm vắng không sinh V cho họ.
- **Scheduler:** `Scheduled Job Log` (chỉ còn giữ từ 05/10) cho thấy bốn job HR chạy hằng giờ trong
  giờ làm việc 05–09/10 và 10:33–10:50 ngày 12/10. Sau 10:50 không còn job nào. Lúc 15:51,
  `bench scheduler status` báo *disabled* và `enable_scheduler = 0`; `System Settings` được sửa lần
  cuối lúc 13:51 ngày 12/10 bởi Administrator. **Chưa xác định được ai hay cái gì bật/tắt.**
- **Site không chỉ có HRMS:** ngày 12/10 lúc 11:03 và 11:18 có một loạt Notification `IMM-*` của
  app khác được nạp lại. Bật/tắt scheduler vì vậy không phải việc riêng của HR.
- **Không đổi:** Bảng Công Tháng duy nhất vẫn ở trạng thái huỷ, 6 phiếu lương tháng 7 vẫn nháp, 0
  Leave Policy Assignment, 0 nhân viên có `reports_to`, 6 nhân viên Active.

---

## 4. Lỗi và rủi ro phát hiện

Đã tự đọc lại code để kiểm chứng. Mức: 🔴 lệch tiền hoặc công · 🟠 lệch hiển thị hoặc quy trình ·
🟡 nhỏ. A16–A17 thêm ngày 12/10, sau khi rà các hàm `@frappe.whitelist` của lớp chấm công Miyano
(phạm vi rà ở mục 8.4).

| #   | Mức | Vấn đề                                                                                                                                                                                                                             | Bằng chứng                                                                         | Kịch bản                                                                                                                                        |
| --- | ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| A1  | 🔴   | **Một dấu chấm = X đủ công.** Bộ phân loại cần cả giờ vào lẫn giờ ra, nên thiếu giờ ra thì bỏ qua. Ngưỡng Frappe = 0, nên status giữ Present, suy ngược ra X.                                         | `attendance.py:181`                                                                | Quẹt đúng một lần lúc 14:00 → 1 công. Trang soát chỉ gắn cờ; chốt công vẫn cho qua.                                                |
| A2  | 🔴   | **Nghỉ nửa ngày có đơn + không đến buổi còn lại**: job ghi `half_day_status = Absent` bằng `set_value`, không cập nhật lại mã và công. Khớp với "2 phiếu lệch 1/2P" còn treo từ đợt ca trượt. | `shift_type.py:384-418`, `leave_application.py:313`                              | Lương trừ 0,5; bảng công ghi 1 → cổng lương chặn, hoặc phải sửa tay.**Cần anh/chị chốt** luật đúng là gì.              |
| A3  | 🔴   | **Hai buổi khác nhau cùng là "đi làm"** (X/W, X/CT): cầu nối xếp W/CT là "nửa không làm", đặt Half Day + nửa kia Absent.                                                                                        | `attendance.py:360-365`                                                            | Sáng ở văn phòng, chiều làm ở nhà: lương trừ 0,5, trong khi Công = 1.                                                                 |
| A4  | 🔴   | **Hai buổi nghỉ khác loại** (P/Ô): cả hai On Leave, chỉ giữ loại của buổi sáng.                                                                                                                                     | `attendance.py:346-352`                                                            | Lương trả 1 ngày, Công = 0,5.                                                                                                                |
| A5  | 🔴   | **Khoá kỳ bị lách.** Duyệt hoặc huỷ đơn nghỉ trên bản ghi có sẵn, Yêu cầu chấm công sửa bản ghi, `recompute_lunch_flags`: tất cả đều `db_set` thẳng, không qua hook khoá.                        | `leave_application.py:284-328`, `attendance_request.py:92-113`, `lunch.py:255` | Sau khi chốt, vẫn duyệt được đơn nghỉ lùi ngày vào kỳ đã khoá; số trên Attendance đổi, còn bảng công đã ký thì không. |
| A6  | 🟠   | **Cờ ăn trưa cũ** sau khi đổi mã bằng đơn nghỉ, Yêu cầu chấm công hoặc Đồng bộ mã: không tính lại `custom_lunch`.                                                                                      | `leave_attendance_code.py:133-168`, `attendance_code_sync.py`                    | Ngày X (ăn trưa = 1) thành P → vẫn tính 1 bữa.                                                                                            |
| A7  | 🟠   | **Công Tác:** huỷ chuyến không gỡ CT. Ngày đã có V hoặc X không được đổi thành CT. Duyệt chuyến rơi vào kỳ đã khoá thì workflow báo lỗi.                                                           | `business_trip.py:85-154`                                                          | Đi công tác ngày đã bị chấm V → vẫn V.                                                                                                  |
| A8  | 🟠   | **Bảng Công Tháng theo phòng ban lấy cả công ty**, trong khi khoá kỳ chỉ khoá phòng ban đó. Bản in **thiếu cột Nghỉ kết hôn**.                                                                        | `monthly_attendance_report.py:289-314`; print format không có `marriage_leave` | Chốt bảng công phòng A mà trong bảng có cả người phòng B.                                                                              |
| A9  | 🟠   | **Loại nghỉ không nộp được đơn**: Ốm, Cô, TS, TNLĐ, KH, R1, R2 không phải `is_lwp` và không cho âm, nên thiếu allocation là bị chặn "không đủ số dư". Không có gì tự cấp quỹ.                | `leave_application.py:394-409`                                                     | Nhân viên thật nộp đơn nghỉ ốm → lỗi.                                                                                                   |
| A10 | 🟠   | **Cửa sổ "ngoài giờ"** của check-in dùng khung cố định 08:00–17:30, không theo ca trượt.                                                                                                                           | `work_schedule.py:391-409`                                                         | Vào 07:00 hợp lệ theo ca trượt nhưng bị gắn "Ngoài giờ".                                                                                |
| A11 | 🟡   | Hai con số "TB giờ/ngày" có thể khác nhau: báo cáo giờ làm tính cả WFH có dấu chấm, bảng công thì không.                                                                                                           | `working_hours.py` vs `employee_working_hours.py`                                | —                                                                                                                                                |
| A12 | 🟡   | Soát công không tạo được bản ghi cho ô`NO_RECORD`.                                                                                                                                                                         | `attendance_review.js:260-263`                                                     | HR phải sang Mark Attendance.                                                                                                                    |
| A13 | 🟡   | Đơn nghỉ cuối tháng 12 sang tháng 1 chỉ tra ngày lễ của Holiday List năm cũ.                                                                                                                                              | `work_schedule.py:322-337`                                                         | Có thể trừ oan ngày lễ đầu năm.                                                                                                           |
| A14 | 🟡   | Trường "Loại nghỉ" (`custom_leave_reason`) trên desk còn hiện, mô tả luật cũ (chọn Ốm lấy từ quỹ phép). Không code nào đọc nó.                                                                                | `custom_field.json:695-722`                                                        | Gây hiểu nhầm cho HR.                                                                                                                          |
| A15 | 🟡   | `custom_min_work_hours` không bắt buộc; để trống thì âm thầm dùng 8h.                                                                                                                                                     | `attendance.py:224`                                                                | —                                                                                                                                                |
| A16 | 🟠   | **`recompute_lunch_flags` mở cho mọi tài khoản đăng nhập** *(12/10)*: hàm `@frappe.whitelist` không kiểm tra vai trò, ghi `custom_lunch` cho cả kỳ bằng `set_value` (cũng là đường lách khoá kỳ ở A5). Không có nút nào trên giao diện gọi hàm này. | `lunch.py:255-268` | Một nhân viên gọi thẳng API → cờ ăn trưa của cả công ty trong tháng bị tính lại, kể cả kỳ đã chốt. Giá trị vẫn theo luật 2.7, không đặt tuỳ ý được. |
| A17 | 🟠   | **Lưới soát công và xem trước đồng bộ mã không kiểm tra quyền** *(12/10)*: `get_review_grid` và `preview_sync` đọc bằng `frappe.get_all` (bỏ qua phân quyền). Hai đường ghi tương ứng (`apply_correction`, `apply_sync`) thì có `check_permission`. | `attendance_review.py:119`, `attendance_code_sync.py:91`, `monthly_attendance_report.py:245` | Mọi tài khoản đăng nhập gọi thẳng API là đọc được mã công, trạng thái, loại nghỉ của toàn công ty. |

---

## 5. Chức năng còn thiếu để hoàn thiện phần công và nghỉ phép

### P0 — trước khi nghiệm thu chạy thật

1. **Vận hành:**
   - giữ scheduler chạy ổn định và làm rõ ai bật/tắt trên site dùng chung (mục 3.1) *(12/10)*;
   - cảnh báo khi job chấm công không chạy quá một ngày — lần này job dừng cả tháng không ai biết
     *(12/10)*;
   - bật `auto_update_last_sync` cho ca, hoặc để máy chấm đẩy mốc đồng bộ;
   - quy trình phân ca hằng tháng (hoặc chỉ dùng `default_shift`);
   - restart app sau deploy.
2. **Giờ định mức theo lịch làm việc** (plan `work-calendar-single-source`, Task 1–5): giờ chuẩn =
   Σ ngày làm việc × giờ ca, không đọc Holiday List. Sửa cả `working_hours.py` và báo cáo
   `monthly_attendance_sheet` chuẩn.
3. **Luật "thiếu dấu chấm":** chốt cách xử lý một dấu (A1). Đề xuất: sinh **1/2X hoặc treo "chờ
   soát"**, và **chặn chốt công** khi còn `SINGLE_PUNCH` hoặc `NO_RECORD` chưa xử lý.
4. **Sửa các lỗi lệch số A2–A5** (đều chạm cổng lương, cần sign-off):
   - nửa còn lại của 1/2P;
   - hai buổi cùng là đi làm;
   - P/Ô;
   - khoá kỳ cho mọi đường ghi.
5. **Cấp quỹ cho các loại nghỉ theo luật** (A9): tự tạo allocation hằng năm theo mức luật. Kết hôn
   3 ngày, con kết hôn 1, tang 3, TNLĐ và Ốm theo xác nhận BHXH; hoặc chuyển các loại "theo sự kiện"
   sang dạng không cần quỹ, có trần số ngày mỗi đơn.
6. **Tính lại cờ ăn trưa và công sau mọi đường đổi mã** (A6), rồi chạy tính lại cho các bản ghi lệch
   ở mục 3.

### P1 — hoàn thiện nghiệp vụ

7. **Đăng ký làm thêm giờ (OT):** spec `overtime-registration.md` đã duyệt 22/07 nhưng **chưa
   build**. Cần doctype đăng ký và duyệt OT, đối chiếu với check-in "ngoài lịch", cột giờ OT trên
   bảng công, hệ số 150/200/300% sang lương. Còn treo: ai duyệt, OT qua nửa đêm.
8. **Nghỉ bù:** làm ngày nghỉ hoặc OT sinh quỹ Nghỉ bù (thay Compensatory Leave Request, hiện không
   dùng được vì cuối tuần không còn nằm trong Holiday List).
9. **Cấp phép năm tự động:**
   - job đầu năm chạy `assign_annual_leave`;
   - cộng thâm niên ngay tháng đủ 5 năm (hiện chờ tới 1/1 năm sau);
   - cảnh báo phép sắp hết hạn cuối năm;
   - quyết định có cho chuyển phép sang quý 1 năm sau không (Điều 113.4).
10. **Thanh toán phép chưa nghỉ khi nghỉ việc** (Điều 113.3): tính số ngày còn lại, đưa sang phiếu
    lương cuối.
11. **Bảng công cá nhân trên app nhân viên:** lịch tháng có mã công, giờ vào/ra, giờ làm, số công,
    số bữa trưa, số dư phép; nhân viên xác nhận hoặc khiếu nại trước khi chốt. PWA hiện chỉ có
    check-in, đơn nghỉ, yêu cầu chấm công và phân ca, **chưa có màn hình này**.
12. **Duyệt đơn nghỉ theo quản lý trực tiếp** (như Yêu cầu chấm công): mặc định `reports_to`, có
    ToDo, nhắc duyệt quá hạn. Điền `reports_to` và `leave_approver` cho nhân viên thật.
13. **Đi muộn / về sớm:** hiện tắt vì ca trượt. Nếu công ty cần thống kê (số lần, số phút), phải
    tính theo khung đã trượt, không theo 08:00 cố định.
14. **Hiện buổi Sáng/Chiều của nửa ngày nghỉ** trên bảng công và bản in (ví dụ `1/2P` kèm "S"/"C",
    hoặc P/X).
15. **Công Tác:** huỷ chuyến thì gỡ CT; cho đổi ngày V hoặc X thành CT; báo lỗi rõ ràng khi rơi vào
    kỳ đã khoá.
16. **Soát công:** tạo được bản ghi cho ô `NO_RECORD` ngay trên lưới; lọc theo phòng ban.

### P2 — dọn dẹp và ổn định

17. Bảng công theo phòng ban (A8), thêm cột Nghỉ kết hôn vào bản in.
18. Ẩn hoặc xoá `custom_leave_reason`. Xoá `Salary Slip Test Holiday List`. Sửa tuần mặc định công
    ty về T2–T6.
19. Cập nhật các spec đã lệch với code:
    - `leave-single-pool-vn.md` (mô hình Ô/Cô rút quỹ phép đã bỏ);
    - `attendance-code-timekeeping.md` (NN, `custom_cong`);
    - `attendance-sheet-color-coding.md`;
    - `lunch-days-attendance.md` §5.4;
    - `leave-entitlement-vn.md` (rounding);
    - docstring `business_trip.py`.
20. Nhiều plan đã làm xong nhưng ô `- [ ]` chưa tick (khoảng 450 ô), nên không dùng được làm danh
    sách việc còn lại.
21. Nhánh `version-15` (nhánh tích hợp) đang chậm 353 commit so với nhánh làm việc *(12/10)*.

### Bổ sung sau rà lại 12/10 — xếp vào P0

22. **Chặn quyền các API chấm công** (A16, A17): `recompute_lunch_flags` chỉ cho HR và phải tôn
    trọng khoá kỳ; `get_review_grid` và `preview_sync` phải kiểm tra quyền đọc Attendance.

---

## 6. Kịch bản nghiệm thu đề xuất

Điều kiện chung: ca "Ca Hành Chính" 08:00–17:30, trưa 12:00–13:30, trượt ±3h, tối thiểu 8h, ngày
thường. Cột "Kỳ vọng theo code" là kết quả **hệ thống hiện cho ra**, tính từ luật trong code. Anh/chị
đánh dấu đồng ý hoặc không vào cột cuối.

### 6.1 Chấm công tự động, mã công, số công, giờ làm, ăn trưa

| #   | Dấu chấm                                   | Mã                  | Công | Giờ làm | Ăn trưa                           | Ghi chú                                                                                         | OK? |
| --- | -------------------------------------------- | -------------------- | ----- | --------- | ----------------------------------- | ------------------------------------------------------------------------------------------------ | --- |
| T1  | 08:00 → 17:30                               | X                    | 1     | 8,0       | 1                                   |                                                                                                  |     |
| T2  | 07:30 → 17:00                               | X                    | 1     | 8,0       | 1                                   | ca trượt sớm 30'                                                                              |     |
| T3  | 08:30 → 17:30                               | **1/2X**       | 0,5   | 7,5       | 1                                   | vào muộn 30' thì khung trượt tới 18:00, về 17:30 là thiếu 30'                           |     |
| T4  | 08:30 → 18:00                               | X                    | 1     | 8,0       | 1                                   | bù đủ giờ                                                                                    |     |
| T5  | 11:30 → 21:00                               | **1/2X**       | 0,5   | 8,0       | 1                                   | vào muộn hơn biên 3h thì khung kẹp 11:00–20:30; giờ làm 8h nhưng giờ tính công 7,5h |     |
| T6  | 08:00 → 12:00                               | 1/2X                 | 0,5   | 4,0       | 0                                   |                                                                                                  |     |
| T7  | 13:30 → 17:30                               | 1/2X                 | 0,5   | 4,0       | 0                                   |                                                                                                  |     |
| T8  | chỉ IN 08:00                                | **X** ⚠       | 1     | 0         | 1                                   | A1                                                                                               |     |
| T9  | chỉ IN 14:00                                | **X** ⚠       | 1     | 0         | 0                                   | A1 — cần chốt luật                                                                           |     |
| T10 | chỉ OUT 17:30 (`log_type` OUT)            | X ⚠                 | 1     | 0         | 1                                   |                                                                                                  |     |
| T11 | không có dấu nào                         | V                    | 0     | 0         | 0                                   | job chấm vắng                                                                                  |     |
| T12 | T7 có check-in 08:00–12:00                 | không sinh bản ghi | –    | –        | –                                  | check-in gắn cờ "Ngày nghỉ"                                                                  |     |
| T13 | ngày lễ                                    | NL                   | 1     | –        | 0                                   | cộng vào Tổng công                                                                           |     |
| T14 | người miễn chấm công, không có dấu   | X (tự sinh)         | 1     | 0         | 0 nếu chưa tick, 1 nếu đã tick |                                                                                                  |     |
| T15 | người miễn chấm công, vào 09:00–10:00 | X                    | 1     | 1,0       | 0                                   | giờ chỉ để báo cáo                                                                         |     |

### 6.2 Nghỉ phép

| #   | Tình huống                                               | Kỳ vọng theo code                                                                                                                                                     | OK? |
| --- | ---------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --- |
| L1  | Đơn P 1 ngày, duyệt                                    | On Leave, P, công 1, lương đủ, quỹ −1, ăn trưa 0                                                                                                               |     |
| L2  | Đơn P Thứ Sáu → Thứ Hai                              | quỹ −2, T7 và CN hiện "-"                                                                                                                                           |     |
| L3  | Đơn P phủ một ngày lễ                                | ngày lễ không trừ quỹ, hiện NL                                                                                                                                    |     |
| L4  | Đơn P nửa ngày (Sáng) + chiều làm 13:30–17:30      | 1/2P, công 1, lương đủ, quỹ −0,5, ăn trưa 0;**không** hiện "Sáng". *Cần chạy thử: check-in buổi chiều gắn vào bản ghi nửa ngày có sẵn.* |     |
| L5  | Đơn P nửa ngày +**không đến** buổi còn lại | ⚠ lương trừ 0,5, công vẫn 1 (A2) → cần chốt: 0,5 công (nửa kia V) hay 1 công?                                                                               |     |
| L6  | Đơn K 1 ngày / K nửa ngày                             | K công 0, trừ 1 ngày LWP / 1/2K công 0,5                                                                                                                            |     |
| L7  | Đơn nghỉ ốm (Ô) 2 ngày                               | Ô, công 0, cột "Ốm";**bị chặn nếu chưa có allocation** (A9)                                                                                              |     |
| L8  | Đơn nghỉ kết hôn 4 ngày                              | bị chặn (tối đa 3 ngày liên tục)                                                                                                                                 |     |
| L9  | Đơn phép vượt số dư                                 | bị chặn (không cho âm)                                                                                                                                              |     |
| L10 | Duyệt đơn nghỉ trên ngày đã có V                  | V → P, công 1                                                                                                                                                         |     |
| L11 | Duyệt đơn nghỉ lùi vào kỳ đã chốt                | ⚠ vẫn ghi được (A5), kỳ vọng đúng: phải bị chặn                                                                                                             |     |
| L12 | Người vào làm 1/7                                      | phép năm chia theo tháng còn lại (khi đã chạy`assign_annual_leave`)                                                                                           |     |
| L13 | Người có 5 năm thâm niên tại 1/1                    | 13 ngày phép                                                                                                                                                          |     |

### 6.3 Yêu cầu chấm công, Công Tác, soát và chốt

| #   | Tình huống                                                    | Kỳ vọng theo code                                        | OK? |
| --- | --------------------------------------------------------------- | ---------------------------------------------------------- | --- |
| R1  | Yêu cầu WFH 1 ngày, quản lý duyệt                         | W, công 1, ăn trưa 0                                    |     |
| R2  | Yêu cầu quên chấm công (ngày đang V)                     | X, công 1; ăn trưa giữ 0 (A6 — không tính lại)     |     |
| R3  | Yêu cầu WFH nửa ngày, nửa kia không làm                  | W/K, công 0,5                                             |     |
| R4  | Nhân viên tự submit yêu cầu của mình                     | bị chặn (chỉ người duyệt hoặc HR)                   |     |
| R5  | Công Tác 3 ngày, COO duyệt                                  | CT 3 ngày làm việc, công 3                             |     |
| R6  | Huỷ Công Tác đã duyệt                                     | ⚠ CT vẫn còn (A7)                                       |     |
| R7  | Soát công: sửa một ô, có lý do                           | mã mới, có Correction Log, ăn trưa được tính lại |     |
| R8  | Chốt Bảng Công Tháng rồi sửa Attendance trong kỳ         | bị chặn                                                  |     |
| R9  | Tạo phiếu lương khi chưa chốt công                       | bị chặn (cổng)                                          |     |
| R10 | `payment_days` phiếu lương = Tổng công trên bảng công | khớp 100%                                                 |     |

---

## 7. Quyết định cần anh/chị chốt

1. **Một dấu chấm** (T8–T10) thì cho mấy công: X, 1/2X, hay treo chờ soát? Có chặn chốt công khi còn
   ngày thiếu dấu không?
2. **Nghỉ phép nửa ngày mà không đến buổi còn lại** (L5): 0,5 công (nửa kia V) hay vẫn 1 công?
3. **Sáng ở văn phòng, chiều WFH hoặc công tác** (A3): đủ 1 công? (Đề xuất: có.)
4. **Các loại nghỉ theo sự kiện** (kết hôn, tang, ốm, TNLĐ): cấp quỹ cố định hằng năm, hay bỏ quỹ và
   chỉ giới hạn số ngày mỗi đơn?
5. **Đi muộn / về sớm:** có cần thống kê không, khi ca trượt đã thay luật này?
6. **Thứ tự ưu tiên:** OT + nghỉ bù trước, hay bảng công cá nhân trên app trước?
7. **Dữ liệu demo trước nghiệm thu** *(12/10)*: câu hỏi cũ "bật scheduler ngay hay dọn trước" đã bị
   vượt qua — job đã chạy và ghi 66 X tự sinh (mục 3.1). Còn lại: dọn sạch dữ liệu demo rồi mới đẩy
   mốc đồng bộ của ca, hay giữ nguyên? Đẩy mốc khi chưa dọn sẽ sinh V cho 4 người từ 24/08 tới nay.
8. **Ai quản scheduler của site `miyano`** *(12/10)*: site dùng chung với app khác và scheduler đang
   lúc chạy lúc dừng. Cần một người chịu trách nhiệm, và quy ước báo cho HR khi tắt.
9. **Hai buổi nghỉ khác loại trong một ngày** (A4, ví dụ sáng P, chiều Ô) *(12/10)*: lương trả 0,5
   ngày cho khớp Tổng công? (Đề xuất: có — đúng luật `paid_credit`.) Báo cáo gốc nêu lỗi này nhưng
   chưa đưa vào danh sách quyết định.

---

## 8. Mức sẵn sàng để phát triển *(thêm 12/10)*

Báo cáo này **đủ làm danh sách lỗi** cho phần chấm công và nghỉ phép. Nó **chưa đủ** làm cơ sở lập
kế hoạch phát triển tiếp, và **không chứa nội dung nào về tối ưu** (hiệu năng, cấu trúc code).

### 8.1 Làm được ngay

| Việc | Cơ sở | Lưu ý |
| --- | --- | --- |
| B2 — giờ định mức theo lịch làm việc | plan `work-calendar-single-source` (mới làm Task 6; 37 ô chưa tick) | — |
| A5 — khoá kỳ cho mọi đường ghi | hành vi đúng đã rõ: phải chặn (L11) | chạm cổng lương → cần sign-off |
| A6 — tính lại ăn trưa sau khi đổi mã | luật ở mục 2.7 | phần chạy tính lại trên site là sửa dữ liệu → cần sign-off |
| A7, A8, A10, A12 | mô tả ở mục 4 | không cần quyết định nghiệp vụ |
| A16, A17 — phân quyền API | mục 4 | — |
| P2 mục 18–20 | mục 5 | xoá Holiday List rác và sửa tuần mặc định là sửa dữ liệu site → hỏi trước |

### 8.2 Bị chặn bởi quyết định ở mục 7

| Việc | Chờ quyết định |
| --- | --- |
| P0 mục 3 — luật một dấu chấm (A1) | 1 |
| A2 — nửa còn lại của 1/2P | 2 |
| A3 — hai buổi cùng là đi làm | 3 |
| A4 — hai buổi nghỉ khác loại | 9 |
| P0 mục 5 — cấp quỹ các loại nghỉ theo luật (A9) | 4 |
| P1 mục 13 — đi muộn / về sớm | 5 |
| Thứ tự P1 mục 7–8 (OT, nghỉ bù) so với mục 11 (bảng công cá nhân) | 6 |
| Nghiệm thu "chạy thật" | 7, 8 |

### 8.3 Cần có trước khi sửa

- **Mốc test.** Chạy bộ test qua harness rollback và ghi lại số xanh/đỏ. Chưa có mốc thì không phân
  biệt được lỗi mới với lỗi có sẵn.
- **Kỳ vọng ở mục 6 chưa được chạy thử.** Cột "Kỳ vọng theo code" suy từ đọc code; L4 tự ghi "cần
  chạy thử". Mỗi dòng ⚠ nên thành một test đỏ trước khi sửa.
- **Bảng trước/sau cho A2–A4.** Ba lỗi này sửa xong sẽ **đổi số lương có chủ đích**, nên cổng "lương
  bất biến" không áp nguyên văn được. Cần bảng `payment_days` / LWP trước và sau cho từng tình huống
  để xin sign-off.
- **Spec và plan cho từng nhóm việc.** Các mục ở phần 5 chưa có tiêu chí nghiệm thu, thứ tự phụ
  thuộc hay ước lượng.

### 8.4 Chưa rà

| Mảng | Tình trạng |
| --- | --- |
| Hiệu năng | Chưa đo, chưa đọc truy vấn. Site chỉ có 6 nhân viên demo nên chưa có số liệu tải thật. |
| Cấu trúc code, nợ kỹ thuật | Chưa đánh giá. A11 (hai cách tính "TB giờ/ngày") là dấu hiệu duy nhất được ghi lại. |
| Tính lương MVL | Chỉ rà cổng đối soát với bảng công, không rà công thức lương. |
| App nhân viên (PWA) | Chỉ liệt kê màn hình có và thiếu. |
| Phân quyền | Ngày 12/10 mới rà các hàm `@frappe.whitelist` trong `attendance_review.py`, `attendance_code_sync.py`, `attendance_exempt.py`, `working_hours.py`, `attendance_xlsx.py`, `lunch.py`, `monthly_attendance_sheet.py`, `work_calendar_settings.py`. Quyền theo vai trò trên từng doctype và các module khác chưa rà. |
| Chạy thật | Chưa có: cách nạp nhân viên thật, điền `reports_to` / `leave_approver`, đường check-in từ máy chấm về hệ thống, phương án lùi lại khi lỗi. |

---

## 9. Tiến độ build *(thêm 13/10)*

> Code nằm trong working tree: **chưa commit, chưa migrate, chưa restart app**. Site đang chạy vẫn
> là code cũ cho tới khi làm ba việc đó.

### 9.1 Đã làm (nhóm "làm được ngay" ở mục 8.1)

| Mục | Trạng thái | Ghi chú |
| --- | --- | --- |
| A16, A17 — phân quyền API | Xong | Chốt `require_timekeeping_role` (HR Manager / HR User / System Manager) trên `get_review_grid`, `preview_sync`, `recompute_lunch_flags`. |
| A5 — khoá kỳ cho mọi đường ghi | Xong phần code | Chặn: duyệt và huỷ đơn nghỉ, duyệt Yêu cầu chấm công, job ép "nửa còn lại = Absent", lượt tính lại ăn trưa. **Cần sign-off trước khi deploy.** |
| A6 — cờ ăn trưa sau khi đổi mã | Xong phần code | `refresh_lunch_flag` chạy sau đơn nghỉ, Yêu cầu chấm công và Đồng bộ mã công. Chưa chạy tính lại cho các bản ghi lệch ở mục 3 (sửa dữ liệu → hỏi trước). |
| A7 — Công Tác | Một phần | Xong: ngày đang `V` thành `CT` khi chuyến được duyệt; chuyến chạm kỳ đã chốt bị từ chối trước khi ghi ngày nào. Chưa: xem 9.3. |
| A8 — bảng công theo phòng ban | Xong | Lọc đúng phòng ban (không kéo phòng con, khớp phạm vi khoá kỳ); thêm bộ lọc Phòng ban trên báo cáo; bản in có cột KH. |
| A10 — "ngoài giờ" theo ca trượt | Xong | Khung ca trượt theo dấu chấm đầu tiên của ngày, dùng chung hàm trượt với bộ chấm công. |
| A12 — tạo ngày công trên lưới soát | Xong | `create_reviewed_day` + lưới mở hộp thoại cho ô `NO_RECORD`. Phần giao diện **chưa kiểm trên trình duyệt**. |
| A14 — ô "Loại nghỉ" cũ | Xong | Ẩn trong fixture, bỏ mô tả luật cũ. |
| B2 — giờ định mức | Xong phần lõi | Plan `work-calendar-single-source` Task 1–2. Trên dữ liệu thật: tháng 8/2026 ra 168h (21 ngày x 8h), không còn 248h. Task 3–5 chưa làm. |
| P1 mục 16 — lọc phòng ban ở soát công | Xong | Trang đã có ô lọc; sửa A8 làm nó có hiệu lực. |

### 9.2 Bằng chứng

- **Mốc test trước khi sửa** (37 module chấm công / nghỉ phép / lương VN, qua harness rollback): 926
  test, 8 fail, 126 error.
- **Sau khi sửa:** 981 test, 8 fail, 126 error. 55 test mới đều xanh; danh sách đỏ **y nguyên** mốc.
- **134 test đỏ có sẵn** gồm hai nhóm:
  - 114 do site thiếu dữ liệu mẫu của test gốc (`_Test Company`, `_T-Employee-00001`) — xanh trên CI;
  - **20 đỏ thật**, đều có từ trước: `test_salary_slip_mvl` (9), `test_code_resync_on_leave_record`
    (4), `test_attendance_exempt` (2), `test_attendance_code_sync` (2), `test_leave_attendance_code`
    (2), `test_setup_vn_leave` (1). Phần lớn là test chưa cập nhật theo đợt tách ngày nghỉ tuần
    14/09 (kỳ vọng 30 ngày công thay vì 22, ngày test rơi vào ngày nghỉ). **Chưa sửa.**
- **Cổng bất biến lương:** 6/6 phiếu lương tháng 7 chạy lại qua toàn tuyến (`validate` + hook) cho
  đúng `total_working_days`, `payment_days`, `absent_days`, LWP và thực lĩnh như đang lưu.
- Harness không ghi gì vào site (đếm 18 doctype trước/sau: không lệch).

### 9.3 Chưa làm, và vì sao

| Việc | Lý do |
| --- | --- |
| A7 — huỷ chuyến thì gỡ CT | Workflow "Cong Tac Approval" không có bước huỷ, và Attendance không có liên kết về chuyến nên không biết ngày CT nào do chuyến nào sinh. Cần thiết kế (thêm trạng thái + field liên kết). |
| A7 — ngày `X` có giờ vào/ra thật → CT | Trái luật E8 đang có test gác ("ngày có giờ vào/ra thật là dữ liệu thật, Công Tác không được đè"). P1 mục 15 ghi "V hoặc X" → cần chốt. |
| B2 — plan Task 3–5 | Khoá Holiday List chỉ đọc, nhãn hai tầng, report "Lịch hiệu lực". Không chặn việc sửa giờ định mức. |
| P2 mục 18 (phần dữ liệu) | Xoá `Salary Slip Test Holiday List` và sửa tuần mặc định 7 ngày là sửa dữ liệu site → hỏi trước. |
| P2 mục 19–20 | Cập nhật spec lệch và tick plan cũ. |
| 20 test đỏ thật ở 9.2 | Ngoài phạm vi danh sách lỗi; nên xử lý trước khi sửa A2–A4 vì nhiều test trong đó đo đúng vùng đó. |
| Mọi việc ở mục 8.2 | Chờ quyết định ở mục 7. |

### 9.4 Việc triển khai còn lại (đều cần anh/chị duyệt)

1. `bench --site miyano migrate` — nạp bản in Bảng Công Tháng (cột KH) và fixture ô "Loại nghỉ".
2. Restart app và xoá cache — code Python, `hooks.py` (hook khoá kỳ mới) và script trang Soát công.
3. Mở trang Soát công trên trình duyệt, thử bổ sung công cho một ô chưa có bản ghi.

### 9.5 Phát hiện thêm trong lúc build

- **Có người đang chạy `bench run-tests` trên site `miyano`** (test của app khác). Mỗi lần chạy,
  hook `before_tests` của HRMS tạo lại `Salary Slip Test Holiday List` rồi commit: 205 lần từ 05/10,
  gần nhất 10:30 ngày 13/10. Đây là lý do danh sách rác đó xoá rồi lại xuất hiện, và nó gây deadlock
  cho phiên đang ghi cùng lúc. Việc này trái quy tắc "không run-tests trên `miyano`".
- **A7 đổi lương có chủ đích:** ngày `V` thành `CT` là từ không lương thành có lương (cùng kiểu đơn
  nghỉ đổi `V` → `P`). Đây là thay đổi hành vi cần sign-off cùng với A5.

---

## Phụ lục A — Bản đồ file

| Chủ đề                               | File                                                                                                                         |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Sinh chấm công                        | `hrms/hr/doctype/shift_type/shift_type.py`, `hrms/hr/doctype/employee_checkin/employee_checkin.py`                       |
| Phân loại ngày (ca trượt)          | `hrms/hr/doctype/attendance/vn_day_classifier.py`, `attendance.py` (`apply_vn_half_day_classifier`)                    |
| Cầu nối mã ↔ lương                | `hrms/hr/doctype/attendance/attendance.py` (`apply_attendance_code_bridge`, `_apply_codes_forward`)                    |
| Lịch làm việc                        | `hrms/hr/work_schedule.py`, `hrms/hr/doctype/work_calendar_settings/`                                                    |
| Miễn chấm công                       | `hrms/hr/attendance_exempt.py`                                                                                             |
| Giờ làm việc                         | `hrms/hr/working_hours.py`, `hrms/hr/report/employee_working_hours/`                                                     |
| Ăn trưa                               | `hrms/vn_payroll/lunch.py`                                                                                                 |
| Mã công của đơn nghỉ              | `hrms/hr/doctype/leave_application/leave_attendance_code.py`, `hrms/hr/leave_type_code.py`                               |
| Quyền phép năm                       | `hrms/setup_vn_leave.py`                                                                                                   |
| Yêu cầu chấm công                   | `hrms/hr/doctype/attendance_request/attendance_request_miyano.py`                                                          |
| Công Tác                              | `hrms/hr/doctype/business_trip/business_trip.py`                                                                           |
| Soát công / khoá kỳ / cổng lương | `hrms/hr/attendance_review.py`, `hrms/hr/period_lock.py`, `hrms/vn_payroll/sheet_gate.py`                              |
| Bảng chấm công, Excel, bản in       | `hrms/hr/report/monthly_attendance_report/`, `hrms/hr/attendance_xlsx.py`, `hrms/hr/doctype/monthly_attendance_sheet/` |

## Phụ lục B — Spec và plan liên quan

| Nhóm       | Trạng thái                                                                                                                                                                                                                                                                                                                                             |
| ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Build xong  | `flex-shift-and-timekeeping-pipeline`, `attendance-code-as-anchor`, `attendance-exempt-employees`, `attendance-request-vs-leave`, `lunch-days-attendance` (+ `plan-lunch-auto-and-override`), `work-schedule-and-holiday-separation`, `work-schedule-integration-hardening`, `leave-entitlement-vn` (code có, chưa chạy trên site) |
| Build dở   | `work-calendar-single-source` (mới làm Task 6), `auto-morning-afternoon-attendance` (phần lớn đã được ca trượt thay thế)                                                                                                                                                                                                                 |
| Chưa build | `overtime-registration`                                                                                                                                                                                                                                                                                                                                |
