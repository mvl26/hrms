# Spec: Tách lịch làm việc khỏi lịch nghỉ lễ

> Status: **DRAFT for approval (Phase 1 / SPECIFY).** Chốt trong phiên brainstorm 2026-08-28.
> Nối tiếp `docs/spec/vn-holiday-and-symbol-standardization.md` (đợt trước dựng Holiday List VN) và
> mở đường cho `docs/spec/overtime-registration.md` (đã duyệt 2026-07-22, chưa build).
> **Không plan/implement tới khi được duyệt.**

## Objective

Hôm nay **"cuối tuần" và "ngày nghỉ lễ" là cùng một thứ trong dữ liệu**: cả hai đều là dòng trong
`Holiday List`, phân biệt bằng đúng một cờ `weekly_off`. Hệ quả là không nơi nào trong hệ thống trả
lời được câu hỏi *"ngày này có phải ngày làm việc không"* mà không đi vòng qua bảng ngày nghỉ lễ, và
khái niệm **"trong ca / ngoài ca"** — nền tảng bắt buộc của tính năng OT sắp làm — không tồn tại.

Spec này tách hẳn hai khái niệm:

- **Lịch làm việc** (ngày nào trong tuần đi làm + khung giờ hành chính) → khai trên **`Shift Type`**.
- **Ngày nghỉ lễ** → khai trên **`Work Calendar Settings`**, sinh tự động xuống **`Holiday List`**,
  và Holiday List từ nay **chỉ chứa ngày lễ**.
- **Ngoại lệ của lịch tuần** (nghỉ ghép, ngày làm bù) → khai chung một bảng ở Work Calendar Settings.
- **Ngoài lịch làm việc** (T7/CN, hoặc ngoài giờ hành chính) → *suy ra*, không lưu, không sinh công.
  Log chấm công rơi vào đó được **giữ và đánh dấu** — đó chính là nguyên liệu OT sau này đọc.

**Success (đợt này):**

1. `Holiday List` không còn dòng `weekly_off` nào; ngày nghỉ cuối tuần đến từ `Shift Type`.
2. Mọi con số lương (`total_working_days` / `payment_days` / `absent_days` / LWP) **giống hệt**
   trước và sau — chứng minh bằng cổng bất biến, không phải bằng niềm tin.
3. Số ngày phép của một đơn nghỉ bắc qua cuối tuần **không đổi**.
4. Không một mã `V` nào rơi vào thứ Bảy/Chủ nhật sau khi gỡ dòng cuối tuần.
5. Bảng công vẫn hiện `-` (ngoài lịch tuần) và `NL` (nghỉ lễ) như hôm nay, nhưng lấy từ hai nguồn
   khác nhau thay vì một cờ.
6. Check-in ngoài lịch làm việc được đánh dấu sẵn, để OT không phải backfill.

## Locked decisions (2026-08-28)

1. **Tách thật, không tách hình thức.** Gỡ hẳn dòng cuối tuần khỏi `Holiday List` và tự tính ngày
   công, chấp nhận phải override công thức của ERPNext. (Phương án nhẹ hơn — vẫn biên dịch cuối tuần
   xuống Holiday List cho ERPNext đọc — đã cân nhắc và **bị loại**.)
2. **Lịch tuần + giờ hành chính khai trên `Shift Type`.** Nơi này đã giữ `start_time`/`end_time`/giờ
   nghỉ trưa/biên trượt, và mỗi nhân viên đã có `default_shift` + `Shift Assignment` theo tháng.
3. **`Holiday List` = chỉ ngày lễ, mỗi năm một list riêng** (`VN Miyano 2026`, `VN Miyano 2027`, …).
   Không gộp thành một list trải nhiều năm.
4. **Mọi ngày lễ khai ở `Work Calendar Settings`** rồi sinh tự động xuống Holiday List — kể cả ngày
   nghỉ riêng của công ty. Không còn đường nhập tay thẳng vào Holiday List.
5. **Check-in ngoài lịch làm việc: giữ log, đánh dấu, không sinh công.** Cờ đánh dấu là **trơ** —
   không nhánh nào của đường sinh công đọc tới nó.
6. **Sinh lại toàn bộ lịch 2026** (không chỉ áp từ 2027). Là data migration → **cổng ký duyệt**.
7. **Gỡ ghim `Employee.holiday_list`** để mỗi năm chỉ còn một chỗ phải trỏ lại (Company default).
8. **Ngoại lệ của lịch tuần khai chung một bảng có cột loại** trong Work Calendar Settings —
   *Nghỉ lễ* (gồm cả nghỉ ghép) và *Làm bù*. Một lưới cho cả năm thì HR thấy được thế cân bằng
   "nghỉ ghép 2 ngày ↔ làm bù 2 ngày"; hai bảng riêng thì phải tự nhớ đối chiếu.
