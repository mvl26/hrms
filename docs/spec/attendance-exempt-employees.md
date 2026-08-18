# Spec — Nhân viên miễn chấm công (full công tự sinh)

Trạng thái: **Implemented** — 2026-08-18 (147 test xanh trên 9 module VN, cổng bất biến lương qua).
Thiết kế duyệt 2026-08-13. Nhánh: `feat/skip-attendance-diag`.
Liên quan: [[project-attendance-code-timekeeping]], [[project-flex-shift-timekeeping-pipeline]],
[[project-timekeeping-logic-2026-07]], [[project-vn-payroll-mvl]], [[project-attendance-request-locked]].
Spec nền: `docs/spec/flex-shift-and-timekeeping-pipeline.md`, `docs/spec/attendance-request-vs-leave.md`,
`docs/spec/business-trip-workflow.md`.

## 1. Vấn đề

Một số người ở Miyano **không quẹt thẻ theo giờ cố định**: giám đốc, người giữ chức vụ quản lý cấp
cao, người có giờ làm việc không cố định. Công của họ là **công khoán theo tháng** — cứ ngày làm
việc là đủ công, không phụ thuộc lượt chấm. Nhưng họ vẫn **đi công tác** và vẫn **xin nghỉ phép**
như mọi người, và những ngày đó phải hiện đúng **CT** / **P** trên bảng chấm công.

Hệ thống hiện tại không có khái niệm này. Tuyến sinh công chỉ có hai nguồn:

| Nguồn | Cơ chế | Người không quẹt thẻ nhận được gì |
|---|---|---|
| Có lượt chấm | `Shift Type.process_auto_attendance` (`shift_type.py:97`) | không có lượt chấm → không chạy |
| Không có lượt chấm | `mark_absent_for_dates_with_no_attendance` (`shift_type.py:236`) | **chấm `Absent` → mã V** |

⇒ Giám đốc không quẹt thẻ **bị chấm vắng cả tháng**, và vì `payroll_based_on = Attendance`,
`Absent` **trừ thẳng `payment_days` trên phiếu lương**. Cách chữa tay duy nhất hôm nay là HR nhập
tay từng ngày hoặc Cancel → Amend từng bản ghi.

Hai cái bẫy phụ, đã kiểm trên site 2026-08-13:

- **Phân ca cấp theo từng tháng.** `Shift Assignment` hiện có cho 6/2026 và 7/2026, **8/2026 chưa
  có bản nào**. Bất kỳ giải pháp nào lệ thuộc phân ca (vd. tạo một "Ca miễn chấm công") sẽ mất công
  ngay tháng nào HR quên phân ca — chính tháng này.
- **Công Tác không ghi đè ngày đã có bản ghi.** `create_travel_attendance` bỏ qua ngày đã có
  Attendance (`business_trip.py:98`, `has_attendance` ở `:114`). Nếu ta tự sinh **X** hằng ngày thì
  chuyến công tác duyệt sau sẽ **không bao giờ ghi được CT** — vi phạm đúng yêu cầu của tính năng.
  (Nghỉ phép và Yêu cầu chấm công thì ngược lại: cả hai **ghi đè** bản ghi sẵn có —
  `leave_application.py:279`, `attendance_request.py:89` — nên hai kênh đó an toàn.)

## 2. Phạm vi

**Trong phạm vi:** một cờ trên hồ sơ nhân viên; một module giữ luật sinh công; bốn điểm móc vào
tuyến chấm công sẵn có; sửa Công Tác để CT thắng ngày X tự sinh; nút chạy bù theo tháng.

**Ngoài phạm vi (YAGNI):** mã công mới (dùng **X** như đi làm bình thường); doctype cấu hình riêng;
nhiều đoạn hiệu lực (chỉ một ngày "từ"); miễn chấm công theo chức vụ hay theo phòng ban; đụng vào
Bảng Công Tháng (nó là ảnh chụp, không ghi ngược); đụng vào công thức lương.

## 3. Thiết kế

### 3.1 Cờ nhận diện — hai custom field trên Employee (fixtures)

| Fieldname | Kiểu | Label | Ghi chú |
|---|---|---|---|
| `custom_exempt_from_checkin` | Check | Miễn chấm công (full công) | `insert_after = "default_shift"` |
| `custom_exempt_from_checkin_from` | Date | Miễn chấm công từ ngày | `depends_on = "custom_exempt_from_checkin"` |

