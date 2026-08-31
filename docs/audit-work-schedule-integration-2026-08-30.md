# Rà soát tích hợp: lịch làm việc mới ↔ các chức năng cũ

> Ngày 2026-08-30. Đối tượng: `hrms/hr/work_schedule.py`, `Work Calendar Settings`,
> `Work Calendar Day`, `Shift Type.custom_working_days`, cờ ngoài lịch trên `Employee Checkin`.
> Nối tiếp `docs/spec/work-schedule-and-holiday-separation.md` (đã build, Task 1–9 + 11).
>
> **Trạng thái: TÀI LIỆU PHÂN TÍCH — chờ duyệt, chưa sửa gì.**

## Vì sao cần rà

Đợt build vừa rồi đổi **nguồn sự thật** của một khái niệm mà gần như mọi chức năng HR đều hỏi tới:
*"ngày này có phải ngày làm việc không"*. Chín điểm tiêu thụ đã được chuyển sang cửa mới và có test.
Nhưng `Holiday List` là một bảng **dùng chung toàn app**, và còn những nơi khác vẫn đọc thẳng nó.

Hôm nay chúng chưa sai, vì lịch 2026 **vẫn còn nguyên 104 dòng nghỉ cuối tuần**. Chúng sẽ sai đúng
vào lúc patch di trú chạy. Nói cách khác: **rủi ro đang bị hoãn lại chứ không phải không có** — và
đó chính là lý do tài liệu này phải xong trước khi bấm nút di trú.

Phạm vi rà: mọi lời gọi `is_holiday` / `get_holiday_dates_between` / `get_holiday_list_for_employee` /
`get_holidays_for_employee` còn lại trong `hrms/`, đối chiếu với hành vi sau di trú.

## Bản đồ điểm nối

### Đã chuyển sang cửa mới (có test, không phải làm lại)

| Chức năng | Nơi | Hỏi gì |
|---|---|---|
| Chấm vắng tự động | `shift_type.get_dates_for_attendance`, `should_mark_attendance` | `non_working_days_between`, `is_working_day` |
| Phân loại giờ vào/ra | `attendance.falls_on_non_working_day` | `is_working_day` |
| Miễn chấm công | `attendance_exempt` | `is_working_day` |
| Công tác | `business_trip.create_travel_attendance` | `is_working_day` |
| Yêu cầu chấm công | `attendance_request.should_mark_attendance` | `is_working_day` |
| Đơn nghỉ | `leave_application.get_holidays`, `update_attendance` | `non_working_days_between` |
| Bảng công + soát công + Bảng Công Tháng | `monthly_attendance_report.get_day_kinds` | `scheduled_days_map` |
| Phiếu lương | `salary_slip_hook.set_working_days`, `SalarySlip.get_holidays_for_employee` | `scheduled_days_between`, `non_working_days_between` |
| Check-in | `employee_checkin.set_outside_schedule_flag` | `is_working_day`, `shift_window` |

### Vẫn đọc thẳng `Holiday List` — đây là phần phải xử

| # | Nơi | Hôm nay | Sau di trú |
|---|---|---|---|
| A1 | `compensatory_leave_request.validate_holidays` | T7/CN là dòng Holiday → phiếu nghỉ bù hợp lệ | **T7/CN không còn là Holiday → không lập được phiếu nghỉ bù cho cuối tuần** |
| A2 | `api/roster.get_holidays` | lưới roster tô T7/CN | **T7/CN biến mất khỏi lưới, nhìn như ngày làm việc** |
| A3 | `api/get_holidays_for_calendar` | lịch chấm công PWA tô cuối tuần | mất tô cuối tuần |
| A4 | `attendance.add_holidays` (calendar view trên Desk) | có sự kiện cuối tuần | mất sự kiện cuối tuần |
| A5 | `attendance.get_unmarked_days(exclude_holidays=1)` | hộp thoại *Mark Attendance* bỏ qua cuối tuần | **liệt kê T7/CN là "ngày chưa chấm" → HR dễ chấm nhầm** |
| A6 | `upload_attendance` | template Excel đánh dấu cuối tuần | không đánh dấu nữa |
| A7 | `employees_working_on_a_holiday` (report) | thấy người đi làm T7/CN | **chỉ còn thấy người đi làm ngày lễ** — mất đúng công dụng chính |
| A8 | `employee_boarding_controller` | lịch onboarding né cuối tuần | task onboarding rơi vào T7/CN |

### Đã kiểm, KHÔNG ảnh hưởng (ghi lại để khỏi rà lần hai)

| Nơi | Vì sao an toàn |
|---|---|
| `employee_reminders` | đã gọi `only_non_weekly=True` — vốn chỉ lấy ngày lễ |
| `payroll_period.get_payroll_period_days` | site **không có Payroll Period nào**; engine MVL không dùng hàm này |
| `employee_benefit_application` | phúc lợi linh hoạt kiểu Ấn Độ, Miyano không dùng |
| `daily_work_summary_group` | có `holiday_list` riêng trên chính doctype, độc lập |
| `monthly_attendance_sheet` (report tiếng Anh) | không phải bảng công VN; cột `total_holidays` sẽ chỉ đếm lễ — chấp nhận được |
| `sheet_gate` đối soát bảng ↔ phiếu | hai vế nay cùng một nguồn nên không thể lệch vì lịch |

