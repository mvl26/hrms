# Thiết kế: Tổng giờ làm trong Bảng chấm công + Dashboard quản lý

- **Ngày:** 2026-06-30
- **App:** hrms (fork Miyano)
- **Trạng thái:** Đã duyệt thiết kế, chuẩn bị lập kế hoạch triển khai

## 1. Mục tiêu

Bổ sung khả năng tính và theo dõi **tổng giờ làm thực tế** của nhân sự:

1. Thêm cột **Tổng giờ làm** vào report `Monthly Attendance Sheet` (bảng chấm công hàng tháng, dùng để xuất Excel).
2. Tổng giờ làm **không bao gồm 90 phút nghỉ trưa**.
3. Cho phép gộp tổng **theo tháng hoặc theo tuần** qua một bộ lọc.
4. Tạo **Dashboard quản lý** gồm 2 biểu đồ: xu hướng giờ làm theo tuần và giờ làm theo phòng ban.

## 2. Quyết định thiết kế (đã chốt với người dùng)

| Hạng mục | Quyết định |
|---|---|
| Con số hiển thị | Giờ làm **thực tế** (không phải định mức 8h×ngày) |
| Nguồn giờ mỗi ngày | `out_time − in_time`; thiếu in/out → fallback trường `working_hours` |
| Trừ 90' nghỉ trưa | Chỉ ngày **Present** (cả ngày) và **Work From Home** mới trừ 1.5h; **Half Day không trừ** |
| Work From Home | Tính như Present (out−in trừ 1.5h, thiếu thì fallback) |
| Gộp tổng | Filter **"Giờ làm theo"**: Tháng (mặc định) / Tuần |
| Dashboard | 2 biểu đồ: xu hướng theo tuần + theo phòng ban (KHÔNG làm KPI cards, KHÔNG làm Top nhân sự) |

## 3. Quy tắc tính giờ net mỗi ngày

Với mỗi bản ghi `Attendance` (docstatus = 1) trong kỳ:

```
gross = (out_time − in_time) quy ra giờ
      = working_hours            (nếu in_time hoặc out_time thiếu)

net (theo status):
  Present, Work From Home  → net = max(gross − 1.5, 0)
  Half Day                 → net = gross
  Absent/On Leave/Holiday/Weekly Off/khác → net = 0
```

Ghi chú:
- `1.5` giờ = 90 phút nghỉ trưa, đặt thành hằng số `LUNCH_BREAK_HOURS = 1.5`.
- Sàn ở 0 để tránh giá trị âm khi `gross < 1.5`.
- `gross` quy đổi ra giờ thập phân, làm tròn 2 chữ số khi hiển thị.

## 4. Kiến trúc

Một thư viện lõi dùng chung, report và dashboard cùng gọi vào để **không lặp logic trừ 90'**.

```
hrms/hr/working_hours.py                       ← LÕI (mới)
   ├── report monthly_attendance_sheet         ← cột + filter (sửa)
   └── dashboard_chart_source                   ← 2 nguồn biểu đồ (mới)
         ├── working_hours_by_week
         └── working_hours_by_department
```

### 4.1. Lõi `hrms/hr/working_hours.py` (mới)

Module thuần Python, không trạng thái, dễ test độc lập. Giao diện công khai:

| Hàm | Đầu vào | Trả về |
|---|---|---|
| `LUNCH_BREAK_HOURS` | hằng số | `1.5` |
| `compute_net_hours(status, in_time, out_time, working_hours)` | 1 bản ghi | float net giờ của 1 ngày |
| `get_net_hours_map(filters)` | filters (company/companies, month, year, [employee]) | `{employee: {shift: {day_of_month: net_hours}}}` |
| `get_week_buckets(year, month)` | năm, tháng | list theo thứ tự: `[{"label": "Tuần 1", "days": [d,...]}, ...]` |
| `get_hours_by_week(filters)` | filters | `{"labels": [...tuần...], "values": [...tổng giờ...]}` |
| `get_hours_by_department(filters)` | filters | `{"labels": [...phòng ban...], "values": [...tổng giờ...]}` |

**`get_week_buckets`**: tuần dương lịch Thứ 2 → Chủ nhật (ISO). Mỗi tuần chỉ tính các ngày **nằm trong tháng** (tuần đầu/cuối có thể không đủ 7 ngày). Nhãn `Tuần 1..N` theo thứ tự thời gian; `N` thường là 5, đôi khi 6.

**`get_net_hours_map`**: truy vấn `Attendance` một lần (lấy `employee, shift, attendance_date/day, status, in_time, out_time, working_hours`), áp `compute_net_hours` cho từng bản ghi, gom theo employee→shift→ngày. Tái dùng điều kiện lọc giống report hiện tại (docstatus=1, company in companies, đúng tháng/năm, optional employee).