Ngày hiệu lực trống ⇒ tính từ **ngày vào làm**. Bỏ tick chỉ **dừng sinh mới**, không xoá ngày công
đã sinh (lịch sử là dữ liệu đã chốt, không tự viết lại).

Cả hai vào `hrms/fixtures/custom_field.json` **và** danh sách lọc `fixtures` trong `hooks.py:292`
(`test_setup_vn_defaults.py` bắt buộc hai nơi khớp nhau).

### 3.2 Cờ nguồn gốc trên Attendance

| Fieldname | Kiểu | Label | Ghi chú |
|---|---|---|---|
| `custom_auto_filled` | Check, `read_only=1`, `print_hide=1` | Công tự sinh (miễn chấm công) | `insert_after = "custom_lunch"` |

Đây là **cờ nguồn gốc**, không phải cờ hiển thị: nó cho phép Công Tác phân biệt "ngày X do hệ thống
khoán" (được phép ghi đè thành CT) với "ngày X do người thật quẹt thẻ hoặc HR nhập tay" (không được
đụng). Không có nó thì Công Tác chỉ còn cách đoán qua `in_time is null`, mà ngày WFH hợp lệ cũng
không có giờ vào — đoán sai là ghi đè lên dữ liệu thật.

### 3.3 Module giữ luật: `hrms/hr/attendance_exempt.py`

Một nơi duy nhất biết "ai được miễn, ngày nào, sinh ra cái gì". Bốn điểm móc ở §3.4 chỉ gọi vào đây.

```python
EXEMPT_CODE = "X"          # mã công của ngày tự sinh
BACKFILL_DAYS = 31         # cửa sổ lùi tối đa của lượt quét tự động (một kỳ công)

def is_exempt(employee: str, date) -> bool
def exempt_employees() -> list[dict]              # Active + có cờ, kèm DOJ / hiệu lực / relieving
def fill_full_day(employee: str, date) -> str | None   # -> tên Attendance, hoặc None nếu bỏ qua
def process_exempt_employees()                    # scheduler hourly_long
@frappe.whitelist()
def generate_for_month(month, year, employee=None) -> int   # nút chạy bù
```

**`is_exempt(employee, date)`** — True khi tất cả đúng:

1. `Employee.custom_exempt_from_checkin = 1` và `status = "Active"`;
2. `date >= max(date_of_joining, custom_exempt_from_checkin_from or date_of_joining)`;
3. `relieving_date` trống hoặc `date <= relieving_date`.

Đọc **phòng thủ**: `frappe.get_meta("Employee").has_field(...)` — site chưa migrate fixtures thì trả
False, tức toàn bộ tính năng im lặng và hành vi cũ y nguyên (cùng khuôn với
`get_split_shift_config` ở `attendance.py:129`). Cache theo request bằng `frappe.cache` cục bộ để
lượt quét không hỏi DB mỗi ngày mỗi người.

**`fill_full_day(employee, date)`** — bỏ qua (trả `None`) khi bất kỳ điều nào đúng:

| Điều kiện bỏ qua | Vì sao |
|---|---|
| Đã có Attendance ngày đó (`docstatus < 2`) | không đè lên dữ liệu đã có — kể cả V do HR cố ý chấm |
| Ngày thuộc Holiday List của nhân viên (T7/CN/lễ) | ngày nghỉ không có công; lễ đã được `paid_holidays_in_period` trả riêng |
| `is_period_locked(employee, date)` (`period_lock.py:50`) | kỳ đã chốt là đóng băng |
| Có Yêu cầu chấm công đã duyệt phủ ngày đó | gọi `reapply_attendance_request` trước rồi thôi — đơn đã duyệt thắng |
| `is_exempt` False | không phải người được miễn |

Còn lại thì tạo Attendance: `custom_attendance_code = "X"`, `custom_auto_filled = 1`, `shift =`
`default_shift` của nhân viên (có thể trống), `company` từ hồ sơ → **cầu nối mã công**
(`apply_attendance_code_bridge`, `attendance.py:206`) tự suy ra `status = "Present"`,
`custom_work_credit = 1.0` → `insert()` + `submit()` + Comment "Tự sinh: nhân viên miễn chấm công".

Không tự đặt `status` bằng tay: **mã công là đầu vào duy nhất**, native fields là đầu ra của cầu
nối. Đặt cả hai là mở đường cho hai nguồn sự thật lệch nhau.

