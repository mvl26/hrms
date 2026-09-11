# Spec: Work Calendar là nguồn duy nhất — chấm dứt trùng cấu hình, nối giờ làm việc

> Status: **DRAFT for approval.** Viết 2026-09-11 theo yêu cầu: *"holiday list và work calendar đang
> bị trùng setting ngày làm việc và nghỉ lễ, cần tách biệt; work calendar phải logic với attendance,
> leave và shift type để tính giờ làm việc và ngày làm việc cho nhân viên."*
> Nối tiếp `docs/spec/work-schedule-and-holiday-separation.md` và
> `docs/spec/work-schedule-integration-hardening.md` (cả hai đã build).
> **Không implement tới khi được duyệt.**

## Objective

Hai việc tách bạch:

**A. Chấm dứt trùng cấu hình.** Hôm nay có **ba** chỗ khai *ngày làm việc trong tuần* và **hai** chỗ
khai *ngày nghỉ lễ*. Hai đợt trước đã dựng đúng mô hình (một nguồn → một kết quả), nhưng **chưa gỡ
những cửa cũ đi**, nên trên màn hình HR vẫn thấy đủ nút để làm lại từ đầu theo lối cũ.

**B. Nối lịch với giờ.** `work_schedule` hiện chỉ trả lời được *"ngày này có phải ngày làm việc
không"*. Nó chưa trả lời được *"nhân viên này tháng này phải làm bao nhiêu giờ"* — con số đó đang
được hardcode `8.0` và đếm ngày nghỉ bằng cách đọc thẳng `Holiday List`.

**Success:**

1. Chỉ còn **một** chỗ khai ngày nghỉ lễ và **một** chuỗi khai ngày làm việc; `Holiday List` thành
   bảng chiếu **chỉ đọc**, không bấm được nút nào để tự sinh lại.
2. `Holiday List` trên site thật không còn dòng nghỉ cuối tuần nào.
3. Giờ định mức của mỗi nhân viên **suy từ ca thật** và **trừ ngày nghỉ phép**, không hardcode.
4. HR mở được một màn hình trả lời: *tháng này nhân viên X có bao nhiêu ngày làm việc, bao nhiêu giờ
   định mức, theo lịch nào.*
5. Cổng bất biến lương vẫn xanh; 6 phiếu lương thật vẫn 0 lệch.

## Bối cảnh: đo trên site `miyano` ngày 2026-09-11

### A1. Ba chỗ khai ngày làm việc trong tuần

| # | Nơi | Trạng thái thật hôm nay | Ai đọc |
|---|---|---|---|
| 1 | `Holiday List.weekly_off` + nút **"Add to Holidays"** | `VN Miyano 2026` đang đặt `weekly_off = Sunday`, **104 dòng** `weekly_off = 1` | ERPNext gốc (qua `Holiday`) |
| 2 | `Work Calendar Settings.default_working_days` | T2–T6 | `work_schedule.company_default_weekdays` |
| 3 | `Shift Type.custom_working_days` | `Ca Hành Chính` = T2–T6 | `work_schedule.shift_weekdays` |

**#2 và #3 KHÔNG phải trùng lặp** — chúng là hai tầng của một chuỗi phân giải (ca thắng, công ty là
lưới an toàn cho nhân viên chưa phân ca). Nhưng giao diện không nói điều đó ở đâu cả, nên nhìn vào
thì đúng là thấy trùng. **#1 mới là trùng thật**, và nguy hiểm: nó là lối cũ vẫn còn nguyên nút bấm.

### A2. Hai chỗ khai ngày nghỉ lễ

| Nơi | Trạng thái | Ghi chú |
|---|---|---|
| `Holiday List.holidays` (bảng con) | 12 dòng lễ, **sửa tay được**, còn nút *Clear Table* và *Add Local Holidays* | ERPNext đọc |
| `Work Calendar Settings.calendar_days` | 7 dòng loại `Nghỉ lễ` | nguồn sinh ra 12 dòng kia |

