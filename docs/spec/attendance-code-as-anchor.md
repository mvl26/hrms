# Spec — Mã công là neo: loại nghỉ tự do, mã công ép đúng

Trạng thái: **Approved** — thiết kế duyệt 2026-08-24. Nhánh: `feat/skip-attendance-diag`.
Liên quan: [[project-attendance-code-timekeeping]], [[project-leave-single-pool]],
[[project-timekeeping-logic-2026-07]].
Spec nền: `docs/spec/attendance-code-timekeeping.md`, `docs/spec/leave-single-pool-vn.md`,
`docs/spec/leave-type-attendance-code-sync.md`, `docs/spec/bang-cong-thang-doctype.md`.

## 1. Vấn đề

Yêu cầu của Miyano: **mã công là gốc**. Mã công đã chuẩn theo quy định, nên một mã ứng với đúng
một loại nghỉ hoặc một loại công, và HR phải **tạo được bao nhiêu Loại nghỉ tuỳ ý** — không bị bó
vào bộ loại nghỉ hệ thống sinh ra (bộ đó có thể sai, có thể phải thay).

Hôm nay mã công đã là gốc cho việc **suy ra** mã và số công, nhưng **không có gì bảo đảm** nó đúng.
Tạo một Loại nghỉ mới rồi nộp đơn nghỉ theo loại đó là ra ngày công sai, im lặng.

### 1.1 Đã tái hiện trên site (2026-08-24, harness rollback, không ghi gì)

Loại nghỉ tạo tay không gắn mã, đối chứng với `Nghỉ phép năm`:

| Tình huống | Loại nghỉ tạo tay | `Nghỉ phép năm` |
|---|---|---|
| Ngày chưa có chấm công | status `On Leave`, **mã `None`, CÔNG = 0**, bảng công **ô trống** | mã `P`, CÔNG = 1 |
| Ngày đã có bản ghi Vắng | status `On Leave`, **mã `V` kẹt lại, CÔNG = 0**, bảng công hiện **V** | mã `P`, CÔNG = 1 |

Đường thứ hai nguy hiểm hơn: lương đọc `status` nên tính là nghỉ, bảng công hiện **V** — hai bên
nói ngược nhau. Thêm đúng một dòng `Attendance Code` trỏ tới loại nghỉ đó là cả hai đường tự đúng
(đã kiểm chứng: mã hiện đúng, CÔNG = 1). Nghĩa là **thiếu master data, không phải lỗi logic** —
nhưng hệ thống không nói cho ai biết là đang thiếu.

### 1.2 Ba tầng hở

**Tầng 1 — Leave Type → Attendance Code không bắt buộc.**
`leave_type_code.warn_if_unmapped` chỉ `msgprint` màu cam, không chặn. Bỏ qua cảnh báo là xong.

**Tầng 2 — `Attendance Code.category` mới là điểm mở rộng thật, mà nó là `Data` tự do.**
`category` quyết định ngày đó rơi vào cột nào và có vào "Tổng công" hay không. Tập giá trị hợp lệ
bị chép cứng ở **năm chỗ**, không chỗ nào biết chỗ nào — còn bản thân doctype thì không ràng buộc
gì cả:

| Chỗ | Hằng | Hậu quả nếu category lạ |
|---|---|---|
| `monthly_attendance_report.py:59` | `REPORT_CATEGORIES` | không có cột → số ngày **biến mất** khỏi báo cáo |
| `monthly_attendance_report.py:255` | `NON_PAID_LEAVE_CATEGORIES` | rơi nhầm vào/ra khỏi "Tổng công" |
| `monthly_attendance_report.py:75` | `CATEGORY_STATE` | ô không được tô màu |
| `monthly_attendance_sheet.py:160` | `category_field` | Bảng Công Tháng **schema cột cố định** → rơi khỏi bản in đã chốt |
| `attendance_legend.py:29` | `CATEGORY_ORDER` | mã tụt xuống cuối chú thích |
| `attendance_code.json` | (không có ràng buộc) | gõ sai một ký tự là hỏng cả năm chỗ trên |

Gõ `"Phep"` thay vì `"Phép"` thì mã vẫn hiện đúng trên từng ngày, công từng ngày vẫn đúng, nhưng
ngày đó **lặng lẽ rơi khỏi mọi cột tổng**. Không lỗi, không cảnh báo.

