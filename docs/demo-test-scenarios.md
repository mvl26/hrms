# Kịch bản test & dữ liệu demo — VN timekeeping (Miyano)

Dữ liệu tạo trên site **`miyano`** (dev). Mở Desk: **http://miyano** (cần `bench start` + đăng nhập).
**Tạo lại/reset dữ liệu:** `bench --site miyano execute hrms.demo_data.create_demo_data` (idempotent).
Tháng demo: **9/2026** (có 01–02/09 Quốc khánh → `NL`; Chủ nhật → `-`).

## Nhân sự demo (công ty Miyano)

| Mã NV | Tên | Vai trò trong demo |
|---|---|---|
| HR-EMP-00002 | Nguyễn Văn An | nhập tay **đủ 11 mã công** |
| HR-EMP-00003 | Trần Thị Bình | **bộ phân loại sáng/chiều** (giờ vào/ra) + thai sản |
| HR-EMP-00004 | Lê Văn Cường | **Công Tác** (mã CT sinh tự động khi duyệt) |
| HR-EMP-00005 | Phạm Thị Dung | **Nghỉ phép → chấm công tự động** |
| HR-EMP-00006 | Hoàng Văn Em | **Employee Checkin** + chấm công |

Chứng từ chính: Bảng Công Tháng **BCT-2026-00002** · Công Tác **CT-2026-00002** · Đơn nghỉ **HR-LAP-2026-00001**.

---

## Kịch bản 1 — Mã công (nhập tay), đủ ký hiệu VN
**Data:** An, tháng 9. **Xem:** `/app/attendance` → lọc Nhân viên = Nguyễn Văn An.
**Mong đợi:** ngày 7 `P` (phép năm, On Leave) · 8 `1/2P` (Half Day) · 9 `Ô` (ốm) · 10 `Cô` (con ốm) ·
11 **`N` (nghỉ việc riêng có lương)** · 12 `NN` (làm nửa ngày) · 14 `1/2K` (nửa ngày KL) · 15 `V` (vắng,
Absent) · 16 `K` (không lương) · 17 `NB` (nghỉ bù) · 18 `T` (tai nạn LĐ). Mỗi mã tự set đúng
`status`/`leave_type`/`half_day_status` qua cầu nối — **không đổi số lương**.

## Kịch bản 2 — Tự động sáng/chiều + giờ net loại trưa
**Data:** Bình, ngày 3–9 (nhập giờ vào/ra, ca "Ca Hành Chính" bật tách buổi). **Xem:** `/app/attendance`
→ lọc Trần Thị Bình; xem `Mã sáng`/`Mã chiều`/`Công`/`Giờ làm`.
**Mong đợi:**
| Ngày | Vào–Ra | Status | Sáng/Chiều | Công | Giờ (loại trưa) |
|---|---|---|---|---|---|
| 3 | 08:00–17:30 | Present | X / X | 1.0 | 8.0 |
| 4 | 08:00–12:00 | **Half Day** | X / V | 0.5 | 4.0 |
| 5 | 13:30–17:30 | **Half Day** | V / X | 0.5 | 4.0 |
| 7 | 08:00–15:00 | **Half Day** (chiều <50%) | X / V | 0.5 | 5.5 |
| 8 | 12:10–13:20 (trong trưa) | **Absent** | – | 0 | 0 |

## Kịch bản 3 — Lịch nghỉ lễ VN (nghỉ lễ có lương)
**Data:** Holiday List `VN Miyano 2026` (mặc định của Miyano). **Xem:** báo cáo
`/app/query-report/Monthly Attendance Report` → **Tháng 9, Năm 2026, Company Miyano**.
**Mong đợi:** cột ngày **1, 2 = `NL`** (Quốc khánh, có lương) · các **Chủ nhật (6,13,20,27) = `-`**.
Xem lịch: `/app/holiday-list/VN Miyano 2026` (52 CN + 5 lễ dương; Tết/Giỗ Tổ HR nhập tay).

