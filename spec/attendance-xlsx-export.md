# Xuất Excel bảng chấm công tháng — có màu, chú thích dạng lưới

Ngày: 2026-08-03 · Báo cáo: **Monthly Attendance Report** (`hrms/hr/report/monthly_attendance_report/`)

## Vấn đề

Nút **Export** của query report đi qua `frappe.desk.query_report.export_query`, dựng file từ
`columns` + `result` bằng `make_xlsx()`. Đường đó **không có chỗ móc để tô màu**: mọi ô ra file đều
trắng trơn, chữ thường, không viền, không đóng băng dòng tiêu đề. Bảng trên màn hình có 10 màu
trạng thái (`STATE_STYLE`) thì file xuất ra mất sạch — người nhận file không đọc được ngày nào là
phép, ngày nào vắng, nếu không tra tay từng ký hiệu.

Chú thích cũng vậy: hiện đi vào file dưới dạng **một dòng văn bản dài** dồn hết 16 ký hiệu vào một
ô (`legend_row()` trong `hrms/hr/attendance_legend.py`) — giải pháp cũ chỉ nhằm "có còn hơn không",
vì `message` (khối chip màu đẹp trên màn hình) không bao giờ đi vào file.

## Kết quả mong muốn

File `.xlsx` xuất ra trông **như bảng trên hệ thống**: ô mã công tô đúng màu trạng thái, cột
*Tổng công* in đậm, tiêu đề đóng băng, viền đầy đủ. Khối chú thích nằm dưới bảng dạng **lưới**:
`Chú thích` một ô, mỗi ký hiệu một ô (tô đúng màu của nó), nghĩa của ký hiệu ở ô ngang hàng bên
cạnh, **tối đa 10 dòng** — vượt thì tràn sang cụm cột kế tiếp.

## Thiết kế

### 1. Bộ dựng file — `hrms/hr/attendance_xlsx.py` (mới)

Một module, hai đường ra, không đụng gì tới logic chấm công:

| Hàm | Vai trò |
|---|---|
| `build_workbook(columns, data, filters) -> Workbook` | thuần hàm, dựng `openpyxl.Workbook` từ đúng `columns`/`data` mà `execute()` trả về. Test bám vào đây. |
| `download(filters, visible_idx=None)` (whitelisted) | chạy `execute()`, lọc theo `visible_idx`, gọi `build_workbook`, trả file qua `provide_binary_file`. |

**Màu lấy từ `STATE_STYLE`** trong `monthly_attendance_report.py` — vẫn đúng một nguồn màu cho cả
ba nơi (formatter JS, print format Jinja, và giờ là file Excel). Dùng cặp màu **nền sáng**
(`bg`/`fg`); bản nền tối chỉ có nghĩa trong Desk.

**State của mỗi ô** không tính lại: `execute()` đã gắn sẵn `_state_<day>` lên từng dòng. Đó là
metadata ẩn, không phải cột — bộ dựng file đọc nó y như formatter JS đọc.

Bố cục sheet:

```
dòng 1   CÔNG TY TNHH MIYANO VIỆT NAM          (gộp ô, đậm, căn TRÁI)
dòng 2   MST: 0109529507                       (gộp ô, trái)
dòng 3   Địa chỉ: số 20, Khu C17, …            (gộp ô, trái)
dòng 4   —
dòng 5   BẢNG CHẤM CÔNG                        (gộp ô, đậm 16, căn GIỮA)
dòng 6   Tháng 06 Năm 2026                     (gộp ô, giữa)
dòng 7   —
dòng 8   STT | Nhân viên | 1  | 2  | … | Tổng công | Phép | … | Số buổi ăn trưa
dòng 9        (gộp dọc)  | T4 | T5 | … |  (gộp dọc)
dòng 10+ dữ liệu — ô ngày tô nền theo state, chữ đậm, căn giữa; Tổng công in đậm
```

- **Cột đầu là STT** (1, 2, 3…), không phải "Mã NV": bản in cần số thứ tự, `HR-EMP-00001` chỉ tốn
  chỗ. Chỉ đổi ở file — trên màn hình cột Mã NV vẫn là liên kết bấm sang hồ sơ nhân viên.
- Neo dòng bằng hằng số `HEADER_ROW` / `WEEKDAY_ROW` / `FIRST_DATA_ROW`, không đếm theo số dòng
  tiêu đề thư thực ghi: thiếu MST hay địa chỉ thì khối trên ngắn lại, bảng vẫn phải bắt đầu đúng
  chỗ mọi nơi khác trông đợi.

- Tiêu đề **hai dòng**: hàng số ngày, ngay dưới là hàng thứ (`T2`…`T7`, `CN`) — đúng lối bảng chấm
  công VN. Cột không phải cột ngày gộp dọc qua cả hai dòng. Cả hai dòng lặp lại ở mọi trang in.
- `freeze_panes = "C5"` → cuộn ngang vẫn thấy mã NV + tên; cuộn dọc vẫn thấy tiêu đề.
- Độ rộng cột lấy từ `width` của `columns` quy đổi (px → ký tự); cột ngày giữ hẹp cho vừa `1/2P`,
  cột còn lại có sàn 11 ký tự.
