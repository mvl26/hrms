# Báo cáo data test — chức năng tự chấm ăn trưa + chọn tay per-ngày

Ngày chạy: **2026-08-27** · Site: `miyano` · Commit: `dafe46a`, `d282d26`
Spec: [`docs/spec/lunch-days-attendance.md`](spec/lunch-days-attendance.md) §5 · Kế hoạch: [`docs/tasks/plan-lunch-auto-and-override.md`](tasks/plan-lunch-auto-and-override.md)

> **Trạng thái: CHỜ DUYỆT.** Chức năng đã chạy đúng 32/32 phép thử. Nhưng phần soát dữ liệu thật
> phát hiện một tình huống **spec chưa lường** — người *miễn chấm công* — cần bạn quyết trước khi
> chạy nốt tháng 6 và tháng 8. Xem §4.

---

## 1. Cách chạy

Toàn bộ chạy **trên site thật** nhưng **không ghi một dòng nào**: `frappe.db.commit` bị vô hiệu
hoá, mọi thao tác ghi nằm trong savepoint và `rollback()` ở `finally`. Phần soát dữ liệu (§3) là
truy vấn **chỉ đọc**.

Bốn phần: **A** ma trận luật (thuần hàm) · **B** ba đường ghi trên DB thật · **C** cổng bất biến số
công · **D** soát toàn bộ dữ liệu thật 3 tháng.

## 2. Kết quả — 32/32 PASS

### A. Ma trận luật (16/16)

| Tình huống | Kết quả |
|---|---|
| Present `X`, 2 dấu 08:00–17:30 (phủ giờ trưa) | ✅ có ăn |
| Present `X`, 2 dấu 08:00–11:00 (về trước trưa) | ✅ không |
| Present `X`, **1 dấu 08:00** (quên chấm ra) | ✅ có ăn |
| Present `X`, **1 dấu 14:00** (chiều mới tới) | ✅ không |
| Present `X`, 1 dấu 12:30 (giữa giờ trưa) | ✅ không |
| Present `X`, **0 dấu** (chấm tay) | ✅ có ăn |
| Half Day `1/2X`, 2 dấu phủ giờ trưa | ✅ có ăn |
| Half Day `1/2X`, 1 dấu 08:00 | ✅ không |
| Half Day `1/2X`, 0 dấu | ✅ không |
| On Leave `P`, dù đủ dấu phủ giờ trưa | ✅ không |
| Absent `V` | ✅ không |
| `CT` công tác, dù đủ dấu phủ giờ trưa | ✅ không |
| `W` làm tại nhà, dù đủ dấu phủ giờ trưa | ✅ không |
| override **Có** trên ngày nghỉ phép | ✅ có ăn |
| override **Không** dù đủ dấu phủ giờ trưa | ✅ không |
| override `Tự động` | ✅ đi nhánh tự động |

### B. Ba đường ghi (13/13)

| Đường | Phép thử | Kết quả |
|---|---|---|
| Lưu Attendance | chấm tay Present không dấu → có ăn | ✅ |
| | chấm tay Half Day không dấu → không | ✅ |
| | mã `CT` → không | ✅ |
| | **override `Không` sống sót qua 2 lần lưu** | ✅ |
| Soát công | sửa `X` → `P` thì **hết** ăn trưa | ✅ |
| | sửa `V` → `X` (không dấu) thì **có** ăn trưa | ✅ |
| | sửa `X` → `CT` thì không ăn trưa | ✅ |
| | **soát công không đè lên lựa chọn tay** | ✅ |
| Recompute | sửa lại cờ bị sai | ✅ |
| | tôn trọng override `Có` | ✅ |

### C. Cổng bất biến số công (3/3)

Đổi ô "Ăn trưa" qua cả `Có` / `Không` / `Tự động`: `status`, `leave_type`, `half_day_status`,
`custom_work_credit` **không xê dịch**. Ăn trưa và số công độc lập nhau — đúng yêu cầu bắt buộc của
repo (`CLAUDE.md`: payroll-invariance gate).

## 3. Soát dữ liệu thật — cả 3 tháng

| Kỳ | Bản ghi | Đang có | Đúng luật mới | Lệch | Chênh tiền |
|---|---|---|---|---|---|
| 2026-06 | 130 | 84 buổi | 85 buổi | **1** | +35.000đ |
| 2026-07 | 132 | 102 buổi | 102 buổi | **0** | 0đ ✅ *(đã chạy 27/08)* |
| 2026-08 | 84 | 51 buổi | 71 buổi | **20** | +700.000đ |