## Kịch bản 4 — Nghỉ phép → chấm công tự động
**Data:** Dung có Leave Allocation "Nghỉ ốm" + đơn **HR-LAP-2026-00001** (7–8/9, đã duyệt).
**Xem:** `/app/leave-application/HR-LAP-2026-00001`; rồi `/app/attendance` lọc Phạm Thị Dung ngày 7–8.
**Mong đợi:** đơn nghỉ khi submit **tự sinh Attendance** ngày 7,8 = On Leave / `Nghỉ ốm`, hiển thị mã
**`Ô`**, có link ngược `leave_application`. (Đây là luồng auto của ERP, mã công suy ngược để hiển thị.)

## Kịch bản 5 — Công Tác + workflow + mã CT tự động
**Data:** **CT-2026-00002** (Hà Nội, 10–12/9), người đi: Bình + Cường; đã chạy workflow
Nháp → Gửi duyệt → Duyệt → **Đã ra QĐ**. **Xem:** `/app/business-trip/CT-2026-00002`.
**Mong đợi:** `workflow_state = Đã ra QĐ`; bảng "Người đi công tác" 2 dòng; khi duyệt **tự sinh mã `CT`**
(Work From Home, tính công) cho Cường ngày 10–12 (`/app/attendance` lọc Lê Văn Cường 10–12).
**Thử thêm:** nút **"Tạo đề nghị thanh toán"** trên chứng từ → tạo Expense Claim gắn `custom_business_trip`.
In: Menu → Print → **QD Cu Di Cong Tac** (QĐ) / **Giay Di Duong** (giấy đi đường, 1 tờ/người).

## Kịch bản 6 — Bảng Công Tháng (chốt sổ + in)
**Data:** **BCT-2026-00002** (đã submit/đóng băng). **Xem:** `/app/monthly-attendance-sheet/BCT-2026-00002`.
**Mong đợi:** lưới nhân viên × ngày (d01…d30) với mã công + `-`/`NL`; cột tổng **field tiếng Anh**
(`work_days`, `annual_leave`, `personal_leave`, `sick_leave`, `maternity_leave`, `work_accident_leave`,
`comp_off`, `unpaid_leave`, `absent`) nhưng **nhãn cột tiếng Việt** (Công, Phép, Việc riêng, Ốm…).
Bình: work_days 14.5 · maternity_leave 3.0 · absent 2.5. In: Print → **Monthly Attendance Sheet**
(lưới + chú thích mã + 2 ô ký). Đã submit → nút "Lấy dữ liệu" bị khoá (chỉ nháp mới lấy được).

## Kịch bản 7 — Dashboard/Report giờ làm (net, loại trưa)
**Xem:** `/app/query-report/Working Hours` (hoặc dashboard giờ làm) → tháng 9/2026, Miyano.
**Mong đợi:** giờ net = tổng phủ sáng+chiều (đã loại nghỉ trưa) cho các bản ghi ca tách-buổi; không trừ
trưa 2 lần.

## Kịch bản 8 — Employee Checkin
**Data:** Em có các cặp checkin IN 08:00 / OUT 17:30 ngày 3,4,5,9,10,11. **Xem:** `/app/employee-checkin`
→ lọc Hoàng Văn Em. (Kèm Attendance tương ứng do classifier tính.)

## Kịch bản 9 — Đặt tên tiếng Anh + hiển thị tiếng Việt
DocType/field nội bộ **tiếng Anh** (Monthly Attendance Sheet, Business Trip, `work_days`…), **label + tiêu
đề tiếng Việt** qua `label` + `hrms/translations/vi.csv`. Đổi ngôn ngữ user sang **Tiếng Việt**
(avatar → My Settings → Language) để tiêu đề DocType hiện "Bảng Công Tháng" / "Công Tác".

---

## Dọn dữ liệu demo (khi cần)
Xoá: 5 nhân viên HR-EMP-00002…00006 + BCT-2026-00002 + CT-2026-00002 + HR-LAP-2026-00001 + các
Attendance/Checkin tháng 9. Chạy lại generator sẽ tự dọn tháng 9 của các NV này trước khi dựng lại.