- Nhãn cột tổng hợp dài hơn ô ("Tai nạn lao động", "Số buổi ăn trưa") thì **xuống dòng trong ô**
  (`wrap_text`, dòng tiêu đề cao 34), không nới cột — nới ra là cả bảng bị co nhỏ khi in vừa một
  trang ngang.
- Viền mảnh toàn bảng; in ngang, co vừa một trang ngang (`fitToWidth`).
- Số: để `General` — 21.5 hiện là `21.5`, 22 hiện là `22`, không thành `22.00`.

### 2. Khối chú thích dạng lưới

Nguồn vẫn là `legend_pairs()` (đọc từ `Attendance Code` + 2 marker lịch) — thêm/bớt mã là file tự
cập nhật, không viết cứng ở đây.

Cách xếp, với `MAX_LEGEND_ROWS = 10`:

```
n_groups = ceil(len(pairs) / 10)          # 16 mã → 2 cụm
n_rows   = ceil(len(pairs) / n_groups)    # → 8 dòng
```

Điền **theo cột** (đầy cụm 1 mới sang cụm 2) để đọc dọc từ trên xuống đúng thứ tự ưu tiên mà
`legend_pairs()` đã sắp (đi làm → nghỉ có lương → không lương → vắng).

```
   B          C     D … J                 K     L … R
1  Chú thích  [X]   Đi làm đủ công        [NB]  Nghỉ bù
2             [CT]  Đi công tác           [KH]  Nghỉ kết hôn
…
10            [T]   Nghỉ tai nạn lao động [NL]  Nghỉ lễ hưởng lương
```

- `Chú thích` — **một ô** (cột **Nhân viên**, dòng đầu khối), không gộp. Không đặt ở cột STT: cột
  đó hẹp, chữ tràn ra ngoài trông như dữ liệu lạc dòng.
- Ký hiệu — **một ô**, tô đúng nền/chữ của state ô đó trong lưới, đậm, căn giữa, có viền.
- Nghĩa — **một ô ngang hàng ngay bên phải**, gộp qua nhiều cột ngày cho đủ rộng
  (cột ngày chỉ ~4 ký tự; gộp là cách duy nhất để vẫn là "một ô" mà đọc được).
- Bề rộng cụm tự co theo số cột còn lại của bảng, tối thiểu 4 cột — tháng 28 ngày vẫn không tràn.

### 2b. Bỏ hẳn dòng chú thích văn bản dài (2026-08-03)

`legend_row()` từng gắn ĐÚNG MỘT dòng cuối bảng, dồn cả 19 ký hiệu vào một ô
(`Chú thích: X=Đi làm đủ công; CT=…`), chỉ để chú thích theo được vào file Excel — `message` không
đi vào file. Khối lưới ở trên đã thay vai trò đó, nên dòng văn bản dài chỉ còn làm bẩn cuối lưới.

Gỡ `legend_row()`, `is_legend_row()`, `legend_text()`, `LEGEND_ROW_FIELD` khỏi
`hrms/hr/attendance_legend.py` và bỏ `data.append(legend_row())` trong `execute()`. Hệ quả đã
lường: đường CSV và export mặc định của Frappe **không còn chú thích** — đúng ý, ai cần chú thích
thì xuất Excel.

### 2d. Tiêu đề thư (2026-08-03)

`company_lines(company)` dựng ba dòng: tên pháp nhân, `MST: …`, `Địa chỉ: …`.

**Master data thắng ở đâu có** — `Company.tax_id` cho MST, Address chính liên kết với Company cho
địa chỉ. Site hiện chưa có cả hai (`tax_id` trống, không Address nào) và `Company.company_name` là
tên gọi tắt `Miyano` chứ không phải tên pháp nhân trên giấy tờ, nên hằng số `MIYANO_LETTERHEAD`
đứng làm mặc định.

Không sửa `Company.company_name` thành tên đầy đủ: đó là tên công ty trên **mọi** chứng từ ERPNext
(hoá đơn, phiếu lương…), không riêng bảng chấm công — đổi là đổi hết. Điền `tax_id` / tạo Address
cho Company thì dữ liệu thắng ngay, không phải sửa code.

### 2e. TB giờ/ngày (2026-08-03)

Cột cuối bảng: **tổng giờ có mặt / số ngày làm việc tại văn phòng**.

Mẫu số là chỗ dễ sai. "Ngày làm việc tại văn phòng" = Attendance đã duyệt có status
`Present`/`Half Day` **và** có cả giờ vào lẫn giờ ra. Bốn nhóm rơi ra ngoài, đúng ý HR:

| Loại ngày | Vì sao không vào mẫu số |
|---|---|
| Nghỉ lễ, nghỉ tuần | không có bản ghi Attendance nào |
| Nghỉ phép, vắng | status `On Leave` / `Absent` |
| **Công tác (CT), làm tại nhà (W)** | cả hai mã đều map sang status `Work From Home` |
| Chấm tay, yêu cầu chấm công | không có giờ vào/ra ⇒ không xác định được thời gian có mặt |