**Tầng 3 — hằng cứng `POOL_LEAVE_TYPE = "Nghỉ phép năm"`.**
`leave_single_pool.POOL_REASONS` map `"Nghỉ phép năm" → "P"` bằng hằng số. Đã kiểm chứng: đường này
cho **đúng cùng kết quả** với `code_for_leave_type()` tra bảng `Attendance Code`. Tức là hằng cứng
đã thừa — nó chỉ còn tác dụng bắt HR chọn trường "Loại nghỉ" trên đơn. Thay `Nghỉ phép năm` bằng
loại nghỉ khác thì nhánh đặc biệt này im lặng ngừng áp dụng.

## 2. Phạm vi

**Trong phạm vi:** một module giữ tập `category` chuẩn; validate cho `Attendance Code`; chống cướp
mã ở form Loại nghỉ; chốt chặn ở Đơn xin nghỉ; gỡ hằng cứng `POOL_*`; cảnh báo loại nghỉ chưa gắn
mã ở `ensure_defaults`.

**Ngoài phạm vi (YAGNI):**
- Doctype `Attendance Category` với cột động — đã cân nhắc và loại: `Monthly Attendance Sheet
  Detail` là child table **submittable** với cột cứng, đổi schema sẽ đụng các kỳ đã chốt và bản in.
- Tách `Nghỉ kết hôn` (`CODE_OWN_BUCKET`) thành một category thật — ngoại lệ có chủ đích, HR chốt
  2026-08-04, đổi sẽ kéo theo màu ô. Giữ nguyên.
- Backfill / patch dữ liệu — thiết kế này **không sửa bản ghi nào**.
- Bỏ trường `custom_leave_reason` — giữ lại làm dấu vết lịch sử, chỉ thôi bắt buộc.

## 3. Thiết kế

### 3.1 `hrms/hr/attendance_category.py` — tập category chuẩn, khai một chỗ

```python
CATEGORIES = ("Công", "Phép", "Ốm", "Thai sản", "Tai nạn LĐ",
              "Nghỉ bù", "Việc riêng", "Không lương", "Vắng")
```

Thứ tự đọc từ trái sang là đi từ "trả đủ" tới "không trả" — đúng thứ tự chú thích đang dùng.
Chín giá trị này khớp **đúng** dữ liệu hiện có trên site (đã kiểm: không có category lạ, không có
lỗi gõ), nên đây là thay đổi khép kín, không cần nắn dữ liệu.

Ràng buộc:

- `Attendance Code.category` đổi từ `Data` → `Select` với đúng chín tuỳ chọn này, và **bắt buộc**
  (`reqd = 1`). Frappe tự chặn giá trị ngoài danh sách khi lưu → không thể gõ sai nữa.
- `attendance_legend.CATEGORY_ORDER` xoá, import từ đây.
- Một test ép **năm nơi tiêu thụ không được lệch** với `CATEGORIES`:
  - tuỳ chọn trong `attendance_code.json` == `CATEGORIES`;
  - mọi category có mặt trong `CATEGORY_STATE` (nếu không thì ô không có màu);
  - mọi category **trừ `Công`** có một cột trong `category_field` của Bảng Công Tháng — `Công` cố
    ý không có cột riêng, nó gộp vào `Tổng công`;
  - mọi mục trong `REPORT_CATEGORIES` là một category hợp lệ hoặc một bucket đã biết
    (`BUCKET_MARRIAGE`);
  - mọi mục trong `NON_PAID_LEAVE_CATEGORIES` là một category hợp lệ.

Test này là thứ khiến "thêm category" trở thành việc **không thể làm nửa vời**: thêm vào
`CATEGORIES` mà quên cột hay quên màu là test đỏ ngay.

### 3.2 `Attendance Code` có validate — ép "1 mã ↔ 1 loại"

`AttendanceCode` hiện là `class AttendanceCode(Document): pass`. Thêm `validate`:

1. **Duy nhất theo cặp** — không được có hai mã cùng `(maps_to_status, leave_type)` khi `leave_type`
   có giá trị. Đây chính là bất biến "1 code chỉ tương ứng 1 loại nghỉ" mà HR yêu cầu; nó cũng là
   thứ khiến `_pick_reverse_code` không bao giờ phải đoán.
2. **`category` bắt buộc** (qua `reqd = 1` ở §3.1) — mã không có nhóm thì `is_paid_leave` coi nó là
   nghỉ CÓ LƯƠNG (vì `None` không nằm trong `NON_PAID_LEAVE_CATEGORIES`) và lặng lẽ cộng vào
   "Tổng công", đồng thời ô không có màu. Đây là lỗ thật, đóng luôn.

