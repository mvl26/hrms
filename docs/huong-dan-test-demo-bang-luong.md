# Hướng dẫn test demo bảng lương (5 phút)

Ngày: 2026-08-27 · Báo cáo: **Bảng lương MVL** (`MVL Salary Register`)

> **Bảng lương ĐÃ CHẠY ĐƯỢC.** Sở dĩ bạn mở ra thấy trống là vì mặc định báo cáo chỉ lấy **phiếu
> lương đã duyệt**, mà 6 phiếu tháng 7/2026 trên site đang là **nháp** — nên bảng rỗng là đúng
> thiết kế, không phải hỏng. Tick một ô là thấy đủ số ngay.

---

## Bước 1 — Mở báo cáo

Bấm **Ctrl + G** → gõ **Bảng lương MVL** → Enter.

*(Nếu muốn dán URL thì phải mã hoá dấu cách: `http://localhost/app/query-report/MVL%20Salary%20Register`
— dán URL có dấu cách thật thì trình duyệt cắt tên, Frappe báo lỗi `getdoctype()` khó hiểu.)*

Lần đầu vào nhớ bấm **Ctrl + Shift + R** một lần để bỏ file `.js` cũ trong cache.

## Bước 2 — Đặt bộ lọc

| Ô | Điền |
|---|---|
| Công ty | `Miyano` |
| Tháng | `7` |
| Năm | `2026` |
| Phòng ban | *(để trống)* |
| **Gồm cả phiếu nháp** | ✅ **TICK VÀO** |

👉 Chưa tick thì bảng **rỗng** (đúng — chưa có phiếu nào được duyệt).
👉 Tick vào thì hiện **6 dòng nhân viên + 1 dòng TỔNG CỘNG**.

## Bước 3 — Đối chiếu số trên màn hình

Phải khớp đúng bảng này:

| # | Họ tên | Loại | Công (H) | Lương thực tế (I) | Ăn trưa (J) | Thuế TNCN (Q) | Thực lĩnh (T) |
|---|---|---|---|---|---|---|---|
| 1 | hieu chu | Bán thời gian | 22,5 | 9.782.609 | 0 | 2.445.652 | 9.782.609 |
| 2 | Nguyễn Văn An | Khoán | 19,5 | 20.000.000 | 0 | 0 | 20.000.000 |
| 3 | Trần Thị Bình | Toàn thời gian | 19,5 | 25.434.783 | 560.000 | 0 | 25.994.783 |
| 4 | Lê Văn Cường | Toàn thời gian | 22,0 | 14.634.783 | 595.000 | 0 | 15.229.783 |
| 5 | Phạm Thị Dung | Chuyên gia | 22,5 | 25.000.000 | 0 | 2.777.778 | 25.000.000 |
| 6 | Hoàng Văn Em | Bán thời gian | 22,5 | 13.206.522 | 0 | 1.467.391 | 13.206.522 |
| | **TỔNG CỘNG** | | | **108.058.697** | **1.155.000** | **6.690.821** | **109.213.697** |

Bảng có đủ **21 cột** theo đúng thứ tự file Excel gốc: Mã NV · Họ tên · Loại · NET/GROSS · Hệ số (E)
· Lương ngày công (F) · Lương đóng BHXH (G) · Số công (H) · Lương thực tế (I) · Phụ cấp ăn trưa (J)
· Tổng thu nhập (K) · Giảm trừ bản thân (L) · Số người phụ thuộc (M) · Tổng giảm trừ (N)
· Thu nhập quy đổi (O) · Thu nhập tính thuế (P) · Thuế TNCN (Q) · BH công ty (R) · BH NLĐ (S)
· Thực lĩnh (T) · TN chịu thuế kê khai (U).

## Bước 4 — Xuất Excel (phần chính cần nghiệm thu)

1. Bấm **⋯ (Menu) → Export**
2. Hiện hộp thoại **"Xuất bảng lương"** — *không phải* hộp Export mặc định của Frappe
3. `Định dạng` = **Excel — mẫu Miyano, có khối ký**
4. Gõ `Người lập` = tên bạn · `Người duyệt` = tên giám đốc
5. **Tải về** → file tên `Bang luong 07-2026.xlsx`