Giờ mỗi ngày là **giờ CÓ MẶT**, không phải giờ quy công: `(ra - vào)` trừ phần giao với khung nghỉ
trưa của ca (mặc định 12:00–13:30). Không cắt theo khung ca — ở lại sau giờ tan ca vẫn được tính.

**Một nguồn duy nhất:** `presence_hours()` / `get_lunch_window_map()` / `NON_PRESENCE_STATUSES` dời
từ `hr/report/employee_working_hours/` về `hrms/hr/working_hours.py` (module dùng chung), thêm
`office_hours_map()` + `avg_office_hours()`. Báo cáo Giờ làm việc nhân viên import lại từ đó, nên
hai báo cáo không thể lệch nhau — đã đối chiếu trên dữ liệu thật tháng 7/2026: khớp cả 6 nhân viên.

### 2c. Thứ trong tuần

`weekday_label(year, month, day)` trong `monthly_attendance_report.py` (suy từ `date.weekday()`,
không đọc dữ liệu nào) là nguồn duy nhất cho cả hai nơi:

- **Trên màn hình** — nhãn cột gộp một dòng: `1 T4`, `2 T5`, … Không xuống dòng bằng `<br>` được:
  datatable đặt `white-space: nowrap` + `overflow: hidden` + chiều cao cố định cho ô tiêu đề nên
  nửa dưới bị cắt. Cột ngày nới 45px → **66px** (ô tiêu đề ăn 24px đệm; hẹp hơn thì `30 T5` bị
  cắt thành `30 T…`).
- **Trong Excel** — tách thành hai dòng tiêu đề như mô tả ở §1; bề rộng cột ngày là hằng số riêng
  (`DAY_WIDTH = 5.0`), không suy từ `width` của report, vì ở đây ô chỉ cần chứa mã công.

### 3. Nối vào nút Export — `monthly_attendance_report.js`

`export_report()` là method của instance query report, `onload(report)` nhận đúng instance đó, nên
ghi đè ở mức instance là đủ — không vá prototype, không ảnh hưởng báo cáo khác:

```js
report.export_report = () => { /* dialog riêng */ };
```

Hộp thoại giữ hai lựa chọn:

- **Excel (có màu)** — mặc định → `open_url_post` sang `hrms.hr.attendance_xlsx.download`.
- **CSV** — giữ nguyên đường cũ `frappe.desk.query_report.export_query`, không mất năng lực nào.

Vẫn gọi `report.make_access_log("Export", …)` để bản ghi truy cập không thủng.

### 4. Quyền

`download()` kiểm tra `frappe.permissions.can_export("Attendance", raise_exception=True)` — đúng
thứ `export_query` kiểm, vì `ref_doctype` của báo cáo là `Attendance`.

## Ràng buộc

- **Chỉ đọc.** Không ghi Attendance, không đụng `status`/`leave_type`/`half_day_status` → lương bất
  biến theo định nghĩa; không cần cổng ký duyệt payroll.
- Không đổi `execute()`, không đổi `STATE_STYLE`, không đổi print format.

## Kiểm chứng

Test mới `hrms/hr/report/monthly_attendance_report/test_attendance_xlsx.py`, dựng workbook trong bộ
nhớ rồi soi ô:

1. Ô ngày mang mã `X` có nền `d9efdc` (state `work`); mã `P` nền `fbedc4`; `V` nền `f7d3d3`.
2. Ô `Tổng công` in đậm; giá trị khớp `execute()`.
3. Dòng chú thích văn bản cũ không có mặt trong sheet.
4. Khối chú thích: `Chú thích` đúng một ô; **số dòng ≤ 10**; mỗi ký hiệu một ô, nghĩa ngang hàng
   bên phải; đủ toàn bộ `legend_pairs()`; ô ký hiệu tô đúng màu state của nó.
5. Chú thích chia đúng số cụm khi số mã > 10 (giả lập danh sách dài).
6. `freeze_panes` = `C10` (ngay dưới hai dòng tiêu đề bảng).
7. Thứ trong tuần: nhãn cột trên màn hình là `1 T7` / `2 CN` cho tháng 8/2026, và đổi theo tháng
   đang xem (9/2026 → `1 T3`); trong Excel hàng thứ nằm ngay dưới hàng số ngày, cột thường gộp dọc
   qua cả hai dòng.
8. Không ô nào trong file còn chuỗi dạng `X=…` (dòng chú thích văn bản dài đã bỏ hẳn).
9. Tiêu đề thư: ba dòng pháp nhân căn trái ở dòng 1–3, `BẢNG CHẤM CÔNG` + `Tháng 07 Năm 2026` căn
   giữa, dòng ngay trên bảng để trống; điền `Company.tax_id` là số đó lên bản in ngay.
10. Cột đầu là `STT` chạy 1, 2, 3…; không ô nào trong file còn chuỗi bắt đầu bằng `HR-EMP`.
