# Nghiệm thu: Xuất Excel bảng lương tháng (mẫu Miyano)

Ngày lập: 2026-08-25 · Người lập: Claude · Nhánh: `feat/skip-attendance-diag`
Spec kỹ thuật: [`docs/spec/salary-register-xlsx-export.md`](spec/salary-register-xlsx-export.md)

Tài liệu này để **bạn tự bấm và tự kết luận đạt / không đạt**. Mỗi bước có thao tác cụ thể và kết
quả mong đợi cụ thể; chỗ nào lệch thì ghi lại rồi báo.

---

## 1. Trạng thái triển khai

| Hạng mục | Trạng thái |
|---|---|
| Code trên nhánh `feat/skip-attendance-diag` | ✅ đã commit (2 commit: `75fc7f3`, `81bd2c2`) |
| `bench --site miyano migrate` | ✅ **đã chạy** — patch đổi tên báo cáo đã áp |
| Báo cáo chạy đúng (kiểm bằng `query_report.run()`) | ✅ đã xác minh |
| Tiến trình web (gunicorn) đã nạp module mới | ⚠️ **chưa xác minh được** — xem 2.1 |
| Đẩy lên GitHub (`git push`) | ❌ **chưa** — chờ bạn duyệt (nhánh đang trước origin 34 commit) |
| Số liệu lương thật để ký | ❌ **chưa** — xem mục 5 |

> **Đã sửa một lỗi có sẵn, nặng, phát hiện lúc kiểm tra:** báo cáo tên `Bảng Lương MVL` **có dấu**
> tiếng Việt, mà Frappe suy đường dẫn file bằng `scrub(tên)` → tìm thư mục `bảng_lương_mvl/` trong
> khi trên đĩa là `bang_luong_mvl/`. Không khớp ⇒ mở báo cáo trên Desk là `ModuleNotFoundError`.
> Nghĩa là **báo cáo này chưa từng chạy được**, và 4 bộ lọc (công ty/tháng/năm/phòng ban) chưa bao
> giờ hiện ra. Đã đổi tên thành **`MVL Salary Register`**, nhãn hiển thị vẫn là **Bảng lương MVL**.

---

## 2. Vào báo cáo

- URL: **http://miyano/app/query-report/MVL Salary Register**
- Hoặc: ô tìm kiếm trên Desk (Ctrl+G) → gõ **Bảng lương MVL**

**Trước khi bắt đầu:** bấm **Ctrl + Shift + R** một lần để trình duyệt bỏ bản `.js` cũ trong cache.
Không làm bước này thì nút Export mới có thể chưa hiện.

### 2.1 — Nếu báo cáo báo lỗi `ModuleNotFoundError` hoặc không thấy nút Export

Tôi kiểm chứng bằng `bench console`, mà đó là **một tiến trình mới** — nó chứng minh code đúng,
nhưng chưa chứng minh tiến trình web đang chạy đã nạp. Thư mục báo cáo vừa **đổi tên** (sau lần
gunicorn khởi động gần nhất lúc 11:52), nên nếu worker giữ bản đường dẫn cũ trong bộ nhớ thì phải
khởi động lại ứng dụng. Tôi **không có quyền restart** tiến trình production, bạn chạy giúp:

```bash
sudo supervisorctl restart frappe-bench-web:
# rồi xoá cache site cho chắc
cd /home/miyano/frappe-bench && bench --site miyano clear-cache
```

Nếu mở phát ăn ngay thì bỏ qua mục này.

---

## 3. Nghiệm thu chức năng

### 3.1 — Báo cáo mở được và có đủ bộ lọc

