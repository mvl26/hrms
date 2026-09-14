# Spec — Số buổi ăn trưa ghi nhận trên Attendance (nguồn duy nhất)

Trạng thái: **Approved (design)** 2026-07-25 ("chạy tiếp"). Nhánh `feat/skip-attendance-diag`.
Liên quan: [[project-vn-payroll-mvl]], [[project-attendance-code-timekeeping]].

## 1. Vấn đề / hiện trạng

Phụ cấp ăn trưa (component **J**) trên phiếu lương **đã tự động** — engine đọc `count_lunch_days`
([lunch.py](../hrms/vn_payroll/lunch.py)) suy từ **checkin + chấm công**: ngày tính ăn khi là ngày
công (status Present/Half Day) VÀ checkin phủ giờ nghỉ trưa của ca (vào < lunch_start, ra ≥ lunch_end;
mặc định 12:00–13:30). Nhưng **số buổi ăn trưa chỉ lưu trên Salary Slip** (`custom_lunch_days`, tính
tại lúc lập phiếu) — **không ghi vào từng Attendance, không có trong report chấm công**.

## 2. Mục tiêu (user chốt)

Ghi số buổi ăn trưa thành **cờ per-Attendance**, làm **NGUỒN DUY NHẤT**: report chấm công, Bảng Công
Tháng (bản in ký), và phiếu lương đều **đếm từ cờ này** — một chỗ tính, khớp tuyệt đối, kiểm toán được.

**Giữ luật hiện tại:** ngày WFH / công tác / on-duty / quên chấm công (không có checkin phủ giờ trưa)
→ **không tính ăn** (ăn trưa = có mặt thực tế tại công ty). Override tay per-NV vẫn còn
(`custom_lunch_days_override` trên Salary Structure Assignment).

## 3. Thiết kế

### 3.1 Field trên Attendance
`Attendance-custom_lunch` (Check 0/1, nhãn "Ăn trưa") — fixture Custom Field + đồng bộ bộ lọc
`fixtures` trong hooks.py. Thuần dữ liệu; KHÔNG đụng `status`/`leave_type`/`half_day_status`.

### 3.2 Tính cờ (một luật)
Tách [lunch.py](../hrms/vn_payroll/lunch.py):
- `is_lunch_day(status, shift, day_checkin_datetimes) -> bool` — luật per-ngày (đúng luật hiện có).
- Attendance controller: method `set_lunch_flag()` gọi trong `before_validate` (sau bridge, khi status
  đã có) → đọc Employee Checkin của ngày đó → set `self.custom_lunch`. Tự chạy khi
  `process_auto_attendance` tạo/cập nhật Attendance và khi sửa tay.
- `count_lunch_days` cũ (quét checkin theo kỳ) → giữ làm **engine recompute** (dùng lại `is_lunch_day`).

### 3.3 Payroll đọc từ Attendance *(chạm lương — CỔNG KÝ)*
`count_lunch_days_from_attendance(employee, start, end)` = `Σ custom_lunch` (Attendance docstatus=1
trong kỳ). `apply_mvl`: `lunch_days = custom_lunch_days_override or count_lunch_days_from_attendance(...)`.
**GATE bắt buộc:** test bất biến — với cùng dữ liệu, `Σ cờ` (sau recompute) == `count_lunch_days` cũ
== `custom_lunch_days` trên 12 phiếu đã submit → phụ cấp J không đổi.

### 3.4 Report Bảng chấm công
`monthly_attendance_report.get_sheet_rows`: thêm `lunch_days` vào `totals` mỗi NV (Σ custom_lunch của
Attendance ngày công). Thêm cột "Số buổi ăn trưa" vào report.

### 3.5 Bảng Công Tháng (Monthly Attendance Sheet)
Thêm field `lunch_days` vào `Monthly Attendance Sheet Detail`; `populate_from_attendance` cộng
`custom_lunch`; print format ký thêm cột "Ăn trưa".

