# Spec: Hoàn thiện tích hợp lịch làm việc với các chức năng cũ

> Status: **ĐÃ BUILD (2026-08-30)** — cả 8 task xong, 442 test xanh, 6 phiếu lương thật 0 lệch.
> Chốt 2026-08-30 từ
> `docs/audit-work-schedule-integration-2026-08-30.md`. Nối tiếp
> `docs/spec/work-schedule-and-holiday-separation.md` (đã build, Task 1–9 + 11).

## Objective

Đợt trước đổi nguồn sự thật của *"ngày này có phải ngày làm việc không"* và chuyển 9 điểm tiêu thụ
sang cửa mới. Rà soát phát hiện **6 điểm còn đọc thẳng `Holiday List`** và **3 khoảng trống logic**.

Hôm nay chúng chưa sai, vì lịch 2026 vẫn còn nguyên 104 dòng nghỉ cuối tuần. Chúng sẽ sai **đúng vào
lúc patch di trú chạy**. Đợt này đóng hết những điểm đó lại, để việc di trú không còn là một bước
nhảy vào chỗ tối.

**Success:**

1. Không còn nơi nào ngoài `work_schedule.py` hỏi lịch qua `Holiday List` — trừ những nơi đã ghi rõ
   là ngoài phạm vi.
2. Ghi tay một ngày công vào ngày ngoài lịch **không làm bảng công và phiếu lương lệch nhau**.
3. Một bộ dựng cảnh test dùng chung chứng minh các mảnh ăn khớp, không chỉ từng mảnh đúng riêng.
4. Toàn bộ test xanh ở **cả hai** trạng thái lịch; 6 phiếu lương thật vẫn 0 lệch.

## Locked decisions (2026-08-30)

1. **Nghỉ bù: HOÃN.** `Compensatory Leave Request` không sửa đợt này. Nó đang bất khả dụng vì hai
   lý do độc lập (đòi Attendance `Present` trên ngày mà auto-attendance không tạo; đòi mọi ngày là
   dòng Holiday). Ghi rõ vào docstring của doctype để người sau không mất công dò lại; vòng nghỉ bù
   thuộc spec OT.
2. **CHO PHÉP ghi tay công vào ngày ngoài lịch.** Không chặn, không cảnh báo trên `Attendance`.
3. **Ngày ngoài lịch tuần chỉ HIỂN THỊ ký hiệu, không vào bất kỳ cột tổng nào** — hệ quả bắt buộc
   của quyết định 2, xem §1.
4. **Roster: NGOÀI PHẠM VI** — không dùng nữa (người dùng chốt 2026-08-30). Không sửa
   `api/roster.py`, không sửa `roster/`.
5. **PWA vẫn trong phạm vi** — lịch chấm công và *Upcoming Holidays* phải đúng.
6. Đổi hai nhãn field nay nói sai nghĩa (§3).
7. Chốt chặn kỳ đã khoá hỏi thẳng `Monthly Attendance Sheet`, không đi vòng qua một nhân viên đại
   diện (§4).

## Bối cảnh kỹ thuật (đã kiểm chứng, không giả định)