**`process_exempt_employees()`** — vào `scheduler_events["hourly_long"]` (`hooks.py:207`), **đặt
SAU** `shift_type.process_auto_attendance_for_all_shifts`. Với mỗi người có cờ, quét
`[max(hôm qua − BACKFILL_DAYS, hiệu lực, DOJ) … min(hôm qua, relieving_date)]` và gọi
`fill_full_day` từng ngày. Không quét ngày hôm nay: ngày chưa hết thì chưa kết luận được.

Cửa sổ 31 ngày là **chốt chặn chi phí**, không phải quy tắc nghiệp vụ: bật cờ cho người vào làm từ
2020 mà không giới hạn thì lượt quét cày sáu năm lịch sử. Muốn bù xa hơn → dùng
`generate_for_month` (§3.6), có chủ đích và có số ngày trả về để đối chiếu.

### 3.4 Bốn điểm móc vào tuyến sẵn có

**(a) Thay chấm vắng bằng full công** — `shift_type.mark_absent_for_dates_with_no_attendance`
(`shift_type.py:225`): trong vòng lặp, ngay sau nhánh `reapply_attendance_request`, nếu
`is_exempt(employee, date)` → `fill_full_day` rồi `continue`, thay cho `mark_attendance(..., "Absent")`.

Điểm móc này **bắt buộc phải có** dù §3.3 đã có lượt quét riêng: cả hai chạy trong cùng một lượt
`hourly_long`, và `process_auto_attendance_for_all_shifts` chạy **trước**. Không chặn ở đây thì V
được ghi trước, lượt quét đến sau thấy "đã có bản ghi" và bỏ qua — người có phân ca vẫn vắng cả
tháng. Nhánh này cũng thừa hưởng nguyên các lá chắn của upstream: bỏ ngày lễ/T7/CN, bỏ ngày đã có
bản ghi, tôn trọng DOJ / ngày nghỉ việc, bỏ kỳ đã chốt (`get_dates_for_attendance`, `:251`).

**(b) Lượt quét độc lập với phân ca** — `process_exempt_employees` ở §3.3. Đây là phần trả lời cái
bẫy "8/2026 chưa phân ca": nhánh (a) chỉ chạm những người `get_assigned_employees` trả về, nhánh
(b) chạm mọi người có cờ. Hai nhánh **idempotent** với nhau vì `fill_full_day` bỏ qua ngày đã có
bản ghi; thứ tự chạy không quan trọng.

**(c) Có quẹt thẻ cũng không bị hạ mã** — hai chỗ:

- `shift_type.process_auto_attendance` (`:115`): sau khi `get_attendance()` trả kết quả, nếu
  `is_exempt` → ép `attendance_status = "Present"`. Không có bước này thì giám đốc ghé một tiếng bị
  ngưỡng `working_hours_threshold_for_absent` (`:200`) quy thành **Absent**.
- `Attendance.apply_vn_half_day_classifier` (`attendance.py:152`): vẫn chạy `classify_day` để
  `working_hours` có số thật (báo cáo giờ làm việc cần), nhưng nếu `is_exempt` thì ghi
  `custom_attendance_code = EXEMPT_CODE` thay vì `ket_qua.code` (`:204`). Bộ phân loại đã return
  sớm khi ngày có `leave_type` / `On Leave` (`:166`) nên nhánh này không bao giờ chạm ngày nghỉ.

**(d) Nửa ngày nghỉ phép không bị trừ nửa còn lại** — `shift_type.mark_absent_for_half_day_dates`
(`shift_type.py:371`) ép `half_day_status = "Absent"` cho ngày Half Day có `modify_half_day_status = 1`,
tức "nửa còn lại vắng vì không có lượt chấm". Với người miễn chấm công, nửa còn lại **là công** →
bỏ qua nhân viên có cờ. Đây là điểm chạm lương trực tiếp: `get_half_absent_days` đọc
`half_day_status` để trừ 0,5 công.

Điểm móc này là **phòng thủ**, không phải đường chạy chính: `modify_half_day_status = 1` chỉ được
đặt khi đơn nghỉ lật một ngày đang **Absent** thành Half Day, mà người có cờ thì ngày đó đã là
Present (X). Giữ nó vì rẻ và vì một ngày V nhập tay rồi xin nghỉ nửa ngày sau đó là đúng kịch bản
đó. Test #6 phải xanh **trước và sau** khi thêm guard — nếu nó xanh sẵn thì guard chỉ là lưới an toàn.