## Bốn khoảng trống về logic, không chỉ về code

### 1. Vòng nghỉ bù vẫn đứt — và đợt này làm nó đứt thêm một nhát

`Compensatory Leave Request` (nghỉ bù do đi làm ngày nghỉ) hiện **chết hai lần**:

- `validate_attendance` đòi có Attendance `Present` đúng những ngày đó — mà auto-attendance không
  bao giờ tạo công cho ngày nghỉ, nên điều kiện không bao giờ thoả;
- `validate_holidays` đòi **mọi ngày trong khoảng** phải là dòng Holiday — sau di trú, thứ Bảy không
  còn là dòng Holiday, nên ngay cả khi có Attendance thì phiếu vẫn bị chặn.

Thực trạng khớp: **0 phiếu** trên site, và quỹ `Nghỉ bù` đang được cấp bằng một Leave Allocation tay
10 ngày, không liên hệ gì với ngày đã làm thêm. Đây là khoảng trống đã nêu ở phân tích 2026-08-28
(mục G2/G3) và nay có thêm dữ kiện: phần chặn thứ hai chính là thứ đợt này tạo ra.

**Hai hướng, cần anh chọn:** (a) Miyano-hoá `Compensatory Leave Request` để nó hỏi lịch tuần
(`is_rest_day` thay cho "là dòng Holiday") và chấp nhận nguồn công khác ngoài Attendance — mở lại
vòng nghỉ bù ngay đợt này; hoặc (b) khoá hẳn doctype này lại (ẩn khỏi menu) và để vòng nghỉ bù cho
spec OT, tránh dựng nửa vời.

### 2. Ba cửa vẫn ghi được công vào ngày ngoài lịch

Đường tự động đã kín, nhưng ghi tay thì chưa:

- `Attendance.validate` **không chặn, không cảnh báo** khi tạo công vào ngày ngoài lịch tuần;
- `Employee Attendance Tool` (chấm hàng loạt) chưa bao giờ xét ngày nghỉ;
- hộp thoại *Mark Attendance* trên list Attendance sẽ **chủ động gợi ý** T7/CN sau di trú (A5).

Hệ quả: một ngày công lọt vào thứ Bảy sẽ **cộng thẳng vào `payment_days`** (vì `set_working_days`
đếm ngày theo lịch tuần, còn `absent_days`/`lwp` đọc Attendance) — nhưng bảng công lại hiện `-` cho
ngày đó. Bảng và phiếu lệch nhau mà không ai báo. Đây là lỗ hổng **nghiêm trọng nhất** trong danh
sách này, vì nó đụng tiền và im lặng.

Đề xuất: `Attendance.before_validate` cảnh báo (không chặn) khi ngày nằm ngoài lịch tuần, **trừ khi**
ca có `mark_auto_attendance_on_holidays` hoặc ngày đó là `Làm bù`; và bảng công hiện mã công thay vì
`-` khi ngày ngoài lịch **có** bản ghi, để hai bên không bao giờ nói khác nhau.

### 3. Hai cái nhãn nay nói sai

- `Attendance Request.include_holidays` — nhãn *"Include Holidays"*, nay ngữ nghĩa thật là *"gồm cả
  ngày nghỉ cuối tuần"*.
- `Shift Type.mark_auto_attendance_on_holidays` — tương tự, nay là *"chấm công cả ngày ngoài lịch"*.

Nhãn sai làm người dùng tick sai; và tick sai ở hai chỗ này đều dẫn tới ngày công thừa.

### 4. Chốt chặn kỳ đã khoá của Work Calendar Settings còn yếu

`validate_period_not_locked` tôi viết đang lấy **một nhân viên Active bất kỳ** rồi hỏi
`locking_sheet`. Mà `locking_sheet` khoá theo **phòng ban** của chính nhân viên đó — nên nếu Bảng
Công Tháng đã chốt chỉ thuộc một phòng ban khác, sửa lịch vẫn lọt. Phải hỏi thẳng `Monthly Attendance
Sheet` đã submit phủ ngày, không đi vòng qua một nhân viên đại diện.

## Bộ dữ liệu test dựng từ chính logic

Hiện mỗi bộ test tự dựng dữ liệu riêng, nên không có chỗ nào chứng minh **các mảnh ăn khớp với
nhau**. Đề xuất một module dựng cảnh dùng chung, `hrms/tests/work_calendar_fixture.py`, sinh ra một
năm 2027 đầy đủ và tất định:

**Ba ca** — để phủ cả ba nhánh của chuỗi phân giải:

| Ca | Lịch tuần | Dùng để chứng minh |
|---|---|---|
| Hành chính | T2–T6 | đường chính |
| Sáu ngày | T2–T7 | ca thắng lịch mặc định công ty |
| Bảy ngày | cả tuần | test độc lập với lịch |