**Đã cân nhắc và LOẠI: bắt buộc `leave_type` khi `maps_to_status = "On Leave"`.** Nghe hợp lý nhưng
mâu thuẫn với chính luồng đang chạy: ô "Mã công cả ngày" trên form Loại nghỉ chọn một mã **đã tồn
tại**, nên mã bắt buộc phải tạo được lúc chưa gắn loại nghỉ nào (`test_leave_type_code.py` dựng
đúng kịch bản đó với mã `ZZ`/`YY`). Lại là bế tắc con-gà-quả-trứng, lần này ở chiều ngược lại. Bất
biến "không có ngày nghỉ nào thiếu mã" đã được chốt chặn ở Đơn xin nghỉ (§3.4) lo — đúng chỗ nó
đáng được lo.

Cả hai luật đều đúng với 17 mã đang có trên site, nên `bench migrate` re-sync fixtures không vỡ.
Một test khẳng định điều đó. `category` thành bắt buộc thì **13 chỗ dựng `Attendance Code` trong
test** (`vn_test_utils.py`, `test_attendance_code.py`, `test_lunch_flag.py`, `test_leave_type_code.py`)
phải bổ sung nhóm — việc cơ học, nằm trong cùng task.

### 3.3 Loại nghỉ — cảnh báo đỏ, và chống cướp mã

`leave_type_code.sync_code_to_leave_type` hiện ghi thẳng `Attendance Code.leave_type = <loại nghỉ
đang lưu>`. **Bẫy có thật:** HR tạo loại nghỉ mới để thay `Nghỉ phép năm` và chọn luôn mã `P` →
`P` bị gỡ khỏi `Nghỉ phép năm`, mọi ngày phép cũ mất đường tra ngược. Sửa: nếu mã đang thuộc **một
loại nghỉ khác**, `throw` kèm tên loại nghỉ đang giữ, thay vì im lặng chuyển chủ.

`warn_if_unmapped` nâng từ cam lên **đỏ**, và nói rõ hệ quả ("ngày nghỉ theo loại này sẽ ra 0 công")
kèm đúng việc phải làm. Vẫn **không chặn** — mã cần loại nghỉ tồn tại trước mới trỏ tới được, chặn
ở đây là bế tắc con-gà-quả-trứng.

`setup_vn_defaults.ensure_defaults` (chạy mỗi `after_migrate`) thêm một cảnh báo liệt kê mọi Loại
nghỉ chưa có mã cả ngày nào trỏ tới — để lỗi lộ ra lúc deploy chứ không phải lúc in bảng công.

### 3.4 Đơn xin nghỉ — chốt chặn thật

Đây là chỗ duy nhất chặn được mà không bế tắc: lúc này cả loại nghỉ lẫn mã đều đã có cơ hội tồn tại.

Trong `before_validate` của Leave Application: loại nghỉ của đơn **phải** có mã ứng với trạng thái
mà đơn sẽ sinh ra, nếu không thì `throw` kèm hướng dẫn:

| Đơn | Mã bắt buộc phải có |
|---|---|
| nghỉ cả ngày | một mã `maps_to_status = On Leave` trỏ tới loại nghỉ đó |
| nghỉ nửa ngày (`half_day = 1`) | thêm một mã `maps_to_status = Half Day` trỏ tới loại nghỉ đó |

**`before_validate`, không phải `validate`** — điểm này quan trọng và đã kiểm trong mã Frappe:
`Document.hook` (`frappe/model/document.py`) chạy method của controller **trước** rồi mới tới hook
`doc_events`. Gắn vào `validate` thì `LeaveApplication.validate()` của upstream (số dư phép, trùng
đơn, ngày lễ) nổ trước — người dùng thấy sai nguyên nhân, và test thì xanh vì nhầm lý do. Thiếu mã
công là vấn đề gốc hơn hết phép, phải báo trước.

Hôm nay chỉ `Nghỉ phép năm` (`1/2P`) và `Nghỉ không lương` (`1/2K`) có mã nửa ngày. Dữ liệu hiện
tại **không có** đơn nghỉ nửa ngày theo loại khác nên không đơn nào đang chạy bị chặn, nhưng đây là
thay đổi hành vi nhìn thấy được — xem §5.

### 3.5 Gỡ hằng cứng: mọi loại nghỉ đi chung một đường

Xoá `POOL_LEAVE_TYPE`, `POOL_REASONS`, `HALF_DAY_CODE`, `resolve_reason_code`. Sau khi duyệt đơn,
mã ghi lên Attendance suy **thuần từ bảng `Attendance Code`**, cùng một đường cho mọi loại nghỉ:

```python
code = code_for_leave_type(doc.leave_type, "Half Day" if is_half_day_that_date else "On Leave")
```

