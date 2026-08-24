# Xuất Excel bảng lương tháng — mẫu Miyano, ký được

Ngày: 2026-08-24 · Báo cáo: **Bảng Lương MVL** (`hrms/payroll/report/bang_luong_mvl/`)

## Vấn đề

Báo cáo `Bảng Lương MVL` đã có đủ 21 cột đúng thứ tự file Excel gốc (E…U), nhưng nút **Export**
vẫn là nút mặc định của query report: `frappe.desk.query_report.export_query` đổ thẳng
`columns` + `result` qua `make_xlsx()`. Ra một **lưới trần** — không tên công ty, không MST, không
địa chỉ, không tên biểu mẫu, không kỳ lương, dòng TỔNG CỘNG lẫn vào như một dòng dữ liệu, và
**không có chỗ ký**.

Bảng lương không phải bản kết xuất dữ liệu: nó là **chứng từ đem trình giám đốc ký**. Thiếu tiêu đề
thư và khối trình ký thì mỗi kỳ lại phải mở Excel gõ tay lại phần đầu và phần cuối tờ giấy — đúng
việc mà bảng chấm công đã bỏ được từ 2026-08-21.

Ngoài ra cột `Mã NV` (`HR-EMP-00001`) chỉ có nghĩa trên màn hình (liên kết bấm sang hồ sơ); trên
bản in nó chiếm chỗ mà không ai đọc.

## Kết quả mong muốn

File `.xlsx` xuất ra là **tờ bảng lương hoàn chỉnh**: tiêu đề thư pháp nhân, tên biểu mẫu, kỳ lương,
bảng số liệu có dấu phân cách nghìn, dòng TỔNG CỘNG in đậm nổi lên, và khối trình ký
`Người lập` / `Người duyệt` ở cuối — in ra là ký được ngay.

## Thiết kế

### 1. Tách kiểu nhà dùng chung — `hrms/miyano_xlsx.py` (mới)

Bảng chấm công và bảng lương khác hẳn nhau về cột, nhưng **đầu và cuối tờ giấy giống hệt**. Phần đó
vốn nằm trong `hrms/hr/attendance_xlsx.py`; nay dời sang module dùng chung để hai biểu mẫu không
trôi khỏi nhau — sửa địa chỉ công ty một chỗ, cả hai cùng đổi.

| Chuyển sang `miyano_xlsx` | Vai trò |
|---|---|
| `MIYANO_LETTERHEAD`, `company_lines/address/city` | ba dòng pháp nhân, master data thắng ở đâu có |
| `write_letterhead(ws, company, last_col, title, subtitle, title_row)` | khối đầu tờ giấy |
| `sign_blocks`, `write_signatures`, `signature_date_line/names`, `session_signer_name` | khối trình ký |
| `BORDER/CENTER/LEFT/RIGHT/HEADER_*`, `excel_width`, `period_line` | style + đổi đơn vị bề rộng |

Một chỗ phải **nới tham số**: `sign_blocks(last_col)` trước đây neo cứng cột đầu = 3 và bề ngang 10
cột — hợp với cột ngày hẹp của bảng chấm công. Bảng lương cột tiền rộng gấp ba, gộp 10 cột thì hai
chữ ký chiếm gần hết bề ngang. Nay là `sign_blocks(last_col, first_col, width)`, **giá trị mặc định
giữ nguyên hành vi cũ** → 23 test của bảng chấm công vẫn xanh không sửa một dòng khẳng định nào.

### 2. Bộ dựng file — `hrms/vn_payroll/salary_xlsx.py` (mới)

| Hàm | Vai trò |
|---|---|
| `build_workbook(columns, data, filters, signatures)` | thuần hàm, dựng `Workbook` từ đúng `columns`/`data` mà `execute()` trả về. Test bám vào đây. |
| `download(filters, visible_idx, prepared_by, approved_by)` | whitelisted, chạy `execute()`, lọc theo dòng đang hiện, trả file qua `provide_binary_file`. |

Bố cục sheet:

```
dòng 1   CÔNG TY TNHH MIYANO VIỆT NAM          (gộp ô, đậm, căn TRÁI)
dòng 2   MST: 0109529507
dòng 3   Địa chỉ: …
dòng 5   BẢNG THANH TOÁN TIỀN LƯƠNG            (gộp ô, đậm 16, căn GIỮA)
dòng 6   Tháng 07 Năm 2026
dòng 8   STT | Họ tên | Loại | NET/GROSS | Hệ số (E) | … | TN chịu thuế kê khai (U)
dòng 9+  dữ liệu
   …     TỔNG CỘNG                             (đậm, nền nhạt)
   …     khối ký: Người lập · Người duyệt
```

