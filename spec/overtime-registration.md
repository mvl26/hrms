# Spec: Ghi nhận giờ làm thêm (OT) theo đăng ký

> Status: **APPROVED (2026-07-22).** Phạm vi **cố ý mỏng** — chốt với người dùng: "phần tính OT thì
> chỉ cần có thôi, không cần làm sâu". Không tính tiền lương OT trong đợt này.

## Mục tiêu

Ghi nhận và báo cáo số giờ làm thêm **đã đăng ký và đã thực làm**, tách hẳn khỏi Attendance để
payroll không thể bị ảnh hưởng.

## Vấn đề

`working_hours` trên Attendance bị bộ phân loại nửa ngày VN tính lại thành *giờ thực trong khung ca
đã trừ nghỉ trưa*, tối đa 8h (`hrms/hr/doctype/attendance/attendance.py`). Nên một ngày chấm
08:07 → 20:30 vẫn ghi 7.9h: **giờ ngoài ca bị cắt, OT vô hình.** Hiện OT chỉ còn dấu vết ở
Employee Checkin và `out_time`.

## Quyết định đã chốt

1. **Mục đích: chỉ ghi nhận + báo cáo.** Không vào lương. (Hệ số 150/200/300%, phụ cấp ca đêm,
   đổi OT sang quỹ nghỉ bù `NB` — đều ngoài phạm vi.)
2. **OT phải đăng ký trước.** Không phải cứ ở lại ngoài giờ hành chính là tăng ca. Đúng tinh thần
   Điều 107 BLLĐ (làm thêm phải có sự đồng ý). Không có phiếu duyệt → không có OT.
3. **Phiếu đăng ký: nhiều người + khoảng ngày, duyệt bằng Frappe Workflow**, dựng theo khuôn
   "Cong Tac Approval" đã chạy tốt.
4. **Số giờ = giao của đăng ký và thực tế, không vượt đăng ký.**
5. **Sổ OT riêng — không đụng Attendance.** Đây là bảo đảm kiến trúc: payroll không thể lệch vì
   không có dòng nào của nó bị ghi.
6. **Trần luật: cảnh báo khi duyệt, không chặn.**

## Mô hình dữ liệu

### `Overtime Request` — Phiếu đăng ký làm thêm giờ (`is_submittable = 1`)

| field | type | ghi chú |
|---|---|---|
| `naming_series` | Select | `OT-.YYYY.-.#####` |
| `company` | Link Company | reqd |
| `department` | Link Department | optional |
| `reason` | Small Text | reqd — lý do làm thêm |
| `from_date` / `to_date` | Date | reqd |
| `planned_start_time` / `planned_end_time` | Time | reqd — khung giờ áp cho mọi ngày trong phiếu |
| `registered_by` | Link Employee | người lập |
| `approver` | Link User | người duyệt |
| `workflow_state` | Link Workflow State | read-only |
| `employees` | Table → `Overtime Request Employee` | người tham gia |
| `amended_from` | Link | bắt buộc cho submittable |

**`Overtime Request Employee`** (`istable = 1`): `employee`, `employee_name`,
`start_time` / `end_time` (bỏ trống = theo phiếu).

Khung giờ khác nhau theo từng ngày → lập phiếu khác. Cố ý **không** làm lịch OT phức tạp.

### `Overtime Entry` — Sổ giờ làm thêm (`is_submittable = 1`, 1 dòng / người / ngày)

`employee`, `date`, `overtime_request` (Link), `planned_from`, `planned_to`, `actual_in`,
`actual_out`, `hours` (Float), `day_type` (Select), `attendance` (Link, read-only).

`day_type` ∈ **Ngày thường / Ngày nghỉ tuần / Ngày lễ**, suy từ Holiday List của nhân viên.
Chưa dùng đến, nhưng đây là thứ quyết định hệ số 150/200/300% nếu sau này tính tiền — ghi sẵn
để khỏi phải dựng lại lịch sử.