`Nghỉ phép năm` thôi là trường hợp đặc biệt trong code. Cặp `P`/`1/2P` và `K`/`1/2K` sẵn có nên
kết quả không đổi — điều này được một test đối chứng khẳng định.

Hệ quả kéo theo:

- `custom_leave_reason` thôi bắt buộc; trường và dữ liệu cũ **giữ nguyên**. Tên loại nghỉ còn bị
  chép cứng ở hai chỗ nữa, cả hai phải gỡ: `depends_on` / `mandatory_depends_on` của trường trong
  `hrms/fixtures/custom_field.json` (`eval:doc.leave_type=='Nghỉ phép năm'`) và
  `frontend/src/views/leave/Form.vue:270`.
- `custom_half_day_period` thôi là điều kiện để nhận ra "nửa ngày" (nay dùng `half_day` +
  `half_day_date`), nhưng **vẫn bắt buộc** khi `half_day = 1`. Đây không phải luật mới: fixture của
  trường đã khai `mandatory_depends_on = eval:doc.half_day` cho **mọi** loại nghỉ, và
  `setHalfDayPeriodVisibility` trong PWA cũng vậy. Chỉ có chốt phía server là đang hẹp hơn khai
  báo — nay nó khớp lại.
- Module `leave_single_pool.py` sau khi rút ruột chỉ còn việc "suy mã công cho đơn nghỉ" → đổi tên
  thành `leave_attendance_code.py`. Tên cũ mô tả một cơ chế không còn ở đó.

## 4. Bất biến lương

Thiết kế này **không ghi vào bản ghi Attendance nào** và **không đụng** ba trường payroll đọc
(`status`, `leave_type`, `half_day_status`). Toàn bộ thay đổi nằm ở master data
(`Attendance Code`, `Leave Type`) và ở các chốt validate.

Cổng bắt buộc trước khi coi là xong: chụp `payment_days` / `absent_days` / LWP của các Salary Slip
hiện có trước và sau, khẳng định không đổi.

## 5. Thay đổi hành vi nhìn thấy được

Ba thứ trước đây lưu được, sau thay đổi này sẽ bị chặn:

1. Hai mã cùng `(maps_to_status, leave_type)`.
2. Mã không có `category`.
3. Đơn nghỉ theo loại chưa có mã ứng với trạng thái cần thiết — gồm cả **đơn nghỉ nửa ngày theo
   loại chưa có mã nửa ngày**. Cách chữa là tạo mã, một dòng master data.
4. Đơn nghỉ nửa ngày không chọn buổi (Sáng/Chiều) — chốt server nay bắt với **mọi** loại nghỉ, khớp
   với `mandatory_depends_on` mà fixture của trường đã khai từ trước. Người dùng desk/PWA không
   thấy khác gì; chỉ đường ghi qua API là siết lại.

Cả bốn đều đúng với dữ liệu hiện tại (đã kiểm trên site), nên không bản ghi nào đang chạy bị vỡ.

## 6. Kiểm thử

| Test | Khẳng định |
|---|---|
| tập category chuẩn | năm nơi tiêu thụ + JSON không lệch với `CATEGORIES` |
| `Attendance Code` validate | chặn trùng cặp; chặn thiếu `category`; cho phép mã `On Leave` chưa gắn loại nghỉ; **17 mã fixtures đang có đều qua** |
| chống cướp mã | gán mã đang thuộc loại nghỉ khác thì `throw`, `Nghỉ phép năm` không mất `P` |
| chốt chặn đơn nghỉ | loại chưa có mã → throw (cả ngày và nửa ngày); có mã → qua |
| đối chứng gỡ hằng | `Nghỉ phép năm` cả ngày/nửa ngày vẫn ra `P`/`1/2P` y như trước |
| đầu-cuối loại nghỉ tự tạo | tạo loại nghỉ + mã riêng → cả hai đường (chưa có chấm công / đã có V) đều ra đúng mã và **CÔNG = 1** |
| bất biến lương | `payment_days`/`absent_days`/LWP không đổi trước–sau |

Chạy bằng harness rollback (`hrms/tests/isolation.py`), **tuyệt đối không** `bench --site miyano
run-tests`.

## 7. Kết quả mong đợi

HR tạo bao nhiêu Loại nghỉ tuỳ ý. Với mỗi loại, tạo mã công trỏ tới nó và chọn nhóm cột — hai
bước, cả hai đều có chốt chặn nếu quên. Bộ loại nghỉ hệ thống sinh ra không còn là ràng buộc: thay
được, bỏ được, thêm được, và không chỗ nào trong code còn gọi tên chúng.