Dòng chữ *"đừng sửa tay Holiday List"* trên form Work Calendar Settings là **lời khuyên, không phải
rào chắn**. Lịch sử đã chứng minh: dòng lễ 17/07/2026 từng được nhập tay thẳng vào Holiday List, kèm
nguyên HTML của trình soạn thảo.

### A3. Việc tách đã BUILD nhưng chưa ÁP DỤNG

Đây là điểm quan trọng nhất của tài liệu này. Patch `remove_weekly_off_from_holiday_list` **đã viết,
đã test, đã diễn tập trên dữ liệu thật (0 lệch), nhưng cố ý CHƯA nối vào `patches.txt`** — nó chờ ký
duyệt vì xoá dữ liệu. Vì vậy 104 dòng nghỉ cuối tuần vẫn nằm nguyên trong `Holiday List`.

Nói cách khác: **một phần cảm giác "đang bị trùng" chính là vì bước cuối chưa bấm.** Không có việc
gì phải thiết kế lại cho phần đó — chỉ cần chạy.

### B1. Giờ định mức đang hardcode, và đang đọc nhầm nguồn

`hrms/hr/working_hours.py`:

```python
STANDARD_HOURS_PER_DAY = 8.0                       # dòng 12 — hardcode
def get_standard_hours(total_days, num_holidays):  # dòng 339
	working_days = max(cint(total_days) - cint(num_holidays), 0)
	return round(STANDARD_HOURS_PER_DAY * working_days, 2)

def _count_holidays_in_month(holiday_list, ...):   # dòng 356 — ĐỌC THẲNG Holiday List
	return frappe.db.count("Holiday", {"parent": holiday_list, ...})
```

Hai lỗi chồng nhau:

- **Hardcode 8h.** `Ca Hành Chính` hiện là **8:00 – 17:30**, nghỉ trưa **12:00 – 13:30** → giờ làm
  thực của ca = 9,5 − 1,5 = **8,0h**. Con số khớp, nhưng là **trùng hợp**: đổi giờ ca 30 phút là KPI
  nói dối mà không ai biết.
- **Đọc thẳng `Holiday List`** — đây là điểm thứ **9** còn sót, hai đợt rà trước đều lọt. Sau khi
  chạy patch di trú, `_count_holidays_in_month` chỉ còn đếm được ngày lễ, nên định mức sẽ tính cả
  T7/CN là ngày công: tháng 7/2026 nhảy từ 23×8 = 184h lên 30×8 = 240h, và **toàn công ty bị báo
  thiếu giờ**. Cùng lỗi ở `monthly_attendance_sheet.set_standard_and_variance`.

### B2. Định mức chưa trừ ngày nghỉ phép

`get_under_target_count_card` so tổng giờ thực với định mức cả tháng. Người nghỉ phép 5 ngày vẫn bị
tính định mức của người đi làm đủ → **luôn nằm trong danh sách thiếu giờ**. Đây chính là mắt xích
"lịch ↔ nghỉ phép" mà yêu cầu nhắc tới.

### B3. `Shift Type.holiday_list` là field chết

Vẫn còn trên form và đang trỏ `VN Miyano 2026`, nhưng từ khi `ShiftType.get_holiday_list` bị gỡ,
**không dòng code nào đọc nó nữa** (đã grep cả hrms lẫn erpnext). Một field còn đó mà không ai đọc
là bẫy: HR đổi nó rồi tưởng có tác dụng.

### B4. Nửa ngày phép chưa có định nghĩa theo giờ

`Leave Application.custom_half_day_period` (sáng/chiều) tồn tại, nhưng không nơi nào nói "sáng" là
khoảng giờ nào. Khung nghỉ trưa của ca (`custom_lunch_start/end`) mới là thứ định nghĩa được điều
đó. Hiện chưa nối.

## Locked decisions

1. **`Work Calendar Settings` là nguồn duy nhất của ngày nghỉ lễ**; `Shift Type.custom_working_days`
   là nguồn duy nhất của lịch tuần, với `default_working_days` của công ty làm **lưới an toàn** cho
   nhân viên chưa phân ca. Hai tầng này được giữ, nhưng phải **nói rõ trên giao diện** là tầng.