- **Một dòng tiêu đề**, khác bảng chấm công (cần hai: số ngày rồi thứ). Neo bằng `HEADER_ROW = 8`
  chứ không đếm số dòng pháp nhân thực ghi: thiếu MST hay địa chỉ thì khối trên ngắn lại, bảng vẫn
  phải bắt đầu đúng chỗ `print_title_rows` và khối ký trông đợi.
- **Cột đầu là STT**, thay cột `Mã NV`. Chỉ đổi ở file — trên màn hình cột Mã NV vẫn là liên kết.
- **Dòng TỔNG CỘNG nhận diện bằng CHỖ THIẾU `employee`**, không so chuỗi nhãn: nhãn đi qua `_()`
  nên đổi theo ngôn ngữ, còn dòng tổng thì vĩnh viễn không có mã nhân viên. Đây là cái bẫy thật:
  bảng chấm công lọc `if row.get("employee")` — bê nguyên sang đây là **ném mất dòng tổng**, đúng
  dòng người ta nhìn đầu tiên trên bảng lương.
- **Định dạng số**: tiền `#,##0` (VND không phần lẻ) và căn phải để so bậc số bằng mắt — `25994783`
  thì không ai soát nổi, `25,994,783` thì liếc qua là biết. Hệ số `0.00`. Số công để `General`:
  19.5 hiện `19.5`, 22 hiện `22`, ép `0.00` thì cả cột đầy `22.00`, rối mà không thêm thông tin.
- `freeze_panes = "C9"` → cuộn sang cột thuế/BH vẫn biết đang xem ai.
- In ngang, co vừa một trang ngang; dòng tiêu đề lặp ở mọi trang.

### 3. Bộ lọc `Gồm cả phiếu nháp` + dấu cảnh báo

Báo cáo trước nay chỉ đọc phiếu `docstatus = 1`. Đúng với tinh thần chứng từ, nhưng trên site thật
(2026-08-24) **mọi phiếu 7/2026 còn nháp** vì cổng chốt công (`hrms_enforce_sheet_gate`) đang bật —
bấm Export ra tờ giấy trắng, không hiểu vì sao.

Thêm filter `include_drafts` (Check, **mặc định TẮT**). Bật lên để soát số trước khi duyệt.

**Bật thì tờ giấy phải nói ra:** `subtitle_line()` gắn thêm `— GỒM CẢ PHIẾU NHÁP — CHƯA CHỐT` vào
dòng kỳ lương. Không có dấu này thì bản nháp trông y hệt bản chính thức và người duyệt ký lên những
con số còn có thể đổi.

### 4. Nối vào nút Export — `bang_luong_mvl.js`

`frappe.query_report` là **MỘT instance dùng chung cho MỌI query report** (`load_report()` chỉ đổi
`report_name`, không dựng lại object). Ghi đè thẳng `export_report` sẽ rò sang báo cáo khác trong
cùng phiên — đúng lỗi đã dính với bảng chấm công 2026-08-03. Nên: bọc **một lần**
(`_mvl_export_patched`) và **luôn kiểm tên báo cáo** lúc bấm.

Hàm hộp thoại đặt tên riêng `mvl_salary_export_dialog`, **không** trùng `vn_export_dialog` của bảng
chấm công: cả hai file đều được `frappe.dom.eval` chèn vào phạm vi toàn cục, trùng tên là file nạp
sau đè file nạp trước và một trong hai báo cáo xuất nhầm biểu mẫu của báo cáo kia.

Hộp thoại: **Excel** (mặc định) / **CSV** (giữ nguyên đường cũ), cộng hai ô tên `Người lập` /
`Người duyệt` chỉ hiện khi chọn Excel. Để trống `Người lập` → lấy tên nhân viên của người đang đăng
nhập; để trống `Người duyệt` → chỉ in chức danh, ký tay. Vẫn gọi `make_access_log("Export", …)`.

### 5. Quyền

`download()` kiểm `frappe.permissions.can_export("Salary Slip", raise_exception=True)` — đúng thứ
`export_query` kiểm, vì `ref_doctype` của báo cáo là `Salary Slip`.

## Ràng buộc