Tháng 7 lệch 0 vì đã chạy `recompute_lunch_flags(7, 2026)` sau khi bạn duyệt — bằng chứng chức năng
đã ổn định trên kỳ đã xử lý.

---

## 4. ⚠️ Việc cần bạn quyết — người *miễn chấm công*

**Toàn bộ 20 ngày lệch của tháng 8 thuộc về đúng 2 người, và cả 2 đều là *miễn chấm công*:**

| Nhân viên | Miễn chấm công | Checkin tháng 8 | Bản ghi tự sinh |
|---|---|---|---|
| `hieu chu` (HR-EMP-00001) | ✅ | 4 | 12/14 |
| `Phạm Thị Dung` (HR-EMP-00005) | ✅ | **0** | 11/14 |
| 4 người còn lại | ❌ | 26 mỗi người | 0/14 |

Đây là tình huống **spec §5 chưa lường**. Yêu cầu ban đầu của bạn nói về *chấm công tạo tay* và
*ngày sửa qua soát công* — những ngày HR chủ động xác nhận. Nhưng người miễn chấm công thì hệ thống
**tự sinh `X` cho mọi ngày làm việc** (`custom_auto_filled`), nên luật "Present + không dấu chấm →
có ăn" sẽ cấp phụ cấp ăn trưa **mỗi ngày, tự động, vĩnh viễn**, mà không có bằng chứng nào là họ có
mặt tại công ty. Phạm Thị Dung không hề chấm công lần nào trong tháng 8.

**Tác động tiền hôm nay: 0đ.** Cả hai đang thuộc cấu trúc lương không có thành phần phụ cấp ăn trưa:

| Cấu trúc | Có phụ cấp ăn trưa |
|---|---|
| Chính thức, Thử việc | ✅ |
| **Bán thời gian** (`hieu chu`), **Chuyên gia** (`Phạm Thị Dung`), Khoán | ❌ |

Nhưng hai hệ quả vẫn thật: **(1)** báo cáo và Bảng Công Tháng sẽ hiển thị họ ăn 20 suất không có căn
cứ; **(2)** ngày nào một trong hai chuyển sang cấu trúc *Chính thức* thì thành tiền thật ngay, âm
thầm.

### Ba lựa chọn

| | Cách làm | Hệ quả |
|---|---|---|
| **A** *(khuyến nghị)* | Không tự cấp ăn trưa cho bản ghi **tự sinh** (`custom_auto_filled = 1`). Muốn có thì HR chọn `Có` từng ngày. | Đúng phạm vi bạn yêu cầu ban đầu; chấm tay và soát công vẫn được hưởng. Tháng 8 chỉ còn lệch 0 ngày. |
| **B** | Loại theo **người**: ai `custom_exempt_from_checkin = 1` thì không tự cấp. | Tương tự A nhưng cứng hơn — kể cả ngày HR sửa tay cho họ cũng không được. |
| **C** | Giữ nguyên như đang chạy. | Hai người trên được 20 suất/tháng tự động, không bằng chứng. Nay 0đ, sau này thành tiền nếu đổi cấu trúc. |

Tôi nghiêng về **A**: nó bám đúng nguyên tắc gốc của spec ("ăn trưa = có mặt thực tế tại công ty"),
đồng thời vẫn giải quyết trọn vấn đề bạn nêu. Ngày tự sinh không phải là ngày ai đó xác nhận có mặt
— nó chỉ là hệ quả của việc miễn chấm công.

---

## 5. Đề xuất các bước tiếp

1. **Bạn chọn A / B / C** ở §4.
2. Nếu **A** hoặc **B**: tôi sửa luật (thêm một điều kiện loại trừ), bổ sung test, chạy lại data
   test này, rồi mới recompute.
3. Nếu **C**: chạy luôn `recompute_lunch_flags` cho tháng 6 và tháng 8.
4. Chạy nốt **tháng 6** (1 ngày, +35.000đ — ngày `X` chấm tay của `hieu chu`, không phụ thuộc lựa
   chọn trên vì đây là ngày *không* tự sinh). *(Nếu chọn A thì cần kiểm lại ngày này có phải tự sinh
   không trước khi chạy.)*
5. Sau recompute: đối chiếu lại phụ cấp **J** trên các phiếu lương của kỳ tương ứng.

## 6. Phụ lục — bằng chứng

- Kịch bản data test: `/tmp/datatest.py` · kết quả đầy đủ: `/tmp/datatest.out`
- Bộ test tự động của repo: **187 test xanh**, `HARNESS_NO_LEAK`, lint sạch
- Đối chiếu phụ cấp J sau lượt recompute tháng 7: **khớp 6/6 phiếu**, không phiếu nào đổi số