### 3.5 Công Tác phải thắng ngày X tự sinh

`business_trip.has_attendance` (`business_trip.py:114`) đang trả True cho mọi bản ghi `docstatus < 2`.
Sửa thành: bản ghi có `custom_auto_filled = 1` **và không có `in_time`/`out_time`** thì coi như ô
trống — `create_travel_attendance` **cập nhật** nó thay vì bỏ qua. Mọi bản ghi khác giữ nguyên hành
vi cũ.

Bản ghi X tự sinh **đã submit**, mà không field mã công nào có `allow_on_submit = 1` (kiểm
`fixtures/custom_field.json` 2026-08-13: cả 5 field Attendance đều `= 0`) ⇒ `save()` sẽ ném lỗi và
cầu nối không thể chạy lại. Dùng đúng khuôn đã có trong repo — `db_set` trên bản đã submit, y như
`leave_application.create_or_update_attendance` (`leave_application.py:279`) và
`attendance_request_miyano.set_attendance_request_code`:

```
db_set: custom_attendance_code = "CT", status = "Work From Home", custom_auto_filled = 0
```

`custom_work_credit` **không phải đổi**: X và CT đều `work_fraction = 1.0`, `is_paid = 1`. Và
`Present → Work From Home` **không đụng lương** — payroll chỉ trừ theo `Absent` / `Half Day` /
`leave_type` thuộc LWP, cả hai status này đều là ngày công có lương. Thêm Comment truy vết như các
kênh khác.

Nghỉ phép và Yêu cầu chấm công **không cần sửa gì** — cả hai đã ghi đè bản ghi sẵn có, và
`resync_code_after_leave_record` (`attendance.py:246`) suy lại mã sau khi đơn nghỉ lật status.

### 3.6 Chạy bù theo tháng

`generate_for_month(month, year, employee=None)` — whitelisted, quyền HR Manager. Dùng khi bật cờ
giữa chừng, khi hủy chốt kỳ để sửa, hoặc khi cửa sổ 31 ngày không phủ hết. Trả về **số ngày đã
sinh** để đối chiếu. Nút "Sinh công tháng (miễn chấm công)" đặt trong menu của danh sách Attendance
(`attendance_list.js`), hỏi tháng/năm/nhân viên trước khi chạy.

### 3.7 Luật ngày — bảng tổng hợp

| Tình huống của người có cờ | Kết quả |
|---|---|
| Ngày làm việc, không quẹt thẻ | **X**, Present, công 1,0 |
| Ngày làm việc, có quẹt thẻ (bất kể mấy giờ) | **X**, Present, công 1,0 — `in/out/working_hours` ghi thật cho báo cáo |
| T7 / CN / ngày lễ | **không sinh bản ghi** (như mọi người) |
| Nghỉ phép cả ngày (đơn duyệt) | **P** / mã theo loại nghỉ, đơn ghi đè ngày X đã sinh |
| Nghỉ phép nửa ngày | **1/2P** — nửa còn lại là công (Present), không bị trừ |
| Đi công tác (Công Tác duyệt) | **CT** — ghi đè ngày X tự sinh (§3.5) |
| Yêu cầu chấm công đã duyệt | mã của đơn (W / CT / X), đơn thắng |
| HR nhập tay V / K | **giữ nguyên** — người thật quyết định thắng máy |
| Ngày thuộc kỳ đã chốt | không đụng |
| Ngày trước ngày hiệu lực / trước DOJ / sau ngày nghỉ việc | không sinh |

## 4. Ảnh hưởng lương (gate ký duyệt)

Đây là thay đổi **cố ý làm đổi số lương**, đã được thống nhất 2026-08-13: người có cờ trước đây bị
chấm V (trừ `payment_days`), sau tính năng thành Present (đủ công). Ràng buộc phải chứng minh bằng
test trước khi deploy:

1. **Người KHÔNG có cờ: `payment_days` / `absent_days` / LWP y hệt trước và sau.** Đây là bất biến
   cứng — tính năng chỉ được chạm đúng những người được tick.
2. **Người CÓ cờ:** tổng công tháng = số ngày làm việc trong tháng (theo Holiday List); ngày nghỉ
   phép vẫn trừ theo loại nghỉ; nghỉ không lương vẫn trừ; nửa ngày phép chỉ trừ 0,5.
3. Phiếu lương của kỳ **đã chốt công** không đổi (tính năng không đụng kỳ khoá).