- **Chỉ đọc.** Không đụng Salary Slip, không tính lại đồng nào: mọi con số lấy nguyên từ `execute()`
  của báo cáo, mà báo cáo lấy nguyên từ `Salary Detail` đã chốt trên phiếu → lương bất biến theo
  định nghĩa, không cần cổng ký duyệt payroll.
- Không đổi engine MVL, không đổi cấu trúc lương, không đổi công thức.

## Đối soát công thức (2026-08-24)

Trước khi làm phần xuất file, đã đối soát **ba chiều** để chắc con số in ra là đúng:

1. **Engine ↔ tài liệu:** `hrms/vn_payroll/tests/test_mvl.py` — 14/14 xanh, oracle là ví dụ số trong
   `docs/Cong_thuc_tinh_luong_MVL.md`.
2. **Phiếu thật ↔ engine:** dựng lại `compute_mvl()` từ Salary Structure Assignment cho cả 6 phiếu
   7/2026 (đủ 6 loại: Chính thức, Thử việc, Bán thời gian ×2, Khoán, Chuyên gia) rồi so từng cột
   I, J, K, N, O, P, Q, R, S, T, U với `Salary Detail` trên phiếu → **65/66 khớp tuyệt đối**.
3. **Bộ test payroll đầy đủ:** 105 test xanh.

**Một điểm lệch, CỐ Ý, cần biết khi đọc bảng:** loại **Khoán** không có component
`Thu nhập chịu thuế kê khai` trong cấu trúc (`setup_mvl.STRUCTURES`, chú thích: "khoán trọn gói,
KHÔNG khấu trừ thuế → không cần cột kê khai U"), nên **cột U của nhân sự khoán hiện 0** trong khi
engine tính ra 20.000.000, và dòng TỔNG CỘNG của cột U thiếu đúng phần đó. Đây là quyết định chính
sách thuế, **không sửa trong phạm vi việc này** — cần sign-off trước khi đổi (CLAUDE.md: đổi logic
cầu nối lương phải hỏi trước).

## Kiểm chứng

`hrms/payroll/report/bang_luong_mvl/test_salary_xlsx.py` — dựng workbook trong bộ nhớ rồi soi ô:

1. Tiêu đề thư ba dòng căn trái; tên biểu mẫu + kỳ căn giữa; dòng ngay trên bảng để trống.
2. Cột đầu là `STT` chạy 1, 2, 3…; không ô nào trong file còn chuỗi bắt đầu bằng `HR-EMP`.
3. Nhãn cột khớp `get_columns()` của báo cáo — file không được tự đặt tên khác màn hình.
4. Dòng TỔNG CỘNG: còn nguyên (không bị lọc mất), in đậm, không đánh STT, và bằng tổng cột.
5. Cột tiền mang `number_format = "#,##0"`.
6. `freeze_panes = "C9"`.
7. Khối trình ký: nằm dưới bảng, người duyệt bên phải người lập, không tràn sang cột STT/Họ tên;
   dòng địa danh + ngày ngay trên chức danh người duyệt; tên gõ ở hộp thoại theo được tới file và
   nằm cách chức danh đúng `SIGN_NAME_GAP` dòng.
8. In ngang, `fitToWidth = 1`, lặp dòng tiêu đề.
9. Kỳ rỗng vẫn ra tờ giấy có tiêu đề + khối ký, không nổ.
10. `download()` bị gọi nhầm từ báo cáo khác thì báo rõ ràng, không ném lỗi khó hiểu của `execute()`.
11. Bật `include_drafts` thì tiêu đề mang dấu `GỒM CẢ PHIẾU NHÁP — CHƯA CHỐT`; tắt thì không.

## Dọn dẹp kèm theo

Hai test của bộ payroll trước đây **đỏ hay xanh tuỳ site đang chạy** — chúng submit phiếu lương
trong kỳ 2099 (không có Bảng Công Tháng nào) nên bị `sheet_gate` chặn trên miyano (cờ
`hrms_enforce_sheet_gate` bật) nhưng lọt trên CI. Đã gắn cửa thoát `skip_sheet_gate` sẵn có, đúng
lối `TestSalarySlipMVL.setUp` vẫn dùng: `test_bang_luong_mvl.py`, `test_packaging.py`.

`TestGateAgainstLiveData` khẳng định `assertTrue(slips)` — site sạch phiếu submit (mọi phiếu còn
nháp) bị báo đỏ y như khi lương thật lệch khỏi bảng đã chốt. Hai chuyện khác hẳn nhau: nay
`skipTest` khi không có phiếu nào để đối soát, giữ nguyên khẳng định lõi `blocked == []`.