- [ ] Mở URL trên, trang hiện ra **không có thông báo lỗi đỏ**.
- [ ] Thanh lọc có đủ **5 ô**: `Công ty`, `Tháng`, `Năm`, `Phòng ban`, `Gồm cả phiếu nháp`.
- [ ] Bảng có **21 cột**, thứ tự: STT/Mã NV · Họ tên · Loại · NET/GROSS · Hệ số (E) · Lương ngày
      công (F) · Lương đóng BHXH (G) · Số công (H) · Lương thực tế (I) · Phụ cấp ăn trưa (J) ·
      Tổng thu nhập (K) · Giảm trừ bản thân (L) · Số người phụ thuộc (M) · Tổng giảm trừ (N) ·
      Thu nhập quy đổi (O) · Thu nhập tính thuế (P) · Thuế TNCN (Q) · BH công ty (R) · BH NLĐ (S) ·
      Thực lĩnh (T) · TN chịu thuế kê khai (U).

> ❗ Nếu bước này hỏng thì **dừng lại** — mọi bước sau đều dựa vào đây.

### 3.2 — Bộ lọc phiếu nháp

Đặt `Công ty = Miyano`, `Tháng = 7`, `Năm = 2026`.

- [ ] **Không** tick `Gồm cả phiếu nháp` → bảng **rỗng** (đúng: 6 phiếu 7/2026 đang là nháp).
- [ ] **Có** tick → hiện **6 dòng nhân viên + 1 dòng TỔNG CỘNG**.

### 3.3 — Nút Export

- [ ] Bấm **Menu (⋯) → Export**. Hiện hộp thoại **"Xuất bảng lương"**, không phải hộp thoại
      Export mặc định của Frappe.
- [ ] Có ô `Định dạng` (mặc định **Excel — mẫu Miyano, có khối ký**) và khi chọn Excel thì hiện
      thêm mục **Khối trình ký** với 2 ô `Người lập`, `Người duyệt`.
- [ ] Gõ `Người lập` = tên bạn, `Người duyệt` = tên giám đốc → bấm **Tải về**.
- [ ] File tải về tên **`Bang luong 07-2026.xlsx`**.

### 3.4 — Nội dung file Excel

Mở file vừa tải:

- [ ] **Dòng 1–3** (căn trái): `CÔNG TY TNHH MIYANO VIỆT NAM` / `MST: 0109529507` / `Địa chỉ: …`
- [ ] **Dòng 5–6** (căn giữa): `BẢNG THANH TOÁN TIỀN LƯƠNG` / `Tháng 07 Năm 2026`
- [ ] Vì đang bật phiếu nháp, dòng 6 có thêm **`— GỒM CẢ PHIẾU NHÁP — CHƯA CHỐT`**
      *(đây là chốt an toàn: bản chưa chốt không được trông giống bản chính thức)*
- [ ] **Cột A là STT** chạy 1…6, **không** phải mã `HR-EMP-…`
- [ ] Tiền hiện dạng **`25,994,783`** (có dấu phân cách nghìn), căn phải
- [ ] Dòng **TỔNG CỘNG** in đậm, nền xám nhạt, **không** có số thứ tự
- [ ] Cuối bảng có khối ký: dòng `Hà Nội, ngày … tháng … năm …`, hai chức danh
      **Người lập** / **Người duyệt**, chừa 6 dòng trống để ký tay, rồi tới hai cái tên bạn vừa gõ
- [ ] In thử (Ctrl+P): **khổ ngang**, cả 21 cột lọt **một trang ngang**

### 3.5 — Không làm hỏng bảng chấm công

Phần dùng chung (tiêu đề công ty + khối ký) đã được tách ra module chung, nên phải kiểm bảng chấm
công vẫn nguyên vẹn:

- [ ] Mở **Bảng chấm công tháng** → Export → Excel: file vẫn **có màu**, vẫn có khối chú thích và
      khối ký như trước.

---

## 4. Nghiệm thu SỐ LIỆU (phần quan trọng nhất)

Tôi đã đối chiếu **6/6 phiếu tháng 7/2026** (đủ 6 loại lương) giữa phiếu lương và engine tính lương:
**65/66 ô khớp tuyệt đối**. Dưới đây là cách bạn tự kiểm lại bằng tay.

### 4.1 — Bảng số liệu tham chiếu (7/2026, đã tick "Gồm cả phiếu nháp")