**Hệ quả đã biết, chấp nhận:** ngày tự sinh **không có suất ăn trưa**. `lunch_flag_for_attendance`
(`vn_payroll/lunch.py:74`) đếm suất từ lượt quẹt thẻ; không quẹt thì `custom_lunch = 0`. Đúng bản
chất "không ăn trưa tại công ty thì không tính suất". Nếu Miyano muốn người miễn chấm công vẫn được
suất ăn thì đó là **quy định riêng, làm sau**, không gói vào tính năng này.

## 5. Kiểm thử

Chạy bằng **rollback harness** (savepoint mỗi test, `frappe.db.commit` bị vô hiệu) — **tuyệt đối
không** `bench --site miyano run-tests`. File: `hrms/hr/tests/test_attendance_exempt.py` (+ bổ sung ca
Công Tác vào test sẵn có của Business Trip).

| # | Ca kiểm | Kỳ vọng |
|---|---|---|
| 1 | có cờ, ngày làm việc, không quẹt thẻ | 1 Attendance: X / Present / work_credit 1,0 / `custom_auto_filled = 1` |
| 2 | có cờ, T7 + CN + ngày lễ | không sinh bản ghi nào |
| 3 | có cờ, quẹt thẻ 10:00–11:00 | vẫn X / Present (không 1/2K, không Absent), `working_hours` = giờ thật |
| 4 | có cờ, ngày đã có V do HR nhập tay | giữ nguyên V |
| 5 | có cờ, đơn nghỉ phép duyệt SAU khi đã sinh X | thành P / On Leave, mã resync đúng |
| 6 | có cờ, nghỉ phép nửa ngày | 1/2P, `half_day_status = "Present"`, trừ đúng 0,5 công |
| 7 | có cờ, Công Tác duyệt SAU khi đã sinh X | thành **CT**, `custom_auto_filled` bị xoá |
| 8 | có cờ, Công Tác trên ngày có quẹt thẻ thật | **không** ghi đè (hành vi cũ giữ nguyên) |
| 9 | có cờ, ngày thuộc kỳ đã chốt | không sinh, không ném lỗi |
| 10 | có cờ nhưng **không có phân ca** tháng đó | vẫn có đủ công (nhánh (b)) |
| 11 | có cờ, ngày trước `custom_exempt_from_checkin_from` | không sinh |
| 12 | **không** có cờ, không quẹt thẻ | vẫn Absent / V — bất biến |
| 13 | chạy lượt quét hai lần | không sinh bản ghi trùng (idempotent) |
| 14 | `generate_for_month` cho tháng quá khứ | sinh đủ ngày làm việc, trả đúng số đếm |
| 15 | fixtures chưa migrate (field chưa có) | `is_exempt` = False, toàn bộ hành vi cũ y nguyên |
| 16 | **payroll**: 2 NV (1 có cờ, 1 không), so `payment_days`/`absent_days`/LWP trước-sau | người không cờ: bằng nhau tuyệt đối; người có cờ: đúng số ngày làm việc |

## 6. Triển khai

1. `bench --site miyano migrate` (nạp 3 custom field qua fixtures) — **ask-first**, theo CLAUDE.md.
2. Tick cờ cho đúng những người đã thống nhất (hiện site có 1 "Giám đốc"), điền ngày hiệu lực.
3. Chạy `generate_for_month` cho tháng hiện tại, đối chiếu bảng chấm công trước khi chốt kỳ.
4. Lượt quét tự động tiếp quản từ chu kỳ `hourly_long` kế tiếp.

Toàn bộ thay đổi là **additive** và `git revert`-able: gỡ commit ⇒ mất cờ và lượt quét, các bản ghi
X đã sinh vẫn là Attendance hợp lệ (mã X, Present) — không có dữ liệu nào trở thành rác.

## 7. Quyết định mở

- **Suất ăn trưa cho ngày tự sinh** — mặc định *không tính* (§4). Đổi ý thì sửa `is_lunch_day`,
  không sửa tính năng này.
- **Ngày lễ** — không sinh bản ghi, hưởng lương qua `paid_holidays_in_period` như mọi người. Nếu
  sau này muốn thấy ngày lễ trên bảng công của họ thì đó là thay đổi chung cho toàn công ty.
- **Người có cờ có được xin nghỉ không lương không** — có, và vẫn bị trừ. Cờ chỉ nói "không cần
  quẹt thẻ", không nói "không bao giờ trừ công".
