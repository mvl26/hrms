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
dòng 1   BẢNG CHẤM CÔNG THÁNG 8/2026          (gộp ô, đậm 14, giữa)
dòng 2   <Công ty>                             (gộp ô, giữa; bỏ nếu không lọc công ty)
dòng 3   Mã NV | Nhân viên | 1 | 2 | … | Tổng công | Phép | … | Số buổi ăn trưa
dòng 4+  dữ liệu — ô ngày tô nền theo state, chữ đậm, căn giữa; Tổng công in đậm
```

- `freeze_panes = "C4"` → cuộn ngang vẫn thấy mã NV + tên; cuộn dọc vẫn thấy tiêu đề.
- Độ rộng cột lấy từ `width` của `columns` quy đổi (px → ký tự), ngày ~4.2 cho vừa `1/2P`.
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
   A          C     D … L                 M     N … V
1  Chú thích  [X]   Đi làm đủ công        [N]   Nghỉ việc riêng
2             [CT]  Đi công tác           [K]   Nghỉ không lương
…
8             [NB]  Nghỉ bù               [NL]  Nghỉ lễ hưởng lương
```

- `Chú thích` — **một ô** (cột A, dòng đầu khối), không gộp.
- Ký hiệu — **một ô**, tô đúng nền/chữ của state ô đó trong lưới, đậm, căn giữa, có viền.
- Nghĩa — **một ô ngang hàng ngay bên phải**, gộp qua nhiều cột ngày cho đủ rộng
  (cột ngày chỉ ~4 ký tự; gộp là cách duy nhất để vẫn là "một ô" mà đọc được).
- Bề rộng cụm tự co theo số cột còn lại của bảng, tối thiểu 4 cột — tháng 28 ngày vẫn không tràn.

Dòng chú thích văn bản cũ (`legend_row()`) bị **lọc khỏi dữ liệu** bằng `is_legend_row()` trước khi
ghi, nếu không sẽ có hai khối chú thích chồng nhau. `legend_row()` vẫn giữ nguyên vì đường xuất
CSV và export mặc định của Frappe vẫn dùng nó.

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
6. `freeze_panes` = `C4`, có dòng tiêu đề tháng.