| # | Họ tên | Loại | Công (H) | Lương thực tế (I) | Ăn trưa (J) | Thuế (Q) | Thực lĩnh (T) |
|---|---|---|---|---|---|---|---|
| 1 | hieu chu | Bán thời gian | 22.5 | 9.782.609 | 0 | 2.445.652 | 9.782.609 |
| 2 | Nguyễn Văn An | Khoán | 19.5 | 20.000.000 | 0 | 0 | 20.000.000 |
| 3 | Trần Thị Bình | Toàn thời gian | 19.5 | 25.434.783 | 560.000 | 0 | 25.994.783 |
| 4 | Lê Văn Cường | Toàn thời gian | 22.0 | 14.634.783 | 595.000 | 0 | 15.229.783 |
| 5 | Phạm Thị Dung | Chuyên gia | 22.5 | 25.000.000 | 0 | 2.777.778 | 25.000.000 |
| 6 | Hoàng Văn Em | Bán thời gian | 22.5 | 13.206.522 | 0 | 1.467.391 | 13.206.522 |
| | **TỔNG CỘNG** | | | **108.058.697** | **1.155.000** | **6.690.821** | **109.213.697** |

- [ ] Số trên màn hình khớp bảng này.
- [ ] Cột **Thực lĩnh (T)** của dòng TỔNG CỘNG = **109.213.697** (bằng tổng 6 dòng trên).

### 4.2 — Tự kiểm công thức bằng tay: 2 ca đại diện

**Ca A — Trần Thị Bình (Chính thức, có BHXH, có người phụ thuộc, không phải nộp thuế)**

Dữ kiện: lương ngày công F = 30.000.000 · công 19,5/23 · ăn 16 buổi · 2 người phụ thuộc ·
lương đóng BHXH G = 30.000.000

| Bước | Công thức | Kết quả |
|---|---|---|
| I | `ROUND(30.000.000 ÷ 23 × 19,5)` | **25.434.783** |
| J | `16 × 35.000` | **560.000** |
| K | `I + J` | **25.994.783** |
| N | `15.500.000 + 2 × 6.200.000` | **27.900.000** |
| O | `MAX(K − N − J, 0)` = `MAX(25.994.783 − 27.900.000 − 560.000, 0)` | **0** |
| Q | O = 0 nên không phải nộp thuế | **0** |
| R | `30.000.000 × 21,5%` | **6.450.000** |
| S | `30.000.000 × 10,5%` | **3.150.000** |
| T | `= K` (trả NET, công ty nộp thay thuế + BH) | **25.994.783** |
| U | `K + Q + S − J` = `25.994.783 + 0 + 3.150.000 − 560.000` | **28.584.783** |

**Ca B — Phạm Thị Dung (Chuyên gia, khấu trừ 10%)**

Dữ kiện: thù lao trọn gói F = 25.000.000 (không nhân theo công) · không đăng ký giảm trừ · không BHXH

| Bước | Công thức | Kết quả |
|---|---|---|
| I | trọn gói, không nhân công | **25.000.000** |
| K | `I + J` (J = 0) | **25.000.000** |
| O | `MAX(K − N − J, 0)`, N = 0 | **25.000.000** |
| P | `ROUND(O ÷ 0,9)` — quy đổi NET → gross | **27.777.778** |
| Q | `ROUND(P × 10%)` | **2.777.778** |
| T | `= K` | **25.000.000** |
| U | `K + Q + S − J` | **27.777.778** |

- [ ] Hai ca trên khớp đúng con số trên báo cáo và trong file Excel.

### 4.3 — Nguồn tham số đang chạy

Kiểm nhanh ở **MVL Payroll Settings** (Desk → tìm "MVL Payroll Settings"):

- [ ] Giảm trừ bản thân **15.500.000** · mỗi người phụ thuộc **6.200.000**
- [ ] Ăn trưa **35.000**/buổi · BH công ty **21,5%** · BH người lao động **10,5%**
- [ ] Hệ số thử việc **0,85**