### 3.6 Làm mới khi checkin về muộn
Cờ tính lại mỗi lần Attendance lưu (validate hook — phủ luồng process_auto_attendance). Cho checkin
về muộn sau khi Attendance đã chốt: tiện ích `recompute_lunch_flags(month, year, company=None)`
(whitelist + bench execute) tính lại `custom_lunch` từ checkin (db_set, update_modified=False) — chạy
TRƯỚC khi chốt lương. **KHÔNG** gọi từ Bảng Công Tháng (giữ nguyên tắc "sheet không bao giờ ghi
Attendance"); report/sheet/payroll đều đọc cùng cờ đã lưu nên nhất quán tại thời điểm đọc.
`compute_lunch_flags_for_period` (thuần, không ghi) tách riêng để test.

### 3.7 Backfill *(data-migration — ASK-FIRST, không tự chạy)*
`hrms.vn_payroll.lunch.backfill_lunch_flags(dry_run=1)` set `custom_lunch` cho MỌI Attendance đã
submit từ checkin — chạy qua `bench execute` (KHÔNG đưa vào patches.txt để tránh auto-run khi migrate
việc khác). Idempotent, mặc định dry_run. Chỉ chạy trên `miyano` sau sign-off.

## 4. Cổng & phi mục tiêu
- **Payroll GATE** (§3.3): số buổi ăn trưa bất biến trước/sau — bắt buộc xanh.
- Test qua **rollback harness** (KHÔNG run-tests trên miyano); cờ test in-memory (bẫy DDL Custom Field).
- **Không tự deploy**: migrate fixture + `bench build` + restart + backfill = ask-first. Build+test trên nhánh.
- Không đánh dấu từng ô ngày trên lưới (user không chọn); chỉ tổng ở report + Bảng Công Tháng.

---

# Sửa đổi 2026-08-27 — tự chấm ăn trưa cho ngày không có checkin + chọn tay per-ngày

Trạng thái: **Approved** 2026-08-27. **Thay thế một phần §2** của bản gốc.

## 5.1 Vì sao đảo quyết định cũ

§2 chốt: "quên chấm công (không có checkin phủ giờ trưa) → **không tính ăn**". Vận hành thực tế cho
thấy luật đó phạt nhầm người: chấm công **tạo tay** và ngày **sửa qua soát công** đều không có
checkin, nên rơi hết về 0 — trong khi đó là những ngày HR đã xác nhận là ngày công đủ. Người có đi
làm, có ăn, nhưng không được phụ cấp.

Đo trên dữ liệu thật 7/2026 (108 ngày công): 2 ngày `X` Present bị mất suất ăn vì 0 và 1 lần chấm.

## 5.2 Hai lỗ hổng (một trong hai là bug thật)

1. **Chấm tay** — `set_lunch_flag()` chỉ suy từ checkin ⇒ không checkin thì luôn 0. *(Đúng spec cũ,
   nay đổi.)*
2. **Soát công** — `apply_correction` ghi bằng `frappe.db.set_value` với danh sách field cố định
   **không có `custom_lunch`**, và `db_set` không chạy `before_validate` ⇒ cờ **kẹt giá trị cũ**.
   *(Bug thật, spec cũ không lường.)* Đã thấy trên dữ liệu thật: 1 ngày `P` (On Leave) mang cờ
   `custom_lunch = 1` vì trước đó là `X` có checkin — **đang trả thừa** 35.000đ.

Và **không sửa tay được**: `custom_lunch` là `read_only`, mà kể cả bỏ read-only thì mỗi lần lưu
`before_validate` lại đè lại giá trị suy từ checkin.

## 5.3 Thiết kế — tách "ý muốn của người" khỏi "kết quả máy"

`custom_lunch` (Check, read-only) **giữ nguyên vai trò kết quả cuối** — mọi nơi đang đếm
(`lunch_days_for_period`, `lunch_days_map`, report, Bảng Công Tháng, phiếu lương) không sửa dòng nào.

Thêm **`Attendance-custom_lunch_override`** (Select `Tự động` | `Có` | `Không`, mặc định `Tự động`,
nhãn "Ăn trưa"). Chọn `Có`/`Không` là **quyết định của người, máy không bao giờ đè lại** — kể cả khi
lưu lại nhiều lần hay chạy `recompute_lunch_flags`.

## 5.4 Luật tự động mới — một hàm duy nhất trong `lunch.py`

```
override = "Có"    → 1
override = "Không" → 0
"Tự động":
    status ∉ (Present, Half Day)          → 0
    mã CT (công tác) / W (làm tại nhà)    → 0     # ăn ngoài / ở nhà
    ≥ 2 lần chấm  → luật cũ: vào < lunch_start VÀ ra ≥ lunch_end
    < 2 lần chấm  → Present → 1 ; Half Day → 0
```

Hai dòng cuối là toàn bộ phần mới:

- **0 lần chấm** (chấm tay, sửa soát công): đã công nhận Present thì mặc định có ăn.
- **1 lần chấm** (quên chấm ra): dữ liệu không đủ để kết luận; người vào từ sáng gần như chắc chắn
  ở lại ăn ⇒ theo mặc định của status, không phạt vì lỗi thao tác.
- **Half Day không checkin → 0**: giữ đúng nguyên tắc "theo checkin" — không có dấu thì không chứng
  minh được là ở lại qua trưa. (User chốt 2026-08-27.)
- **CT/W không bao giờ tính**: giữ nguyên tinh thần §2 — ăn ngoài, và công tác đã có Expense Claim.

## 5.5 Ba đường ghi phải cùng dùng luật đó

| Đường | Sửa gì |
|---|---|
| `Attendance.before_validate → set_lunch_flag()` | dùng luật mới, tôn trọng override |
| `attendance_review.apply_correction` | **thêm `custom_lunch` vào `db_set`**, tính lại theo mã mới — vá bug §5.2(2) |
| `lunch.recompute_lunch_flags` | tôn trọng override, để lượt tính lại trước khi chốt lương không xoá lựa chọn tay |

## 5.6 Cổng ký duyệt *(chạm lương)*

Ăn trưa vào thẳng phụ cấp **J** (35.000đ/buổi) → **đổi thực lĩnh**. Không phải field hiển thị.

Tác động đo được trên 7/2026: `+1` (X, 0 chấm) `+1` (X, 1 chấm) `−1` (P hết kẹt cờ sai) = **ròng +1
buổi = +35.000đ**, phần lớn là sửa sai.

Hai mốc ký riêng: **(a)** duyệt thiết kế để code — *đã có 2026-08-27*; **(b)** duyệt riêng lúc chạy
`recompute_lunch_flags` trên dữ liệu thật sau migrate.

## 5.7 Phi mục tiêu

- Không đổi cách đếm ở report / Bảng Công Tháng / phiếu lương — vẫn Σ `custom_lunch`.
- Không thêm cột sửa hàng loạt trên lưới soát công (user chọn ô 3 trạng thái trên phiếu, 2026-08-27).
- Không đụng `status` / `leave_type` / `half_day_status` → số công không đổi, chỉ phụ cấp ăn đổi.

## 5.8 Người miễn chấm công — ô tick trên hồ sơ (2026-08-27, sau data test)

Data test soát dữ liệu thật phát hiện tình huống §5.4 chưa lường: **20/20 ngày lệch của tháng 8
thuộc đúng 2 người *miễn chấm công*** (`hieu chu`, `Phạm Thị Dung` — người sau không chấm công lần
nào cả tháng). Với họ, `attendance_exempt.py` **tự sinh** `X` cho mọi ngày làm việc
(`Attendance.custom_auto_filled = 1`), nên luật "Present + không dấu chấm → có ăn" sẽ cấp phụ cấp
**mỗi ngày, tự động, vĩnh viễn**, không một bằng chứng nào là họ có mặt tại công ty.

**Quyết định (user, 2026-08-27):** thêm ô tick **"Tự chấm ăn trưa"**
(`Employee.custom_auto_lunch_when_exempt`, Check, mặc định TẮT) ngay dưới ô *Miễn chấm công (full
công)*, chỉ hiện khi ô đó được bật. Bật tick = người này thật sự lên văn phòng ⇒ ngày `X` tự sinh
được tính ăn trưa; để trống ⇒ ngày tự sinh không được tính.

Đặt quyết định ở **cấp con người** thay vì bắt HR sửa tay 20+ ngày mỗi tháng: tick một lần, data tự
chạy chuẩn từ đó.

**Vị trí trong luật** — chèn vào đúng nhánh "không đủ dấu chấm", SAU nhánh phủ giờ trưa:

```
≥ 2 dấu phủ giờ trưa            → 1     # BẰNG CHỨNG có mặt, thắng cả việc chưa bật tick
ngày tự sinh & chưa bật tick    → 0     # ← MỚI
< 2 dấu, còn lại                → luật §5.4
```

Thứ tự đó là cố ý: người miễn chấm công thỉnh thoảng vẫn quẹt thẻ (`hieu chu` có 4 dấu trong tháng
8); hôm nào có dấu phủ giờ trưa thì đó là bằng chứng thật, không cần tick.

**Ngày HR sửa qua soát công** cho người miễn chấm công vẫn giữ `custom_auto_filled = 1`, nên vẫn
theo tick. Muốn cấp riêng cho một ngày thì dùng ô **Ăn trưa = Có** của ngày đó — đúng việc mà
override sinh ra để làm.

**Kết quả sau khi áp:** tháng 8 lệch từ 20 ngày về **0**; tháng 6 còn đúng 1 ngày (ngày `X` chấm tay
của `hieu chu`, `custom_auto_filled = 0`, có 1 dấu chấm buổi sáng) — đúng luật, không liên quan tick.