**Năm nhân viên** — A ca hành chính; B ca sáu ngày; C **không phân ca** (rơi về mặc định công ty);
D miễn chấm công; E vào làm giữa tháng và nghỉ việc giữa tháng khác.

**Lịch 2027** — lễ dương tự sinh; Tết âm khai tay; một lễ riêng công ty rơi thứ Tư; một lễ rơi Chủ
nhật (sinh nghỉ bù); **một cặp nghỉ ghép + làm bù cùng tháng** (mẫu số không đổi) và **một cặp khác
tháng** (mẫu số hai tháng đổi ngược chiều — đúng cái bẫy đã cảnh báo trong spec §3b).

**Sự kiện** — check-in trong ca / ngoài giờ / ngày nghỉ / ngày làm bù; đơn nghỉ bắc qua cuối tuần,
nửa ngày, trùng lễ, trùng ngày làm bù; một chuyến công tác vắt qua cuối tuần; một yêu cầu chấm công
vào ngày nghỉ; một phiếu lương cho mỗi nhân viên.

Mỗi khẳng định chạy **hai lượt**: lịch còn dòng cuối tuần và lịch đã gỡ. Đó là bất biến trung tâm của
cả đợt, và nó phải đúng trên một cảnh phức tạp chứ không chỉ trên các ca đơn lẻ.

## Ma trận test case đề xuất

| Nhóm | Số ca | Nội dung chính |
|---|---|---|
| Phân giải lịch | 8 | 3 tầng + lỗi cấu hình; ca đổi giữa kỳ; ngoại lệ làm bù; lễ trên ngày nghỉ bị bỏ |
| Chấm công | 10 | không V vào ngày nghỉ; V vào ngày làm bù; miễn chấm công; công tác vắt cuối tuần; yêu cầu chấm công |
| Đơn nghỉ | 6 | bắc cuối tuần; trùng lễ; trùng ngày làm bù; nửa ngày; đơn toàn ngày nghỉ bị chặn |
| Check-in | 6 | 4 ca gắn cờ + cờ trơ + ngày làm bù |
| Bảng công | 6 | `-` / `NL` / mã công ngày làm bù; cột tổng; màu; khớp lưới soát công |
| Lương | 10 | 8 ca biên đang có + ngày làm bù vào mẫu số + cặp nghỉ ghép khác tháng |
| Tích hợp cũ | 8 | 8 điểm A1–A8 sau khi sửa |
| Ghi tay | 4 | cảnh báo công ngoài lịch; bảng ↔ phiếu không lệch |
| **Tổng mới** | **~58** | cộng vào 406 test đang xanh |

## Việc đề xuất, theo thứ tự

| # | Việc | Rủi ro |
|---|---|---|
| 1 | Bộ dựng cảnh `work_calendar_fixture.py` + ma trận test trên cảnh đó | thấp — chỉ thêm test |
| 2 | Sửa A2–A6, A8 sang cửa mới (roster, PWA, calendar, unmarked days, upload, onboarding) | thấp — hiển thị/tiện ích |
| 3 | A7 `employees_working_on_a_holiday`: mở rộng thành "đi làm ngày ngoài lịch" | thấp |
| 4 | Khoảng trống 2: cảnh báo công ngoài lịch + bảng công hiện mã công cho ngày đó | **đụng bảng công ↔ phiếu lương → cổng bất biến** |
| 5 | Khoảng trống 4: siết chốt kỳ đã khoá của Work Calendar Settings | thấp |
| 6 | Khoảng trống 3: đổi nhãn hai field (+ bản dịch) | thấp |
| 7 | A1 nghỉ bù — theo hướng anh chọn (a) hoặc (b) | (a) trung bình, (b) thấp |
| 8 | Chạy lại toàn bộ + đối soát 6 phiếu thật, rồi mới bàn tiếp việc chạy patch di trú | — |

## Ba câu cần anh chốt

1. **Nghỉ bù (A1)** — Miyano-hoá `Compensatory Leave Request` để mở lại vòng nghỉ bù ngay đợt này,
   hay khoá doctype đó lại và để cho spec OT?
2. **Công ghi tay vào ngày ngoài lịch** — **cảnh báo** (đề xuất) hay **chặn hẳn**? Chặn thì an toàn
   hơn cho lương nhưng HR mất đường xử lý ngoại lệ khi chưa có OT.
3. **Roster / PWA** — có cần tô lại ngày nghỉ cuối tuần không, hay chấp nhận hai màn đó chỉ hiện ngày
   lễ? (Tô lại thì phải thêm một endpoint đọc lịch tuần, không chỉ đổi truy vấn.)

> Chưa động vào code cho tới khi anh duyệt tài liệu này. Patch di trú vẫn **chưa** nối vào
> `patches.txt`, site vẫn nguyên 104 dòng nghỉ cuối tuần — nên chưa có gì trong danh sách A đang sai
> ở thời điểm này.