2. **`Holiday List` trở thành bảng chiếu CHỈ ĐỌC.** Ẩn `weekly_off`, nút *Add to Holidays*,
   *Clear Table*, *Add Local Holidays*; chặn mọi lần lưu không đến từ generator.
3. **Giờ định mức suy từ ca**, không hardcode: `(end_time − start_time − nghỉ trưa)` của đúng ca áp
   cho ngày đó.
4. **Định mức trừ ngày nghỉ** (phép, ốm, không lương…): không đi làm thì không kỳ vọng có giờ.
5. **Gỡ `Shift Type.holiday_list`** khỏi form (ẩn, không xoá cột) — không ai đọc nó.
6. **Chạy patch di trú là một phần của đợt này**, không còn để treo. Vẫn là cổng ký duyệt riêng.

## Thiết kế

### 1. Ai là nguồn, ai là kết quả

```
NGUỒN (HR khai)                              KẾT QUẢ (máy sinh, chỉ đọc)
┌────────────────────────────────┐
│ Shift Type.custom_working_days │──┐
│   lịch tuần của CA             │  │
├────────────────────────────────┤  │      ┌──────────────────────┐
│ Work Calendar Settings         │  ├─────▶│ work_schedule        │
│   · default_working_days       │  │      │  (API miền duy nhất) │
│     (lưới an toàn)             │  │      └──────────┬───────────┘
│   · calendar_days              │──┘                 │
│     (Nghỉ lễ / Làm bù)         │                    ▼
└────────────────────────────────┘         Attendance · Leave · Payroll
                │                          Bảng công · KPI giờ · PWA
                │ generate_holiday_list()
                ▼
       ┌──────────────────┐
       │ Holiday List     │  CHỈ ĐỌC — chỉ còn ngày lễ
       │ (ERPNext đọc)    │
       └──────────────────┘
```

### 2. Khoá `Holiday List` thành chỉ đọc

Hai lớp, vì một lớp không đủ:

- **Lớp giao diện** — Property Setter (cơ chế repo đã dùng, có trong `fixtures`): `hidden = 1` cho
  `weekly_off`, `get_weekly_off_dates`, `clear_table`, `add_weekly_holidays`, `add_local_holidays`,
  `get_local_holidays`; `read_only = 1` cho bảng `holidays`. Thêm một khối HTML chỉ đường sang
  Work Calendar Settings.
- **Lớp dữ liệu** — `Holiday List.validate` (qua `doc_events`) chặn lưu nếu không đến từ generator:

```python
if not frappe.flags.get("generating_work_calendar"):
	frappe.throw("Holiday List là kết quả sinh ra từ Cấu hình lịch làm việc — sửa ở đó rồi sinh lại.")
```

Generator bật cờ quanh `doc.save()`. Cố ý **không** dùng `read_only` doctype-level: ERPNext còn tạo
Holiday List ở luồng khác (onboarding công ty mới), chặn cứng là vỡ luồng đó.

> Ngoại lệ có chủ ý: danh sách **không** thuộc công ty nào đang dùng (ví dụ
> `Salary Slip Test Holiday List`) không bị chặn — chặn nó chỉ làm phiền, không bảo vệ gì.

### 3. Nói rõ hai tầng lịch tuần

Đổi nhãn + mô tả để giao diện tự giải thích, và thêm một chỗ tra cứu:

| Field | Nhãn mới | Mô tả |
|---|---|---|
| `Shift Type.custom_working_days` | Ngày làm việc trong tuần **(của ca này)** | "Ca có khai thì ca THẮNG lịch mặc định công ty." |
| `Work Calendar Settings.default_working_days` | Lịch mặc định **(chỉ dùng khi ca chưa khai)** | "Lưới an toàn cho nhân viên chưa phân ca." |

Và **gỡ `Shift Type.holiday_list`** khỏi form (Property Setter `hidden = 1`) — quyết định 5.

### 4. Giờ làm việc: suy từ ca, trừ ngày nghỉ

Thêm vào `hrms/hr/work_schedule.py` — vẫn một cửa, không mở cửa thứ hai:

```python
working_days_between(employee, start, end) -> set[date]
    # ngày PHẢI đi làm = scheduled − ngày lễ. (Hiện API chỉ có scheduled_* và non_working_*.)

shift_hours_per_day(shift) -> float
    # (end_time − start_time − nghỉ trưa) của ca. Ca cấu hình vô nghĩa -> dùng khung trưa mặc định,
    # đúng cách `resolve_lunch_window` đang phòng thủ.

standard_hours_between(employee, start, end, exclude_leave=True) -> float
    # Σ shift_hours_per_day(ca của ngày đó) cho từng ngày phải đi làm,
    # trừ những ngày đã có Attendance mang mã nghỉ (hoặc đơn nghỉ đã duyệt).
```

`working_hours.py` thôi hardcode: `get_standard_hours_map` gọi `standard_hours_between`.
`STANDARD_HOURS_PER_DAY` chỉ còn là **mặc định cuối cùng** khi ca không khai giờ, kèm docstring nói
rõ nó là fallback chứ không phải chính sách.

**Vì sao trừ ngày nghỉ:** định mức là *kỳ vọng có mặt*. Người nghỉ phép 5 ngày không được kỳ vọng có
mặt 5 ngày đó; giữ nguyên định mức là đẩy họ vào danh sách "thiếu giờ" vĩnh viễn — KPI nói sai về
người tuân thủ đúng quy định.

> Đây là thay đổi **KPI**, không phải lương. `payment_days` / `total_working_days` không đụng tới.
> Vẫn chạy cổng bất biến lương để chứng minh.

### 5. Màn hình "Lịch hiệu lực của nhân viên"

Một report tra cứu, trả lời đúng câu hỏi trong yêu cầu — *tính giờ làm việc và ngày làm việc cho
nhân viên*:

| Nhân viên | Ca áp dụng | Nguồn lịch tuần | Ngày làm việc | Ngày nghỉ tuần | Ngày lễ | Ngày làm bù | Giờ/ngày | Giờ định mức |
|---|---|---|---|---|---|---|---|---|

Cột **Nguồn lịch tuần** ghi rõ `Ca` / `Mặc định công ty` — chính là thứ làm tan cảm giác "trùng
setting": nhìn một dòng là biết người này đang theo lịch nào và vì sao.

### 6. Nửa ngày phép theo khung ca

`work_schedule.half_day_window(employee, date, period)` → `(từ giờ, tới giờ)`:
*sáng* = `start_time → lunch_start`, *chiều* = `lunch_end → end_time`.

Đợt này **chỉ dùng để hiển thị** (bảng công, PWA, chú giải) — chưa đổi cách tính công hay lương của
nửa ngày. Mục đích là định nghĩa "sáng/chiều" ở một chỗ thay vì để mỗi nơi tự hiểu.

## Tech Stack

Frappe/ERPNext HRMS v15, Python, Property Setter qua `fixtures`, `hrms/translations/vi.csv`.
Test qua **rollback harness** — KHÔNG `bench run-tests` trên `miyano`.

## Project structure (files)

```
hrms/hr/work_schedule.py                               (sửa — working_days_between, shift_hours_per_day,
                                                        standard_hours_between, half_day_window)
hrms/hr/working_hours.py                               (sửa — thôi hardcode, thôi đọc Holiday List)
hrms/hr/report/monthly_attendance_sheet/…              (sửa — set_standard_and_variance)
hrms/hr/holiday_list_guard.py                          (MỚI — chặn sửa tay Holiday List)
hrms/hooks.py                                          (sửa — doc_events Holiday List + fixtures filter)
hrms/fixtures/property_setter.json                     (MỚI/sửa — ẩn field lối cũ)
hrms/hr/doctype/work_calendar_settings/…               (sửa — nhãn hai tầng)
hrms/hr/doctype/shift_type/shift_type.json             (sửa — nhãn custom_working_days)
hrms/hr/report/employee_work_calendar/…                (MỚI — màn hình lịch hiệu lực)
hrms/patches.txt                                       (sửa — nối patch di trú đã chờ sẵn)
hrms/tests/test_work_calendar_single_source.py         (MỚI)
hrms/hr/tests/test_standard_hours.py                   (MỚI)
```

