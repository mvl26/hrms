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

Đọc **Attendance** `docstatus = 1` trong khoảng ngày (không đọc Employee Checkin thô — `in_time` /
`out_time` của Attendance đã là punch đầu/cuối trong ngày, đã qua xử lý ca).

**Giờ ở báo cáo này là giờ CÓ MẶT, không phải giờ quy công.** `Attendance.working_hours` do
`vn_day_classifier.classify_day` tính chỉ cộng phần giờ **nằm trong khung ca**
(`overlap_hours(in, out, w_start, w_end)`), nên người ở lại tới 19:30 vẫn chỉ được ghi 8h. Lấy con
số đó làm mẫu số thì "TB giờ/ngày" hoá ra là **công tháng**, không phải thời gian thật ở văn phòng
— đúng lỗi HR báo 2026-07-31.

| Trường hợp | Giờ có mặt | Giờ tính công (cột đối chiếu) |
|---|---|---|
| Có cả giờ vào và giờ ra | `(ra − vào) −` phần giao với khung nghỉ trưa, **không cắt theo khung ca** | `compute_net_hours` |
| Thiếu giờ vào hoặc giờ ra (WFH, yêu cầu chấm công, nhập tay) | 0 — không xác định được thời gian ở văn phòng | `compute_net_hours` |
| Trạng thái Absent / On Leave | 0 kể cả khi có punch lẻ | 0 |

Khung nghỉ trưa lấy theo `custom_lunch_start` / `custom_lunch_end` của ca, mặc định
**12:00–13:30** (`Attendance.VN_DEFAULT_LUNCH_START/END`). Ca tạo mới mà không nhập giờ trưa bị
Frappe điền **giờ hiện tại** vào cả hai field (khung rộng 0 giây) → coi là rác, rơi về mặc định.

Đối chiếu thực tế 7/2026: TB/ngày của report khớp công cụ JS đang dùng tới 0,01h
(8,25/8,26 · 8,47/8,48 · 8,52/8,52 · 8,34/8,34 · 8,32/8,32); chỉ lệch ở ngày về giữa giờ trưa —
report trừ phần đã bước vào giờ nghỉ, công cụ JS thì không.

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

`Nhân viên | Tên | Phòng ban | Số ngày có mặt | Tổng giờ có mặt | TB giờ/ngày | Giờ vào TB | Giờ ra TB`

**Detail** — 1 dòng / nhân viên / ngày, chỉ những ngày có Attendance:

`Nhân viên | Tên | Ngày | Thứ | Ca | Trạng thái | Giờ vào | Giờ ra | Giờ có mặt | Giờ tính công`

Cột **Giờ tính công** đứng cạnh **Giờ có mặt** để soát chênh lệch với bảng chấm công (ví dụ ngày
07:55→19:38: có mặt 10,2h nhưng chỉ 8h được quy công).

Ba thẻ tóm tắt (report summary): Tổng giờ có mặt · Số NV có mặt · TB giờ/ngày toàn kỳ.

### 3.5 Quy ước tính

- **Số ngày có mặt** = số ngày có giờ có mặt > 0, tức ngày thực sự làm ở văn phòng. Ngày nghỉ,
  ngày WFH, ngày được trả công nhưng không có punch **không** vào mẫu số.
- **TB giờ/ngày** = Tổng giờ có mặt ÷ Số ngày có mặt; bằng 0 khi mẫu số bằng 0 (không chia 0).
- **Giờ vào TB / Giờ ra TB** = trung bình giờ đồng hồ của các ngày có mặt, hiển thị `HH:MM`.
  Ca qua đêm đọc theo giờ đồng hồ (giới hạn đã biết, Miyano dùng ca hành chính).
- Gọi là **"ngày có mặt"**, cố ý tránh chữ "công" để không lẫn với công tính lương.

### 3.6 Ràng buộc

**Chỉ đọc.** Report không ghi, không sinh Attendance, không đụng Salary Slip → payroll-neutral theo
định nghĩa; không cần cổng ký duyệt payroll-invariance.

## 4. Tiêu chí chấp nhận

1. Present 08:00→17:30 ra **8,0h** (9,5h gross − 1,5h trưa).
2. Half Day 08:00→12:00 ra **4,0h** (không chạm giờ trưa nên không trừ).
3. Absent / On Leave ra **0h** và **không** vào mẫu số TB, kể cả khi có punch.
4. Ca tách buổi 08:00–17:30, có mặt 08:00→19:30 ra **10,0h** giờ có mặt và **8,0h** giờ tính công
   — giờ có mặt KHÔNG bị cap ở khung ca.
4b. Ngày không có giờ vào/ra ra **0h** và không vào mẫu số.
4c. Khung nghỉ trưa rác của ca (start = end) rơi về mặc định 12:00–13:30.
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