9. **Đổi tên child doctype `Lunar Holiday` → `Work Calendar Day`.** Tên cũ đã sai từ lúc bảng đó
   nhận thêm ngày lễ riêng công ty, và sẽ sai nặng hơn khi nhận cả ngày làm bù. Chỉ được tham chiếu
   ở Work Calendar Settings + test của nó, dữ liệu 6 dòng trên một Single → rename gọn.
10. **Nghỉ ghép = có lương** (loại *Nghỉ lễ*, thành `NL`, vào Tổng công). Đây đúng bằng hành vi của
    ngày 17/07/2026 hôm nay nên **không đổi gì**. Nếu HR xác nhận Miyano có kiểu nghỉ ghép *trừ phép
    năm* hoặc *không lương* thì cần thêm loại — xem Open Questions.

## Bối cảnh kỹ thuật (đã kiểm chứng phiên này — không giả định)

- **`Salary Slip.get_working_days_details`** ([salary_slip.py:520-534](../../hrms/payroll/doctype/salary_slip/salary_slip.py#L520-L534)):
  `total_working_days = số ngày trong kỳ − len(MỌI dòng Holiday)`. Dòng cuối tuần nằm chung trong đó.
  Gỡ cuối tuần mà không làm gì thêm → mẫu số nhảy 22 → 31, **lương sai toàn bộ**.
- **`get_payment_days`** trừ y hệt, nhưng trên khoảng `actual_start_date..actual_end_date` (đã chặn
  theo ngày vào làm / nghỉ việc). Nhánh clamp: `if payment_days > lwp: … else: payment_days = 0`.
- `payment_days` cuối cùng = `base − lwp − absent_days`, trong đó `doc.absent_days` **đã gộp** cả
  `half_absent_days × 0.5`. Nên chỉ cần trừ đúng hai giá trị đã nằm trên doc.
- **`get_employee_shift`** ([shift_assignment.py:402](../../hrms/hr/doctype/shift_assignment/shift_assignment.py#L402))
  đã phân giải sẵn Shift Assignment → `Employee.default_shift`. Không phải viết lại.
- **`get_holiday_list_for_employee` mù ngày tháng** — trả về đúng một list bất kể đang hỏi về ngày
  nào. Với mô hình mỗi năm một list, sang 2027 mà xem lại tháng 12/2026 sẽ tra nhầm lịch → mất `NL`.
- **`Leave Application.get_holidays`** ([leave_application.py:1249](../../hrms/hr/doctype/leave_application/leave_application.py#L1249))
  đếm dòng Holiday để trừ khỏi số ngày phép. Gỡ cuối tuần → đơn T6→T2 ăn 4 ngày phép thay vì 2.
- **`Shift Type.mark_absent_for_dates_with_no_attendance`** ([shift_type.py:281-289](../../hrms/hr/doctype/shift_type/shift_type.py#L281-L289))
  loại ngày nghỉ bằng `get_holiday_dates_between`. Không sửa → **V mọi thứ Bảy**.
- **Hiện trạng site `miyano`:** 1 Holiday List thật (`VN Miyano 2026`: 104 dòng cuối tuần + 12 dòng
  lễ, trong đó 1 dòng *Nghỉ lễ công ty* 17/07 nhập tay, description dính nguyên HTML ql-editor);
  6/6 nhân viên ghim `holiday_list = VN Miyano 2026` và `default_shift = Ca Hành Chính`;
  `Ca Hành Chính` có `mark_auto_attendance_on_holidays = 0`; Payroll Settings
  `payroll_based_on = Attendance`, `include_holidays_in_total_working_days = 0`,
  `consider_unmarked_attendance_as = Present`.
- **6 Salary Slip tồn tại, TOÀN BỘ ở `docstatus = 0` (nháp), đều kỳ 07/2026**; cả 5 cấu trúc lương
  đều là cấu trúc MVL. → Sinh lại lịch 2026 **không đụng phiếu lương đã phát hành nào**. Vẫn phải
  qua cổng bất biến, nhưng rủi ro thực tế thấp hơn nhiều so với dự kiến ban đầu.

## Mô hình

### Ba loại ngày, ba nguồn tách bạch

| Loại ngày | Nguồn sự thật | Ai khai | Bảng công | Có lương |
|---|---|---|---|---|
| **Ngày làm việc** | `Shift Type.custom_working_days` + `start_time`/`end_time` | HR, một lần | mã công | theo mã |
| **Ngoài lịch tuần** (T7/CN) | *suy ra* — không nằm trong lịch tuần | không ai | `-` | không |
| **Nghỉ lễ** | `Holiday List` (sinh từ Work Calendar Settings) | HR, mỗi năm | `NL` | có |

### Chuỗi phân giải lịch tuần

```
Shift Assignment phủ ngày đó  →  Employee.default_shift  →  Work Calendar Settings (mặc định công ty)  →  LỖI CẤU HÌNH
```

Hai tầng đầu do `get_employee_shift()` lo sẵn. Tầng ba là lưới an toàn cho nhân viên chưa phân ca.
**Tầng cuối là chủ ý**: thà nổ lỗi rõ ràng còn hơn im lặng coi mọi ngày là ngày làm việc rồi chấm V
cả tháng và tính sai mẫu số lương. Đây là bài học trực tiếp từ rủi ro "lịch chết ngày 01/01/2027"
đã phát hiện khi phân tích.

### Chuỗi phân giải Holiday List — theo NGÀY

Vì mỗi năm một list, không thể dùng thẳng `get_holiday_list_for_employee` (mù ngày tháng):

```
list của công ty NV, có [from_date, to_date] phủ `date`  →  get_holiday_list_for_employee()  →  không có (cảnh báo, không throw)
```

Thiếu lịch lễ chỉ làm mất ký hiệu `NL` và làm lễ không được tính công — **không** phá ngày nghỉ cuối
tuần (đã tách sang Shift Type). Đó chính là lợi ích an toàn lớn nhất của việc tách: chế độ hỏng khi
quên tạo lịch năm mới trở nên nhẹ và nhìn thấy được, thay vì thảm hoạ im lặng.

### Bất biến của generator: dòng lễ chỉ rơi vào ngày làm việc

Lễ trùng ngày ngoài lịch tuần → sinh **nghỉ bù** vào ngày làm việc kế tiếp (Điều 112 khoản 3), đúng
như logic đang chạy — chỉ đổi chỗ hỏi: hỏi **lịch tuần** thay vì hỏi cờ `weekly_off`.

`work_schedule.public_holidays_between()` **giao thêm với tập ngày làm việc** như một lớp phòng thủ:
một dòng lễ bị nhập nhầm vào Chủ nhật không được phép cộng khống một ngày công vào lương.

## Thiết kế

### 1. Module miền `hrms/hr/work_schedule.py` — cửa duy nhất

Mọi code Miyano hỏi lịch qua đây. Không nơi nào gọi thẳng `is_holiday()` nữa.

```python
calendar_exceptions(year) -> dict[date, str]     # {ngày: day_type} từ Work Calendar Settings
is_scheduled_day(employee, date) -> bool        # (mẫu tuần XOR ngoại lệ "Làm bù"). KHÔNG xét ngày lễ
is_rest_day(employee, date) -> bool             # ngoài lịch tuần            → bảng công "-"
is_public_holiday(employee, date) -> bool       # dòng lễ, đã giao với ngày trong lịch tuần → "NL"
is_working_day(employee, date) -> bool          # PHẢI ĐI LÀM = scheduled AND không phải lễ

scheduled_days_between(emp, start, end) -> set[date]     # MẪU SỐ LƯƠNG — kể cả ngày lễ
non_working_days_between(emp, start, end) -> set[date]   # nghỉ tuần ∪ lễ, đã khử trùng
public_holidays_between(emp, start, end) -> set[date]
scheduled_days_map(employees, start, end) -> dict        # bulk cho report/bảng công — không N+1
shift_window(employee, date) -> tuple | None             # (giờ vào, giờ ra) của ca — nền cho OT
holiday_list_for(employee, date) -> str | None           # phân giải theo ngày (mục trên)
```

**Quy ước đặt tên là một phần của spec, không phải chuyện thẩm mỹ.** *Scheduled* = theo lịch tuần,
**kể cả ngày lễ**; *working* = **phải đi làm**, tức đã trừ lễ. Mẫu số lương dùng **scheduled** — vì
theo quyết định HR 2026-08-04, ngày công chuẩn = ngày đi làm + nghỉ lễ + nghỉ có lương, nên ngày lễ
phải nằm trong mẫu số. Dùng nhầm `working_*` cho mẫu số sẽ **hụt đúng bằng số ngày lễ của tháng** —
loại lỗi im lặng, chỉ lộ ở tháng có lễ. Hai từ không được phép dùng lẫn ở bất kỳ đâu.

Phần thuần luật (tập thứ trong tuần → ngày trong lịch) tách thành hàm không chạm DB để test trực
tiếp. Cache theo request cho `Shift Type → tập thứ` và cho danh sách lễ, giống lối `_cell_code_map()`
đang dùng trong report.

### 2. `Shift Type`: thêm lịch tuần

Custom field qua fixtures (theo đúng lối 5 field tách buổi đã có):

| field | type | label | ghi chú |
|---|---|---|---|
| `custom_working_days` | Table → `Assignment Rule Day` | Ngày làm việc trong tuần | để trống = rơi xuống mặc định công ty |

Không thêm field giờ nào — `start_time`, `end_time`, `custom_lunch_start/end`,
`custom_flexible_shift`, `custom_flex_band_minutes`, `custom_min_work_hours` đã đủ mô tả khung ca.
**"Ngoài giờ" = ngoài khung đó**, và đó chính là định nghĩa OT sẽ dùng, nên OT không phải phát minh
lại khái niệm nào.

`Ca Hành Chính` sẽ được đặt T2–T6 qua `ensure_defaults` (self-heal, idempotent, không ghi đè nếu HR
đã khai khác).

### 3. `Work Calendar Settings`: nguồn duy nhất của ngày lễ

- **Thêm** `default_working_days` (Table → `Assignment Rule Day`) — lịch tuần mặc định công ty, tầng
  ba của chuỗi phân giải.
- **Bỏ** `weekly_off_days` — chính sách nghỉ tuần chuyển hẳn sang lịch làm việc. (Bỏ field, không đổi
  ý nghĩa field cũ: tránh cảnh một field vẫn còn đó mà không ai đọc.)
- **Đổi** bảng `lunar_holidays` thành `calendar_days` (child doctype `Lunar Holiday` →
  `Work Calendar Day`, **thêm cột `day_type`**) — giữ mọi ngày khác thường của năm ở một chỗ: lễ âm,
  lễ riêng công ty, nghỉ ghép, và ngày làm bù. Xem §3b. Nhãn section: *"Ngày đặc biệt trong năm"*.
- Lễ **dương lịch** (1/1, 30/4, 1/5, 1/9, 2/9) vẫn tự sinh, không phải nhập.
- Dòng chữ *"đừng sửa tay Holiday List"* trên form nay **đúng thật**: đã có đủ đường khai chính thức.

### 3b. Ngoại lệ của lịch tuần (nghỉ ghép / làm bù)

`custom_working_days` là **mẫu tuần lặp lại vô hạn** — nó không nói được "riêng thứ Bảy 29/08/2026
thì đi làm". Mô hình cũ nói được (HR xoá dòng `weekly_off` của đúng ngày đó), nên nếu bỏ qua thì
spec này là một **bước lùi về khả năng biểu đạt**. Làm bù là thông lệ phổ biến ở Việt Nam.

Bảng ngoại lệ trong Work Calendar Settings, mỗi dòng là một ngày **khác với mẫu tuần**:

| Cột | Kiểu | Ghi chú |
|---|---|---|
| `year` | Int | năm, để lọc khi sinh lịch |
| `holiday_date` | Date | ngày dương lịch |
| `day_type` | Select | **`Nghỉ lễ`** (mặc định) hoặc **`Làm bù`** |
| `description` | Data | tên hiển thị |

- **`Nghỉ lễ`** → xuống Holiday List như dòng lễ (`weekly_off = 0`) → `NL`, có lương, vào Tổng công.
  Dùng cho cả lễ âm (Tết, Giỗ Tổ), lễ riêng công ty (17/07), và **nghỉ ghép**.
- **`Làm bù`** → **KHÔNG** xuống Holiday List (nó là ngày *làm việc*, không phải ngày nghỉ). Nó sống
  ở Work Calendar Settings và được `is_scheduled_day` đọc trực tiếp.

Luật hợp nhất: `is_scheduled_day(nv, ngày)` = *(thứ nằm trong mẫu tuần)* **XOR** *(ngày có dòng
`Làm bù`)*, rồi `is_working_day` trừ tiếp ngày lễ.

**Ngoại lệ tự lan ra mọi nơi** — đây là lợi tức của thiết kế một cửa. Chỉ `is_scheduled_day` biết về
nó, sáu nơi còn lại đúng theo mà không phải sửa dòng nào:

| Nơi | Ngày T7 làm bù |
|---|---|
| Bảng công | hiện mã công thay vì `-` |
| Chấm vắng tự động | ai không đi làm hôm đó → `V` |
| Phân loại giờ vào/ra | chạy như ngày thường |
| Đơn nghỉ | nghỉ đúng hôm đó → trừ phép |
| Mẫu số lương | +1 ngày |
| Cờ check-in ngoài lịch | **không** gắn cờ |

#### Quy tắc vận hành: làm bù phải cùng tháng với ngày nghỉ ghép

Ví dụ thật, Quốc khánh 2026 (01/09 T3, 02/09 T4). Công ty nghỉ thêm 03/09 (T5) + 04/09 (T6) để nghỉ
liền tới hết tuần, và làm bù hai thứ Bảy:

- bù **cùng tháng** (05/09 và 12/09): tháng 9 vẫn **22** ngày công → lương một ngày không đổi. ✔
- bù **khác tháng** (29/08 và 05/09): tháng 8 lên **22** (từ 21), tháng 9 xuống **21** (từ 22) →
  **lương một ngày công của hai tháng lệch nhau**, dù tổng cả năm không đổi.

Không phải ràng buộc kỹ thuật — là điều HR phải biết trước khi ký. Ghi vào mô tả field.

#### Ba chốt an toàn

1. **Xem trước tác động lên mẫu số.** Lưu Work Calendar Settings thì hiện bảng *số ngày công từng
   tháng — trước / sau*. Bắt đúng lỗi "khai làm bù mà quên khai nghỉ ghép", vốn im lặng đổi lương.
2. **Chặn sửa lịch của kỳ đã chốt công.** Bảng Công Tháng đã ký mà đổi lịch quá khứ thì bảng và
   phiếu lương lệch nhau trong im lặng. Dùng `period_lock.is_period_locked`, nhất quán với
   `guard_period_not_locked` đang áp cho Attendance.
3. **Validate trùng và vô nghĩa.** Một ngày không được vừa `Nghỉ lễ` vừa `Làm bù` → chặn. Dòng
   `Làm bù` rơi vào ngày vốn đã trong mẫu tuần → cảnh báo, không im lặng nuốt.

### 4. `setup_vn_holiday.create_vn_holiday_list`: thôi sinh cuối tuần

- Bỏ vòng `get_weekly_off_dates()` **và bỏ luôn tham số `weekly_off_days`** khỏi chữ ký hàm —
  Holiday List chỉ còn dòng lễ, nên tham số đó không còn nghĩa gì. Để lại một tham số không ai
  đọc là mời gọi người sau truyền vào rồi tưởng nó có tác dụng.
- Quy tắc nghỉ bù hỏi `work_schedule` (lịch tuần) thay vì tập `weekly_off_dates`.
- Giữ nguyên tính idempotent và mẹo `scheduled_holidays` (ngày bù của lễ xử lý sớm không được nuốt
  một lễ chưa tới lượt — vd 30/4/2028 rơi Chủ nhật).
- Giữ nguyên các dòng lễ HR đã nhập tay từ trước (append-only, không xoá).

### 5. Payroll: **đặt thẳng con số**, không nudge

Thay `add_paid_holidays` bằng một hook duy nhất `set_working_days`, cùng vị trí thứ nhất trong chuỗi
`Salary Slip.validate` (vẫn phải chạy **trước** `sheet_gate.gate`):

```python
total_working_days = |scheduled_days_between(emp, start_date, end_date)|
base               = |scheduled_days_between(emp, actual_start_date, actual_end_date)|
payment_days       = base - leave_without_pay - absent_days   if base > leave_without_pay else 0
```

(`scheduled_*` chứ không phải `working_*` — xem quy ước đặt tên ở §1; nhầm là hụt mẫu số đúng bằng
số ngày lễ của tháng.)

Vì sao **đặt tuyệt đối** thay vì cộng/trừ delta:

- Con số đúng **không phụ thuộc** vào việc Holiday List còn hay đã hết dòng cuối tuần → mỗi bước
  triển khai độc lập, deploy lệch nhau không sao, migration chạy dở cũng không sinh trạng thái sai.
- `days − (cuối tuần ∪ lễ) + lễ` rút gọn đúng bằng `số ngày làm việc theo lịch tuần`. Đặt thẳng
  con số đó vừa ngắn hơn vừa nói đúng ý định, thay vì hai phép trừ–cộng triệt tiêu nhau.
- Nhánh clamp `else: 0` sao chép **y nguyên** ERPNext để bất biến là byte-identical, kể cả ở ca biên.

`doc.absent_days` đã gộp `half_absent_days × 0.5` nên chỉ trừ đúng hai giá trị đã nằm trên doc.

**Phạm vi mở rộng có chủ ý:** hook bỏ điều kiện `salary_type_of(...)` mà `add_paid_holidays` đang
dùng — nó phải chạy cho **mọi** Salary Slip. Sau migration không phiếu nào còn lấy được cuối tuần từ
Holiday List, nên một phiếu ngoài MVL bị bỏ sót sẽ ra mẫu số 31. Trên site hiện cả 5 cấu trúc đều là
MVL nên đây **không** phải thay đổi hành vi thực tế, nhưng là thay đổi phạm vi phải nói rõ.

> **Đây là sửa logic cầu nối lương → cổng ký duyệt bắt buộc theo CLAUDE.md.**

### 6. Đơn nghỉ

`get_holidays()` trả về `|non_working_days_between(...)|` — hợp của (dòng lễ, ngày ngoài lịch tuần),
đã khử trùng. Đơn T6→T2 vẫn trừ đúng 2 ngày phép trước và sau khi đổi.

`create_or_update_attendance` (leave_application.py:251-270) đổi `holiday_dates` → tập ngày không làm
việc, để đơn nghỉ không sinh Attendance vào T7/CN.

### 7. Chấm công

| Nơi | Đổi thành |
|---|---|
| `Shift Type.mark_absent_for_dates_with_no_attendance` | `non_working_days_between` — **không sửa là V mọi thứ Bảy** |
| `Attendance.falls_on_holiday` | `not is_working_day` (đổi tên thành `falls_on_non_working_day`) |
| `attendance_exempt.is_exempt_working_day` | `is_working_day` |
| `business_trip.create_trip_attendance` | `is_working_day` |
| `attendance_request` (`include_holidays`) | `is_working_day` |

Cờ `mark_auto_attendance_on_holidays` của Shift Type **giữ nguyên ngữ nghĩa**: bật = chấm công cả
ngày ngoài lịch. Đợt này không đổi giá trị của nó trên site (đang `0`).

### 8. Báo cáo & Bảng Công Tháng

`monthly_attendance_report.get_holidays` tách làm hai nguồn qua `scheduled_days_map`:
`-` từ lịch tuần, `NL` từ Holiday List. Ký hiệu, màu, cột tổng, `Tổng công` **không đổi một chữ**.

`get_sheet_rows` giữ nguyên vị thế nguồn suy diễn duy nhất; `attendance_review` tiếp tục đọc lại nó.

Phần thưởng kèm theo: mục *Upcoming Holidays* trên PWA
([Holidays.vue](../../frontend/src/components/Holidays.vue)) lâu nay liệt kê cả thứ Bảy/Chủ nhật, sau
đổi chỉ còn ngày lễ thật.

### 9. `Employee Checkin`: cờ ngoài lịch — nền cho OT

Hai custom field, gắn khi tạo log:

| field | type | label |
|---|---|---|
| `custom_outside_schedule` | Check | Ngoài lịch làm việc |
| `custom_outside_reason` | Select | Ngày nghỉ / Ngoài giờ |

- `Ngày nghỉ` = ngày đó ngoài lịch tuần hoặc là ngày lễ.
- `Ngoài giờ` = ngày làm việc nhưng dấu chấm nằm ngoài khung ca (đã tính biên trượt).

**Cờ này hoàn toàn trơ.** Không nhánh nào của đường sinh công đọc tới nó — đường sinh công vẫn loại
ngày nghỉ theo *ngày* như hôm nay. Test sẽ chứng minh bằng cách bật cờ rồi chấm lại và so mã công.

Cố ý **không** dùng lại `skip_auto_attendance`: cờ đó đang là đối tượng chẩn đoán của
[skip_attendance_diag.py](../../hrms/skip_attendance_diag.py), mượn vào là làm nhiễu công cụ đó.

### 10. Di trú

Patch `hrms/patches/v15_0/remove_weekly_off_from_holiday_list.py` (+ dòng trong `hrms/patches.txt`):

1. **Chặn trước:** mọi `Shift Type` đang được dùng phải đã khai `custom_working_days`, hoặc Work
   Calendar Settings phải có `default_working_days`. Thiếu → abort, không xoá gì.
2. Chụp `total_working_days` / `payment_days` / `absent_days` / `leave_without_pay` của **toàn bộ**
   Salary Slip hiện có.
3. Xoá các dòng `weekly_off = 1` khỏi những Holiday List **đang được Company hoặc Employee trỏ tới**;
   giữ nguyên dòng lễ (kể cả 2 dòng nghỉ bù và dòng *Nghỉ lễ công ty* 17/07 nhập tay). Danh sách rác
   của test (`Salary Slip Test Holiday List`) **không** đụng tới — nó không thuộc đường chạy thật, và
   sửa nó chỉ làm nhiễu chẩn đoán sau này.
4. Gỡ ghim `Employee.holiday_list` (về trống → rơi về Company default, một chỗ duy nhất phải trỏ lại
   mỗi năm).
5. Tính lại và **khẳng định từng phiếu giống hệt**. Lệch một số → abort + rollback.
6. Dọn HTML ql-editor trong `description` của dòng lễ nhập tay (hiển thị thô trên report/print/PWA).

Không `git revert` được → **ask-first, ký duyệt riêng trước khi chạy trên site.**

## Tech Stack

Frappe/ERPNext HRMS v15, Python (controllers + `frappe.qb`), fixtures JSON, Vue 3 (chỉ hưởng lợi
gián tiếp, không sửa). Test qua **rollback harness** trong console — **KHÔNG** `bench run-tests` trên
`miyano`.

## Commands

```bash
cd /home/miyano/frappe-bench

bench --site miyano migrate                    # nạp custom field lịch tuần + cờ ngoài lịch
bench --site miyano console                    # rollback harness (savepoint mỗi test, commit→noop)
# sinh lại lịch lễ một năm (ask-first trên site):
bench --site miyano execute hrms.hr.doctype.work_calendar_settings.work_calendar_settings.generate_holiday_list \
      --kwargs "{'year': 2026}"
bench build --app hrms                         # nếu chạm .js của Work Calendar Settings
```

## Project structure (files)

```
hrms/hr/work_schedule.py                                     (MỚI — API miền, cửa duy nhất)
hrms/hr/tests/test_work_schedule.py                          (MỚI — luật lịch + chuỗi phân giải)
hrms/hr/doctype/work_calendar_settings/work_calendar_settings.py   (sửa — bỏ weekly_off, thêm default_working_days)
hrms/hr/doctype/work_calendar_settings/work_calendar_settings.json (sửa — field + bảng ngoại lệ)
hrms/hr/doctype/work_calendar_day/                           (ĐỔI TÊN từ lunar_holiday/ + cột day_type)
hrms/patches/v15_0/rename_lunar_holiday_doctype.py           (MỚI — pre_model_sync)
hrms/setup_vn_holiday.py                                     (sửa — thôi sinh cuối tuần; nghỉ bù hỏi lịch tuần)
hrms/setup_vn_defaults.py                                    (sửa — self-heal T2–T6 cho Ca Hành Chính)
hrms/vn_payroll/salary_slip_hook.py                          (sửa — set_working_days thay add_paid_holidays)
hrms/hooks.py                                                (sửa — doc_events Employee Checkin + fixtures filter)
hrms/hr/doctype/shift_type/shift_type.py                     (sửa — chấm vắng hỏi work_schedule)
hrms/hr/doctype/attendance/attendance.py                     (sửa — falls_on_non_working_day)
hrms/hr/doctype/leave_application/leave_application.py       (sửa — get_holidays + sinh attendance)
hrms/hr/attendance_exempt.py                                 (sửa — is_working_day)
hrms/hr/doctype/business_trip/business_trip.py               (sửa — is_working_day)
hrms/hr/doctype/attendance_request/attendance_request.py     (sửa — is_working_day)
hrms/hr/report/monthly_attendance_report/monthly_attendance_report.py (sửa — "-" và "NL" hai nguồn)
hrms/hr/doctype/employee_checkin/employee_checkin.py         (sửa — gắn cờ ngoài lịch)
hrms/fixtures/custom_field.json                              (sửa — 1 field Shift Type + 2 field Checkin)
hrms/patches/v15_0/remove_weekly_off_from_holiday_list.py    (MỚI — di trú, ký duyệt)
hrms/patches.txt                                             (sửa — 1 dòng)
hrms/payroll/doctype/salary_slip/test_working_days_invariance.py  (MỚI — CỔNG bất biến lương)
hrms/hr/doctype/employee_checkin/test_outside_schedule.py    (MỚI — cờ trơ)
hrms/tests/test_holiday_separation_e2e.py                    (MỚI — E2E xuyên module)
docs/spec/work-schedule-and-holiday-separation.md            (spec này)
```

Các test đã có (`test_setup_vn_holiday.py`, `test_work_calendar_settings.py`, `test_shift_type.py`,
`test_attendance_exempt.py`, `test_monthly_attendance_report.py`) được **mở rộng**, không viết lại.

## Code style

Theo convention repo: tabs, double quotes, line length 110, ruff qua pre-commit. Tên doctype/field
tiếng Anh, label tiếng Việt. Docstring nêu **why** chứ không kể lại code. Guard idempotent
(`frappe.db.exists` trước khi tạo). Tái dùng cơ chế Frappe (`get_employee_shift`,
`Assignment Rule Day`) thay vì tự code. **Không** đặt tên method có tiền tố `_` trên `Document`
(bị `__getattr__` nuốt thành `None`).

## Testing strategy (rollback harness — NEVER `bench run-tests` trên `miyano`)

**Cổng bất biến lương (chặn — chạy ở CẢ HAI trạng thái lịch):** kỳ thường / kỳ có ngày lễ / có ngày
vắng / có nửa ngày / vào làm giữa kỳ / nghỉ việc giữa kỳ / kỳ toàn ngày nghỉ (chia 0) / `lwp ≥ base`
(nhánh clamp). Dựng Salary Slip trên data cố định → ghi 4 con số → chạy ở trạng thái *còn dòng cuối
tuần* và *đã gỡ* → **giống hệt**.

- **Bất biến số ngày phép:** đơn T6→T2 = 2 ngày, trước và sau.
- **Chấm vắng:** không `V` nào rơi vào T7/CN sau khi gỡ dòng cuối tuần.
- **Chuỗi phân giải ca:** có Shift Assignment / chỉ `default_shift` / chỉ mặc định công ty / không gì
  cả → lỗi cấu hình rõ ràng (không âm thầm coi là ngày làm việc).
- **Phân giải Holiday List theo ngày:** ở năm 2027, hỏi ngày 12/2026 vẫn ra lịch 2026.
- **Bất biến của generator:** dòng lễ không bao giờ rơi vào ngày ngoài lịch tuần; lễ trùng T7/CN sinh
  đúng một ngày bù; chạy lại không nhân đôi; dòng nhập tay cũ sống sót.
- **Phòng thủ:** một dòng lễ nhập nhầm vào Chủ nhật **không** cộng khống ngày công.
- **Báo cáo:** `-` từ lịch tuần, `NL` từ Holiday List, cột tổng và màu không đổi.
- **Cờ ngoài lịch là trơ:** bật cờ rồi chấm lại → mã công y nguyên.
- **E2E:** một tháng đầy đủ (checkin → attendance → bảng công → phiếu lương) so khớp trước/sau.

## Boundaries

- **Always:** mọi câu hỏi về lịch đi qua `work_schedule`; đặt tuyệt đối thay vì nudge ở payroll;
  `get_sheet_rows` vẫn là nguồn suy diễn duy nhất; cờ ngoài lịch phải trơ; fixtures additive; stage
  đúng file của task (không `git add -A`); test qua rollback harness; `git revert` được (trừ patch di
  trú, đã tách riêng).
- **Ask first (STOP ký duyệt):** chạy patch di trú trên site; thay `add_paid_holidays` bằng
  `set_working_days` (sửa cầu nối lương); gỡ ghim `Employee.holiday_list`; deploy fixtures lên site;
  đổi `include_holidays_in_total_working_days` hay bất kỳ setting nào của Payroll Settings.
- **Never:** đổi ngữ nghĩa `status` / `leave_type` / `half_day_status`; để đường sinh công đọc cờ
  ngoài lịch; nới lỏng test bất biến để "cho xanh"; seed Holiday List tự động khi migrate; sinh công
  cho ngày ngoài lịch trong đợt này; tính tiền OT trong đợt này.

## Success Criteria

- [ ] `hrms/hr/work_schedule.py` là cửa duy nhất; không còn lời gọi `is_holiday()` nào trong code
      Miyano ngoài chính module đó.
- [ ] `Shift Type` khai được ngày làm việc trong tuần; chuỗi phân giải 4 tầng có test, tầng cuối nổ
      lỗi cấu hình rõ ràng.
- [ ] `Holiday List` không còn dòng `weekly_off`; mọi ngày lễ (kể cả lễ riêng công ty) khai ở Work
      Calendar Settings và sinh tự động.
- [ ] **Cổng bất biến lương xanh** ở cả hai trạng thái lịch, đủ 8 ca biên.
- [ ] Số ngày phép của đơn bắc qua cuối tuần không đổi; không `V` nào rơi vào T7/CN.
- [ ] Bảng công giữ nguyên `-` / `NL` / màu / cột tổng, nay từ hai nguồn tách bạch.
- [ ] Khai được **ngày làm bù** (T7/CN thành ngày công) và **nghỉ ghép**; ngoại lệ lan đúng tới cả
      6 nơi tiêu thụ; trùng ngày và kỳ đã khoá bị chặn.
- [ ] Check-in ngoài lịch được đánh dấu; test chứng minh cờ không làm lệch mã công.
- [ ] Patch di trú có bước chặn trước, chụp–so–abort, và đã được ký duyệt trước khi chạy.

## Out of scope (spec/đợt sau)

- **Tính OT** (giờ, hệ số 150/200/300%, phụ cấp ca đêm) — `docs/spec/overtime-registration.md`.
  Đợt này chỉ dựng nền: khái niệm trong/ngoài ca + log đã đánh dấu.
- **Sinh công cho ngày làm thêm** và **nghỉ bù tự động từ ngày làm thêm** (khoảng trống G2/G3 đã nêu
  khi phân tích: `Compensatory Leave Request` hiện bất khả dụng vì đòi Attendance `Present` trên ngày
  mà hệ thống không bao giờ tạo).
- **Nửa ngày nghỉ tuần** (làm sáng thứ Bảy) — lịch tuần đợt này là đơn vị ngày.
- **Nhiều bộ lịch theo phòng ban** — đã mô hình hoá được qua Shift Type nhưng không cấu hình đợt này.
- Tự sinh ngày âm lịch (Tết/Giỗ Tổ) — vẫn nhập tay.

## Open Questions

1. **Nghỉ ghép ở Miyano có trừ phép năm hay không lương không?** Spec đang mặc định **có lương**
   (loại *Nghỉ lễ*) — đúng bằng hành vi của 17/07 hôm nay. Nếu HR xác nhận có kiểu *trừ phép năm*,
   cần thêm một loại **và** một cơ chế sinh đơn nghỉ, tức một mảng việc lớn hơn hẳn — spec riêng.
2. **Lịch tuần mặc định công ty đặt là gì?** Đề xuất T2–T6 (khớp thực tế đang chạy: nghỉ T7 + CN).
3. **Ngày lễ 17/07/2026 *"Nghỉ lễ công ty"*** — sau khi dọn HTML, có giữ nguyên tên đó không, và có
   khai ngược vào Work Calendar Settings để lần sinh sau không mất?
4. **Ai được sửa `Shift Type.custom_working_days`?** Hiện Shift Type mở cho HR Manager. Lịch tuần nay
   là đầu vào của mẫu số lương → có nên siết quyền, hoặc chặn sửa khi kỳ công đã chốt?

> Đã chốt (2026-08-28): tách thật · lịch tuần trên Shift Type · Holiday List chỉ lễ, mỗi năm một list
> · mọi ngày lễ khai ở Work Calendar Settings · log ngoài lịch giữ + đánh dấu + trơ · sinh lại cả 2026.
