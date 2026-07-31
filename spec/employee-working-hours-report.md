# Spec — Báo cáo giờ làm việc nhân viên (giờ vào / giờ ra / tổng giờ / TB ngày)

Trạng thái: **Approved (design)** — 2026-07-31. Nhánh: `feat/skip-attendance-diag`.
Liên quan: [[project-working-hours-feature]], [[project-timekeeping-logic-2026-07]],
[[project-flex-shift-timekeeping-pipeline]].

## 1. Vấn đề

HR cần một bảng xem nhanh **giờ vào / giờ ra / tổng giờ / trung bình giờ mỗi ngày** của **tất cả
nhân viên đang làm việc (Active)** trong một khoảng thời gian. Hiện tại chưa có:

- Report upstream **Shift Attendance** có `in_time` / `out_time` / `working_hours` nhưng là
  **giờ gross** (chưa trừ nghỉ trưa), chỉ liệt kê từng bản ghi Attendance, **không có** dòng tổng
  theo nhân viên, **không** hiện nhân viên Active không chấm công ngày nào.
- Module `hrms/hr/working_hours.py` đã có công thức giờ net và đang nuôi dashboard/number card,
  nhưng **không có report dạng bảng** để HR mở ra xem và xuất Excel.
- Bản chạy tay hiện nay là một đoạn JS gọi `frappe.client.get_list` trên Employee Checkin, tự tính
  giờ theo ca cứng 12:00/13:30 và tự dựng Excel bằng thư viện CDN — nằm ngoài phân quyền server,
  không test được, và cho số **lệch** với bảng chấm công vì bỏ qua xử lý ca của Attendance.

## 2. Phạm vi

**Trong phạm vi:** một Script Report mới, chỉ đọc, hai chế độ xem (tổng hợp / chi tiết).

**Ngoài phạm vi (YAGNI):** tự sinh file Excel bằng thư viện ngoài (desk đã có nút Export); đọc
Employee Checkin thô; tô màu mã công (đã có *Monthly Attendance Report*); sửa bất kỳ logic chấm
công hay lương nào.

## 3. Thiết kế

### 3.1 Vị trí & tên

Script Report `Employee Working Hours` — `hrms/hr/report/employee_working_hours/` (JSON + `.py` +
`.js`), module **HR**, `ref_doctype = Attendance`, roles: HR User / HR Manager / System Manager
(không mở cho Employee — báo cáo phơi giờ giấc của toàn bộ nhân sự).

Nhãn tiếng Việt qua `hrms/translations/vi.csv`: `Employee Working Hours` → **Giờ làm việc nhân
viên** (quy ước đặt tên: tên/fieldname tiếng Anh, label tiếng Việt).

### 3.2 Nguồn dữ liệu & công thức

Đọc **Attendance** `docstatus = 1` trong khoảng ngày, KHÔNG đọc Employee Checkin thô — để số liệu
khớp 100% với bảng chấm công và dashboard giờ làm.

Giờ của một ngày = **`hrms.hr.working_hours.compute_net_hours`** dùng lại nguyên vẹn:

| Trạng thái | Cách tính |
|---|---|
| Present / Work From Home | `(out − in)` (hoặc `working_hours` nếu thiếu in/out) **− 1,5h nghỉ trưa**, sàn 0 |
| Half Day | `(out − in)` — không trừ trưa |
| Absent / On Leave | 0 |
| Ca có `custom_split_half_day` | dùng thẳng `working_hours` (đã là giờ net) — không trừ trưa lần hai |

Không đưa thêm hằng số giờ ca (12:00 / 13:30 của đoạn JS chạy tay) vào code: `Attendance.in_time`
/ `out_time` đã qua xử lý ca, kể cả ca trượt ±3h.

### 3.3 Filter

| Filter | Kiểu | Mặc định |
|---|---|---|
| `from_date` / `to_date` | Date, bắt buộc | đầu tháng → cuối tháng hiện tại |
| `company` | Link Company, bắt buộc | company mặc định của user |
| `department` / `employee` / `shift` | Link, tuỳ chọn | — |
| `view` | Select: `Summary` / `Detail` | `Summary` |
| `include_inactive` | Check | 0 — bật lên để xem cả người đã nghỉ việc trong kỳ |

Không hard-code danh sách nhân viên loại trừ (đoạn JS chạy tay loại cứng 5 mã) — dùng filter.

### 3.4 Cột

**Summary** — 1 dòng / nhân viên, liệt kê **mọi nhân viên Active** khớp filter, *kể cả người 0
giờ* (để thấy ngay ai không chấm công):

`Nhân viên | Tên | Phòng ban | Số ngày có chấm giờ | Tổng giờ | TB giờ/ngày | Giờ vào TB | Giờ ra TB`

**Detail** — 1 dòng / nhân viên / ngày, chỉ những ngày có Attendance:

`Nhân viên | Tên | Ngày | Thứ | Ca | Trạng thái | Giờ vào | Giờ ra | Số giờ`

Ba thẻ tóm tắt (report summary): Tổng giờ · Số nhân viên có chấm giờ · TB giờ/ngày toàn kỳ.

### 3.5 Quy ước tính

- **Số ngày có chấm giờ** = số ngày có giờ net > 0. Ngày nghỉ / vắng / 0 giờ **không** vào mẫu số.
- **TB giờ/ngày** = Tổng giờ ÷ Số ngày có chấm giờ; bằng 0 khi mẫu số bằng 0 (không chia 0).
- **Giờ vào TB / Giờ ra TB** = trung bình giờ đồng hồ của các ngày có giờ net > 0, hiển thị `HH:MM`.
  Ca qua đêm đọc theo giờ đồng hồ (giới hạn đã biết, Miyano dùng ca hành chính).
- Gọi là **"ngày có chấm giờ"**, cố ý tránh chữ "công" để không lẫn với công tính lương.

### 3.6 Ràng buộc

**Chỉ đọc.** Report không ghi, không sinh Attendance, không đụng Salary Slip → payroll-neutral theo
định nghĩa; không cần cổng ký duyệt payroll-invariance.

## 4. Tiêu chí chấp nhận

1. Present 08:00→17:30 ra **8,0h** (9,5h gross − 1,5h trưa).
2. Half Day 08:00→12:00 ra **4,0h** (không trừ trưa).
3. Absent / On Leave ra **0h** và **không** vào mẫu số TB.
4. Ca `custom_split_half_day` **không** bị trừ trưa lần hai.
5. Nhân viên Active không có Attendance nào trong kỳ vẫn hiện ở Summary với 0 giờ, TB 0.
6. TB giờ/ngày = tổng ÷ số ngày có giờ > 0 (ví dụ 8 + 6 + 0 → 2 ngày, TB 7,0).
7. Filter khoảng ngày / phòng ban / nhân viên / ca lọc đúng; ngoài khoảng không lọt vào.
8. Attendance `docstatus = 0` hoặc `2` không được tính.
9. `view = Detail` trả 1 dòng mỗi Attendance với `HH:MM` giờ vào/ra; `view = Summary` trả 1 dòng
   mỗi nhân viên.
10. Người đã nghỉ việc không hiện khi `include_inactive = 0`, có hiện khi bật.

## 5. Test

Chạy qua **rollback harness** (không `bench --site miyano run-tests`), file
`hrms/hr/report/employee_working_hours/test_employee_working_hours.py`, kế thừa
`PerTestRollback` + `FrappeTestCase`, dựng nhân viên/Attendance riêng cho từng test.