## Quy tắc tính

```
hours = độ dài( [khoảng đăng ký] ∩ [khoảng có mặt thực tế] ) − phần rơi vào nghỉ trưa
```

- Giờ thực tế lấy từ `Attendance.in_time/out_time`; không có thì ghép cặp IN/OUT của
  Employee Checkin trong ngày.
- **Không vượt khoảng đã đăng ký** — chấm ra muộn hơn đăng ký cũng chỉ tính tới giờ đã duyệt.
- Trừ nghỉ trưa chỉ khi khoảng đăng ký chồng lên `custom_lunch_start`..`custom_lunch_end` của
  Shift Type (xảy ra với OT cả ngày Chủ nhật).
- Không có mặt → `hours = 0`, entry **vẫn** được tạo và chốt, để giữ dấu vết "có đăng ký mà không làm".

## Vòng đời

1. Phiếu được duyệt (workflow đến trạng thái duyệt cuối) → sinh `Overtime Entry` **nháp**, một
   dòng cho mỗi (nhân viên × ngày) trong phiếu.
2. Job chạy hằng ngày đối chiếu các entry nháp của **ngày đã qua**: đọc chấm công thực tế, tính
   `hours`, rồi **submit** để đóng băng.
3. Chạy lại thủ công cho một khoảng ngày bằng `bench execute` khi cần sửa muộn.
4. Huỷ phiếu → huỷ các entry của phiếu đó.

## Báo cáo & hiển thị

- **Report "Làm thêm giờ"**: lọc theo công ty / bộ phận / nhân viên / khoảng ngày. Cột: nhân viên,
  tổng OT, tách theo 3 loại ngày, luỹ kế tháng, luỹ kế năm.
- **Bảng Công Tháng**: thêm cột `overtime_hours` vào dòng chi tiết, **đọc** từ sổ OT lúc
  `populate_from_attendance`. Bảng vẫn là ảnh chụp chỉ đọc, không ghi ngược.

## Trần luật định

Lúc duyệt phiếu: cộng *(entry đã chốt + giờ đăng ký của phiếu này)* rồi `msgprint` cảnh báo nếu vượt
**40h/tháng**, **200h/năm**, hoặc **12h/ngày** (giờ chính + OT). Chỉ cảnh báo kèm số liệu, **không chặn** —
thực tế có ngành được 300h/năm nên chặn cứng dễ gây tắc.

## Kiểm thử

Chạy qua harness rollback trên `miyano` — **không bao giờ** `bench run-tests` trên site này.

- Unit quy tắc giao khoảng: về sớm; ở lại quá đăng ký; vắng mặt hoàn toàn; OT xuyên trưa;
  OT ngày lễ / ngày nghỉ tuần; phiếu có override giờ theo từng người.
- **Payroll gate**: chạy `hrms/payroll_gate.py` trước/sau khi sinh sổ OT → `payment_days`,
  `absent_days`, LWP không đổi.
- Một test khẳng định sinh `Overtime Entry` **không sửa dòng Attendance nào** (so sánh ảnh chụp
  bảng Attendance trước/sau).
- Workflow: các bước duyệt + phân quyền, theo khuôn `test_business_trip.py`.

## Cố ý không làm

Tiền lương OT và hệ số 150/200/300%; phụ cấp ca đêm +30%; tự động đổi OT thành quỹ nghỉ bù (`NB`);
khung giờ OT khác nhau theo từng ngày trong một phiếu; OT qua nửa đêm.

## Điểm còn treo (cần HR xác nhận trước khi build)

1. **Người duyệt OT**: dùng lại vai `COO` (đã có từ luồng Công Tác) hay trưởng bộ phận?
2. **Ca qua nửa đêm**: OT tới 23:00 thì ổn; nếu Miyano có OT vượt 00:00 thì cần thiết kế thêm.