## Testing strategy

- **Cổng bất biến lương** + đối soát 6 phiếu thật: phải 0 lệch (đợt này không đụng lương, nhưng
  `standard_hours` dùng chung API với mẫu số nên vẫn phải chứng minh).
- **Chặn sửa tay:** lưu Holiday List ngoài generator → throw; generator vẫn lưu được; danh sách rác
  của test không bị chặn.
- **Giờ định mức:** ca 8:00–17:30 trừ trưa 1,5h → 8,0h/ngày; đổi ca thành 8:00–17:00 → **7,5h/ngày**
  (đây là ca mà hardcode cũ nói dối); tháng có ngày lễ; tháng có ngày làm bù; người nghỉ phép 5 ngày
  → định mức giảm đúng 5 × giờ ca.
- **Sau di trú:** định mức tháng 7/2026 vẫn là 23 ngày × giờ ca, **không** nhảy lên 30 ngày.
- Toàn bộ chạy ở **cả hai** trạng thái lịch, trên bộ dựng cảnh `work_calendar_fixture`.

## Boundaries

- **Always:** mọi câu hỏi về lịch/giờ đi qua `work_schedule`; cổng bất biến lương trước khi commit
  bất kỳ thay đổi nào chạm số; stage đúng file của task.
- **Ask first (STOP):** chạy patch di trú (xoá dữ liệu, không `git revert` được); deploy Property
  Setter lên site; bất kỳ thay đổi nào làm đổi `payment_days`.
- **Never:** để `Holiday List` sửa được bằng tay sau khi khoá; hardcode lại giờ/ngày ở nơi thứ hai;
  đổi cách tính công của nửa ngày trong đợt này.

## Success Criteria

- [ ] `Holiday List` không bấm được nút tự sinh nào; lưu ngoài generator bị chặn, có test.
- [ ] `Holiday List` trên site không còn dòng `weekly_off` (patch đã chạy, đã đối soát).
- [ ] `Shift Type.holiday_list` không còn trên form.
- [ ] Hai tầng lịch tuần có nhãn nói rõ tầng nào thắng.
- [ ] Giờ định mức suy từ ca, đổi giờ ca thì định mức đổi theo — có test cho ca 7,5h.
- [ ] Định mức trừ ngày nghỉ phép.
- [ ] Không còn nơi nào ngoài `work_schedule` đọc `Holiday List` để suy ngày nghỉ.
- [ ] Report *Lịch hiệu lực của nhân viên* trả lời được ngày làm việc / giờ định mức / nguồn lịch.
- [ ] Cổng bất biến lương xanh; 6 phiếu thật 0 lệch.

## Out of scope

- **Tính công / lương của nửa ngày theo giờ** — `half_day_window` đợt này chỉ để hiển thị.
- **Nghỉ bù & OT** — `docs/spec/overtime-registration.md`.
- **Loại ngày thứ ba "Nghỉ không tính công"** (nghỉ ghép kiểu đổi ngày) — câu hỏi mở từ spec trước.
- **`api/roster.py` / `roster/`** — không dùng nữa.
- Nhiều công ty trong một site: `Work Calendar Settings` vẫn là Single một công ty.

## Open Questions

1. **Có giữ tầng lịch mặc định của công ty không?** Đề xuất **giữ** (lưới an toàn cho nhân viên chưa
   phân ca — đúng ca nhân viên C trong bộ dựng cảnh). Nếu muốn tuyệt đối một chỗ thì bỏ nó và bắt
   mọi ca phải khai, đổi lại: quên khai ca là nổ lỗi cấu hình thay vì chạy êm.
2. **Định mức trừ ngày nghỉ phép — trừ loại nào?** Đề xuất trừ **mọi ngày không đi làm** (phép, ốm,
   không lương, công tác vẫn tính là có mặt). Hay chỉ trừ nghỉ có lương?
3. **Giờ định mức của ngày làm bù** — tính bằng giờ ca của ngày đó (đề xuất), hay coi là ngày ngoài
   định mức?