Mở file, kiểm đúng 7 điểm:

- [ ] Dòng 1–3 căn trái: `CÔNG TY TNHH MIYANO VIỆT NAM` / `MST: 0109529507` / `Địa chỉ: …`
- [ ] Dòng 5–6 căn giữa: `BẢNG THANH TOÁN TIỀN LƯƠNG` / `Tháng 07 Năm 2026`
- [ ] Dòng 6 có thêm **`— GỒM CẢ PHIẾU NHÁP — CHƯA CHỐT`** *(vì đang bật phiếu nháp)*
- [ ] Cột A là **STT** 1…6, không phải mã `HR-EMP-…`
- [ ] Tiền hiện `25,994,783` (có dấu phân cách nghìn), căn phải
- [ ] Dòng **TỔNG CỘNG** in đậm, nền xám nhạt, không có số thứ tự
- [ ] Cuối bảng: dòng `Hà Nội, ngày … tháng … năm …`, hai chức danh **Người lập** / **Người duyệt**,
      chừa 6 dòng trống để ký tay, rồi tới hai cái tên bạn vừa gõ

In thử (Ctrl+P): khổ **ngang**, cả 21 cột lọt **một trang**.

## Bước 5 — Thử tự kiểm một công thức bằng tay

Lấy **Trần Thị Bình** (Chính thức, lương ngày công F = 30.000.000, công 19,5/23, ăn 16 buổi,
2 người phụ thuộc, lương đóng BHXH 30.000.000):

| Bước | Công thức | Ra |
|---|---|---|
| I | `ROUND(30.000.000 ÷ 23 × 19,5)` | 25.434.783 |
| J | `16 × 35.000` | 560.000 |
| K | `I + J` | 25.994.783 |
| N | `15.500.000 + 2 × 6.200.000` | 27.900.000 |
| O | `MAX(K − N − J, 0)` | 0 → không phải nộp thuế |
| R | `30.000.000 × 21,5%` | 6.450.000 |
| S | `30.000.000 × 10,5%` | 3.150.000 |
| T | `= K` (trả NET) | **25.994.783** |

Con số trên báo cáo phải khớp từng đồng.

## Bước 6 — Kiểm không làm hỏng bảng chấm công

Phần tiêu đề công ty + khối ký nay dùng chung hai biểu mẫu, nên thử luôn:

- [ ] Mở **Bảng chấm công tháng** → Export → Excel: file vẫn **có màu**, vẫn đủ khối chú thích và
      khối ký như trước.

---

## Muốn ra bản CHÍNH THỨC (không còn dòng cảnh báo)?

Cần 2 việc, và việc thứ 2 có rủi ro nên **chờ bạn đồng ý**:

1. **Chốt Bảng Công Tháng 7/2026** — bản `BCT-2026-00001` đang ở trạng thái *đã huỷ*, phải lập và
   chốt lại. Đây là bản chụp chỉ-đọc của chấm công, không đụng lương.
2. **Submit 6 phiếu lương** — ⚠️ **Payroll Settings đang bật `email_salary_slip_to_employee`**, nên
   submit sẽ **tự gửi email phiếu lương** cho nhân viên. Nhân viên `hieu chu` có địa chỉ thật
   (`chuvanhieu357@gmail.com`). Phải tắt cờ gửi mail trước, hoặc chấp nhận email được gửi đi.

Xong 2 bước đó thì **bỏ tick** `Gồm cả phiếu nháp` → bảng hiện đủ số, tiêu đề sạch dòng cảnh báo →
Export ra bản đem trình ký.

## Lưu ý về dữ liệu

Site hiện chỉ có **6 nhân viên demo** (Nguyễn Văn An, Trần Thị Bình, Lê Văn Cường, Phạm Thị Dung,
Hoàng Văn Em + hieu chu). **Nhân sự thật của Miyano chưa được nhập** — nên đây là bảng lương demo
để nghiệm thu chức năng, chưa phải bảng lương thật để chi trả.