- **`if att:` chạy TRƯỚC nhánh lịch** trong `get_sheet_rows`
  ([monthly_attendance_report.py:479-506](../../hrms/hr/report/monthly_attendance_report/monthly_attendance_report.py#L479-L506)).
  Nghĩa là ngày ngoài lịch **có** bản ghi ĐÃ hiện mã công thay vì `-`. Phần hiển thị không hỏng —
  chỉ phần cộng tổng mới hỏng.
- **`reconcile_with_sheet` so `Tổng công` của bảng đã chốt với `payment_days` của phiếu**
  ([sheet_gate.py:99-126](../../hrms/vn_payroll/sheet_gate.py#L99-L126)), lệch quá `TOLERANCE` thì
  **throw**. Một ngày `X` ghi tay vào thứ Bảy cộng +1 vào Tổng công nhưng `set_working_days` giữ mẫu
  số ở 23 → **chặn sạch mọi phiếu lương của tháng đó**. Đây là defect cụ thể mà quyết định 2 mở ra.
- **Payroll đã an toàn sẵn ở chiều ngược lại**: `calculate_lwp_ppl_and_absent_days_based_on_attendance`
  bỏ qua `Absent` / `Half Day` / nghỉ không lương rơi vào ngày trong tập `holidays`, mà
  `SalarySlip.get_holidays_for_employee` nay trả *ngày không phải đi làm*. Nên một dòng `V` ghi nhầm
  vào Chủ nhật **không** trừ lương. Không cần làm gì thêm cho chiều này.
- **`employee_reminders` an toàn** — đã gọi `only_non_weekly=True`.
- **`payroll_period.get_payroll_period_days` không chạy trên site** — không có `Payroll Period` nào,
  và engine MVL không gọi hàm này.
- Site: **0 `Compensatory Leave Request`**, quỹ `Nghỉ bù` cấp bằng Leave Allocation tay 10 ngày.

## Thiết kế

### 1. Ngày ngoài lịch có bản ghi: hiện ký hiệu, không cộng tổng

Quy tắc, một câu: **`is_rest_day` → chỉ hiển thị, không vào cột tổng nào.**

| Tình huống | Ô hiện | Cột tổng |
|---|---|---|
| `X` ghi tay vào thứ Bảy | `X` | **không cộng** vào Công / Tổng công |
| `V` ghi nhầm vào Chủ nhật | `V` | **không cộng** vào Vắng |
| `X` vào ngày lễ (17/07) | `X` | cộng bình thường — ngày lễ **nằm trong** lịch tuần |
| `X` vào ngày `Làm bù` | `X` | cộng bình thường — làm bù **là** ngày làm việc |

Vì sao không cộng: chưa có chính sách trả công ngày nghỉ (`docs/spec/overtime-registration.md` chốt
"hiện không tính tăng ca"). Cộng vào Tổng công là **hứa trả tiền** cho một ngày mà phiếu lương không
trả — hai bên lệch nhau và cổng đối soát chặn. Không cộng thì bảng công nói đúng thực tế hôm nay:
*ngày đó có đi làm, và chưa được tính công*. Khi OT ra đời, chính nó sẽ trả cho những ngày này, và
`custom_outside_schedule` đã tích sẵn dữ liệu.

Chú giải màu của bảng công thêm một dòng: ô mã công trên nền *"nghỉ tuần"* = đi làm ngoài lịch, ghi
nhận nhưng chưa tính công.

> **Đây là điểm duy nhất của spec này đụng tới con số của bảng công**, nên nó đi kèm cổng đối soát:
> dựng một tháng có ngày công ghi tay vào thứ Bảy, chứng minh `reconcile_with_sheet` **không** chặn.

### 2. Sáu điểm còn lại chuyển sang cửa mới

| Nơi | Đổi thành |
|---|---|
| `api/__init__.get_holidays_for_calendar` | ngày không làm việc từ `non_working_days_between` |
| `api/__init__.get_holidays_for_employee` (Upcoming Holidays) | chỉ ngày lễ — **giữ nguyên ngữ nghĩa**, nhưng đọc qua `holiday_list_for` để đúng lịch theo năm |
| `attendance.add_holidays` (calendar trên Desk) | `non_working_days_between`, nhãn `Ngày nghỉ` / `Nghỉ lễ` |
| `attendance.get_unmarked_days(exclude_holidays)` | `non_working_days_between` — hộp thoại *Mark Attendance* thôi gợi ý T7/CN |
| `upload_attendance` | `non_working_days_between` cho cột đánh dấu của template |
| `employees_working_on_a_holiday` (report) | mở rộng thành **"đi làm ngày ngoài lịch"**: quét ngày nghỉ tuần **và** ngày lễ, thêm cột *Loại ngày*. Đây chính là báo cáo trả lời "ai đang đi làm cuối tuần" — sau di trú nếu chỉ quét lễ thì nó mất đúng công dụng chính. |
| `employee_boarding_controller` | `is_working_day` khi rải lịch task onboarding |

`api/roster.py` **không đụng** (quyết định 4).

### 3. Hai nhãn nói sai

| Field | Nhãn cũ | Nhãn mới |
|---|---|---|
| `Attendance Request.include_holidays` | *Include Holidays* | *Gồm cả ngày nghỉ (cuối tuần + lễ)* |
| `Shift Type.mark_auto_attendance_on_holidays` | *Mark Auto Attendance on Holidays* | *Chấm công tự động cả ngày ngoài lịch* |

Cả hai đều là cờ mà tick sai sẽ sinh ngày công thừa, nên nhãn phải nói đúng thứ nó làm. Nhãn tiếng
Việt đi qua `hrms/translations/vi.csv` theo quy ước repo; `include_holidays` là field của doctype
hrms nên sửa thẳng JSON, `mark_auto_attendance_on_holidays` cũng vậy.

### 4. Chốt chặn kỳ đã khoá

`WorkCalendarSettings.validate_period_not_locked` đang lấy **một nhân viên Active bất kỳ** rồi hỏi
`period_lock.locking_sheet`. Mà `locking_sheet` khoá theo **phòng ban** của chính nhân viên đó — nếu
bảng đã chốt thuộc phòng ban khác thì sửa lịch vẫn lọt.

Đổi thành: hỏi thẳng có `Monthly Attendance Sheet` nào `docstatus = 1` phủ ngày bị sửa hay không,
không cần biết nhân viên nào. Lịch là chính sách **toàn công ty**, nên đúng câu hỏi phải là "có kỳ
nào đã chốt phủ ngày này không", chứ không phải "kỳ của người này đã chốt chưa".

### 5. Bộ dựng cảnh test dùng chung

`hrms/tests/work_calendar_fixture.py` — dựng một năm 2027 tất định, dùng lại được cho mọi bộ test.

**Ba ca** (phủ cả ba tầng của chuỗi phân giải): Hành chính T2–T6 · Sáu ngày T2–T7 · Bảy ngày cả tuần.

**Năm nhân viên**: A ca hành chính · B ca sáu ngày · C **không phân ca** (rơi về mặc định công ty) ·
D miễn chấm công · E vào làm giữa tháng, nghỉ việc ở tháng khác.

**Lịch 2027**: lễ dương tự sinh · Tết âm khai tay · một lễ riêng công ty rơi giữa tuần · một lễ rơi
thứ Bảy (sinh nghỉ bù) · **một cặp nghỉ ghép + làm bù cùng tháng** · **một cặp khác tháng**.

Bộ dựng cảnh **chỉ dựng dữ liệu, không assert**. Mọi bộ test gọi nó rồi tự khẳng định phần của mình.

## Tech Stack

Frappe/ERPNext HRMS v15, Python, Vue (PWA — chỉ đọc endpoint đã sửa, không đổi component), fixtures
JSON, `hrms/translations/vi.csv`. Test qua **rollback harness** — KHÔNG `bench run-tests` trên
`miyano`.

## Project structure (files)

```
hrms/tests/work_calendar_fixture.py                    (MỚI — bộ dựng cảnh dùng chung)
hrms/tests/test_work_calendar_integration.py           (MỚI — ma trận tích hợp trên cảnh đó)
hrms/hr/report/monthly_attendance_report/monthly_attendance_report.py  (sửa — §1)
hrms/api/__init__.py                                   (sửa — 2 endpoint lịch của PWA)
hrms/hr/doctype/attendance/attendance.py               (sửa — add_holidays, get_unmarked_days)
hrms/hr/doctype/upload_attendance/upload_attendance.py (sửa)
hrms/hr/report/employees_working_on_a_holiday/         (sửa — mở rộng thành "ngoài lịch")
hrms/controllers/employee_boarding_controller.py       (sửa)
hrms/hr/doctype/attendance_request/attendance_request.json  (sửa — nhãn)
hrms/hr/doctype/shift_type/shift_type.json             (sửa — nhãn)
hrms/translations/vi.csv                               (sửa — 2 nhãn)
hrms/hr/doctype/work_calendar_settings/work_calendar_settings.py  (sửa — §4)
hrms/hr/doctype/compensatory_leave_request/compensatory_leave_request.py  (sửa — chỉ docstring)
```

## Testing strategy (rollback harness)

- **Cổng bảng ↔ phiếu (chặn):** tháng có ngày công ghi tay vào thứ Bảy → `Tổng công` = `payment_days`
  → `reconcile_with_sheet` không chặn. Chạy ở **cả hai** trạng thái lịch.
- **Cổng bất biến lương** hiện có phải vẫn xanh, và 6 phiếu thật vẫn 0 lệch.
- Ma trận trên bộ dựng cảnh: ~58 ca theo 8 nhóm của tài liệu rà soát (phân giải · chấm công · đơn
  nghỉ · check-in · bảng công · lương · tích hợp cũ · ghi tay).
- Mỗi endpoint/report đã sửa có một test đọc đúng ngày nghỉ tuần **sau** khi mô phỏng di trú.
- Kiểm tiêu chí "một cửa" bằng grep, danh sách ngoại lệ phải khớp đúng §2 + quyết định 4.

## Boundaries

- **Always:** mọi câu hỏi về lịch đi qua `work_schedule`; ngày ngoài lịch không vào cột tổng; cổng
  bất biến lương xanh trước mọi thay đổi chạm số; stage đúng file của task; test qua harness.
- **Ask first (STOP):** bất kỳ thay đổi nào làm đổi `payment_days` / `Tổng công` ngoài §1; chạy patch
  di trú; deploy fixtures lên site.
- **Never:** sửa `api/roster.py` hay `roster/` (ngoài phạm vi); build vòng nghỉ bù; tính tiền OT;
  nới lỏng cổng đối soát để "cho xanh".

## Success Criteria

- [x] Ngày ngoài lịch có bản ghi: hiện ký hiệu, không vào cột tổng; `reconcile_with_sheet` không
      chặn — có test ở cả hai trạng thái lịch.
- [x] 6 điểm ở §2 đọc lịch qua cửa mới; grep "một cửa" chỉ còn đúng danh sách ngoại lệ đã ghi.
- [x] `employees_working_on_a_holiday` trả lời được "ai đi làm cuối tuần".
- [x] Hai nhãn nói đúng nghĩa, có bản dịch.
- [x] Chốt kỳ đã khoá hỏi thẳng `Monthly Attendance Sheet`, có test cho ca khác phòng ban.
- [x] `work_calendar_fixture.py` dựng đủ 3 ca / 5 nhân viên / lịch 2027 có cả hai cặp nghỉ ghép–làm bù.
- [x] Ma trận tích hợp xanh; cổng bất biến lương xanh; 6 phiếu thật 0 lệch.
- [x] `Compensatory Leave Request` có docstring nói rõ vì sao bất khả dụng và nó thuộc spec nào.

## Phát hiện thêm khi build (2026-08-30)

- **Điểm thứ 7 bỏ sót ở lần rà:** `leave_application.add_holidays` — calendar của **Đơn nghỉ** cũng
  đọc thẳng dòng `Holiday`, nên sau di trú người xin nghỉ không thấy cuối tuần trên lịch và dễ chọn
  nhầm khoảng nghỉ. Đã sửa cùng cách với calendar của Attendance.
- **Hai chỗ code chết** lộ ra khi kiểm tiêu chí "một cửa": import
  `get_holiday_list_for_employee` ở `hrms/api/__init__.py`, và hàm
  `hrms/utils/holiday_list.get_holiday_dates_between` không còn ai gọi. Đã gỡ — để lại thì lời hứa
  "mọi câu hỏi về lịch đi qua một cửa" thành sai.
- **Bộ dựng cảnh bắt được một khẳng định sai của spec trước** ngay lần chạy đầu — xem §6.

## Out of scope

- **Vòng nghỉ bù** (`Compensatory Leave Request`) — hoãn, thuộc spec OT.
- **Roster** (`api/roster.py`, `roster/`) — không dùng nữa.
- **Tính tiền OT** — `docs/spec/overtime-registration.md`.
- **Chạy patch di trú** — vẫn chờ ký duyệt riêng, không thuộc đợt này.
- `monthly_attendance_sheet` (report tiếng Anh của upstream), `employee_benefit_application`,
  `payroll_period`, `daily_work_summary_group` — đã kiểm, không ảnh hưởng.

### 6. Nghỉ ghép hiện KHÔNG phải là "đổi ngày" — bộ dựng cảnh vừa chứng minh

Spec trước (§3b) viết rằng nghỉ ghép + làm bù cùng tháng thì mẫu số không đổi. **Khẳng định đó sai**,
và test của bộ dựng cảnh bắt được ngay ở lần chạy đầu.

Lý do: ngày nghỉ ghép được khai loại `Nghỉ lễ`, tức **ngày có lương**, nên nó **vẫn nằm trong mẫu
số** (đúng quy ước "ngày công chuẩn = ngày đi làm + nghỉ lễ + nghỉ có lương"). Ngày làm bù thì cộng
thêm một. Kết quả: **một cặp nghỉ ghép + làm bù làm mẫu số +1, không phải 0.**

Số học tháng 8/2027: 22 ngày T2–T6 → 21 ngày đi làm + 1 ngày lễ (nghỉ ghép) + 1 ngày làm bù = **23**.

Mô hình tự nó nhất quán. Nhưng nếu HR hiểu nghỉ ghép là **đổi ngày** (nghỉ thứ Sáu, làm bù thứ Bảy,
net 0) thì mô hình hiện tại **chưa diễn đạt được** — sẽ cần một loại thứ ba, ví dụ *"Nghỉ không tính
công"*, gỡ hẳn ngày đó khỏi lịch thay vì biến nó thành lễ. Xem Open Questions.

Đợt này **không** thêm loại thứ ba; chỉ ghi nhận hành vi đúng bằng test và đặt câu hỏi.

## Open Questions

1. **Nghỉ ghép: "ngày lễ" hay "đổi ngày"?** Hiện là ngày lễ có lương, nên một cặp nghỉ ghép + làm
   bù làm mẫu số **+1** (xem §6). Nếu Miyano hiểu là đổi ngày net 0 thì cần thêm loại *"Nghỉ không
   tính công"* — một task riêng, không nằm trong 8 task của plan này.
2. **Ngày ngoài lịch có nên hiện màu khác** với ngày nghỉ không có bản ghi? Đề xuất: giữ nền "nghỉ
   tuần" nhưng chữ đậm, thêm một dòng chú giải — để HR thấy ngay ai đi làm cuối tuần mà không phải
   mở report riêng.