Sửa ở đây là số trên bảng lương đổi theo — **không phải sửa code**.

---

## 5. Việc còn lại trước khi có bảng lương THẬT để ký

Bảng đang hiện là **dữ liệu demo** (hieu chu, Nguyễn Văn An, Trần Thị Bình, … là nhân viên thử),
và **mọi phiếu đều là nháp**. Để ra bản chính thức đem ký:

1. **Chốt công tháng**: cổng `hrms_enforce_sheet_gate` đang **BẬT**, nên phiếu lương không submit
   được khi kỳ chưa có **Bảng Công Tháng** đã chốt. Bảng công 7/2026 (`BCT-2026-00001`) hiện đang ở
   trạng thái **đã huỷ** → phải soát và chốt lại.
2. **Submit các phiếu lương** của kỳ.
3. Mở lại báo cáo, **bỏ tick** `Gồm cả phiếu nháp` → bảng hiện đủ số, tiêu đề **không còn** dòng
   cảnh báo → Export ra bản chính thức đem trình ký.

---

## 6. Điểm đã biết, cần bạn quyết

### 6.1 — Cột U của loại **Khoán** hiện 0

Cấu trúc lương `Khoán` **cố ý** không có thành phần *Thu nhập chịu thuế kê khai*
(`setup_mvl.py`: "khoán trọn gói, KHÔNG khấu trừ thuế → không cần cột kê khai U"), trong khi engine
tính ra 20.000.000. Hệ quả: dòng TỔNG CỘNG cột U là **97.899.518** thay vì 117.899.518.

Đây là quyết định **chính sách thuế**, không phải lỗi kỹ thuật — tôi không tự sửa.
→ **Bạn xác nhận muốn kê khai thu nhập khoán thì tôi thêm thành phần vào cấu trúc Khoán.**

### 6.2 — Chưa có lối vào từ workspace

Hiện phải tìm báo cáo qua ô tìm kiếm. Nếu muốn, tôi thêm shortcut **Bảng lương MVL** vào workspace
*Chi trả lương* cho HR bấm thẳng.

### 6.3 — Chưa đẩy lên GitHub

Nhánh đang trước `origin` 34 commit. Nói một tiếng là tôi `git push`.

---

## 7. Nếu cần trả lại như cũ

Hai commit này **revert được sạch**, không đụng dữ liệu lương:

```bash
cd /home/miyano/frappe-bench/apps/hrms
git revert 81bd2c2 75fc7f3      # bỏ đổi tên báo cáo + bỏ chức năng xuất Excel
cd /home/miyano/frappe-bench && bench --site miyano migrate
```

Lưu ý: patch đổi tên báo cáo đã chạy nên revert code thôi **chưa** đổi tên bản ghi Report về cũ —
báo về, tôi đổi lại bằng một dòng `frappe.rename_doc`.

Toàn bộ chức năng này **chỉ đọc**: không ghi Salary Slip, không tính lại đồng nào — mọi con số lấy
nguyên từ `Salary Detail` đã chốt trên phiếu. Lương không thể bị xê dịch bởi việc xuất file.

---

## 8. Bằng chứng kiểm thử

| Hạng mục | Kết quả |
|---|---|
| Engine tính lương ↔ tài liệu `Cong_thuc_tinh_luong_MVL.md` | 14/14 test xanh |
| 6 phiếu 7/2026 thật ↔ engine (11 cột × 6 người) | **65/66 khớp tuyệt đối** (1 điểm ở mục 6.1) |
| Test xuất Excel bảng lương (mới) | 14/14 xanh |
| Test báo cáo bảng lương | 2/2 xanh |
| Test xuất Excel bảng chấm công (không hồi quy) | 23/23 xanh |
| Toàn bộ bộ test lương + chấm công liên quan | **112 xanh**, harness không rò dữ liệu |
| Lint (`pre-commit`, ruff + prettier) | sạch |