**`get_hours_by_week` / `get_hours_by_department`**: gọi `get_net_hours_map`, cộng dồn toàn công ty theo tuần / theo phòng ban (join `Employee.department`). Trả về dạng `{labels, values}` để chart source bọc lại thành `{labels, datasets}`.

### 4.2. Report `monthly_attendance_sheet` (sửa)

**`monthly_attendance_sheet.js`** — thêm filter:
```
{
  fieldname: "working_hours_period",
  label: __("Working Hours By"),
  fieldtype: "Select",
  options: ["Month", "Week"],   // hiển thị: Tháng / Tuần
  default: "Month",
}
```

**`monthly_attendance_sheet.py`** — thay đổi tối thiểu, gọi lõi:

- `get_columns(filters)`: sau các cột ngày (detailed view) và cuối summarized view, thêm:
  - Nếu `working_hours_period == "Month"`: 1 cột `total_working_hours` — label "Tổng giờ làm", fieldtype Float, width ~120.
  - Nếu `== "Week"`: các cột `week_1..week_N` (label "Tuần 1..N") + cột `total_working_hours` ("Tổng tháng"), đều Float. Số cột tuần lấy từ `get_week_buckets`.
- `get_data` / `get_rows`: nạp `net_hours_map = get_net_hours_map(filters)` một lần, truyền xuống.
  - **Detailed view**: mỗi dòng là (employee, shift) → tổng net của đúng shift đó (theo tháng) hoặc tổng từng tuần (theo tuần).
  - **Summarized view**: mỗi dòng là employee → tổng net mọi shift của employee.
- Giá trị cột là Float giờ (làm tròn 2 chữ số).

Không thay đổi logic status/ngày/biểu đồ hiện có của report.

### 4.3. Dashboard "Quản lý giờ làm" (mới)

Theo đúng cấu trúc đóng gói có sẵn của hrms.

**Dashboard Chart Source** (code trong app, mỗi nguồn = 1 thư mục `.py/.js/.json/__init__.py`):

- `hrms/hr/dashboard_chart_source/working_hours_by_week/`
  - `get_data(...)` đọc `filters` (company, month, year — mặc định tháng hiện tại), gọi `working_hours.get_hours_by_week`, trả `{"labels", "datasets":[{"name":"Giờ làm","values":[...]}]}`. Loại biểu đồ gợi ý: **line**.
- `hrms/hr/dashboard_chart_source/working_hours_by_department/`
  - tương tự, gọi `get_hours_by_department`, biểu đồ **bar**.

Tham chiếu source mẫu: `hrms/hr/dashboard_chart_source/employees_by_age/` (dùng `@frappe.whitelist()` + `@cache_source`, chữ ký `get_data(chart_name, chart, no_cache, filters, from_date, to_date, timespan, time_interval, heatmap_year)`).

**Dashboard Chart** (2 record JSON trong `hrms/hr/dashboard_chart/`): type `Custom`, trỏ `source` tới 2 chart source trên; `filters_json` chứa company/month/year.

**Dashboard** (`hrms/hr/hr_dashboard/working_hours/working_hours.json`): chứa 2 chart, tiêu đề "Working Hours" / "Quản lý giờ làm".

## 5. Test

Bổ sung vào `hrms/hr/report/monthly_attendance_sheet/test_monthly_attendance_sheet.py` và test mới cho lõi:

- `compute_net_hours`: ngày Present đủ giờ → trừ 1.5h; Half Day → không trừ; thiếu in/out → fallback working_hours; gross < 1.5 → sàn 0; WFH như Present.
- `get_week_buckets`: tháng bắt đầu/kết thúc giữa tuần → ngày phân đúng tuần, không lẫn ngày ngoài tháng.
- Report mode "Month": cột `total_working_hours` đúng tổng.
- Report mode "Week": đúng số cột tuần + giá trị từng tuần + tổng tháng = tổng các tuần.
- Mỗi chart source `get_data` trả `labels`/`datasets` đúng độ dài và tổng.

## 6. Phạm vi & rủi ro

- **Không** thay đổi schema/DB, không migration.
- File: 1 lõi mới (`working_hours.py`), sửa 2 file report (`.py`, `.js`), ~8 file dashboard mới (2 chart source × 4 file), 2 Dashboard Chart JSON, 1 Dashboard JSON, bổ sung test.
- Rủi ro chính: dữ liệu `in_time/out_time` không đầy đủ → đã có fallback `working_hours`; nếu cả hai thiếu thì net theo working_hours (có thể 0). Site `miyano` hiện chưa có bản ghi Attendance nên cần seed dữ liệu test khi kiểm thử thủ công.
- Sửa thẳng report upstream → tách logic ra `working_hours.py` để giảm xung đột khi cập nhật hrms.

## 7. Câu hỏi mở

Không còn. Mọi điểm đã chốt ở mục 2.
