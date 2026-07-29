# CÔNG THỨC TÍNH LƯƠNG — CÔNG TY TNHH MIYANO VIỆT NAM

> Trích xuất từ file `3. MVL_Bang luong 06.2026_Lan final.xlsx` (sheet chính **Salary 06.2026**, tham chiếu thêm các sheet **SALARY**, **BHXH**, **07 2024**).
> Toàn bộ công thức Excel gốc được giữ nguyên, kèm diễn giải và ví dụ số liệu thật trong bảng lương.
> Phân loại lao động chuẩn hóa gồm 5 loại: **Chính thức toàn thời gian — Thử việc — Bán thời gian — Khoán — Chuyên gia**, trả theo **NET** hoặc **GROSS**.

---

## 1. THAM SỐ CHUNG (kỳ lương 06/2026)

| Tham số | Giá trị | Ô trong file |
|---|---|---|
| Số công làm việc chuẩn tháng | **22 công** (thay đổi theo tháng, VD tháng 5 là 21) | `$H$7` |
| Giảm trừ gia cảnh bản thân | **15.500.000 đ/tháng** | cột `L` |
| Giảm trừ mỗi người phụ thuộc | **6.200.000 đ/người/tháng** | `$M$7` |
| Phụ cấp ăn trưa (miễn thuế TNCN) | **35.000 đ/ngày công** | cột `J` |
| Bảo hiểm bắt buộc — Công ty trả | **21,5%** × Lương đóng BHXH | `$R$7` |
| Bảo hiểm bắt buộc — NLĐ trả | **10,5%** × Lương đóng BHXH | `$S$7` |

Chi tiết tỷ lệ bảo hiểm 32% (tổng 2 bên) theo sheet **BHXH**:

| Loại | Tỷ lệ tổng (Cty + NLĐ) |
|---|---|
| BHXH | 25,5% (17,5% + 8%) |
| BHYT | 4,5% (3% + 1,5%) |
| BHTN | 2% (1% + 1%) |
| **Cộng** | **32%** = 21,5% (Cty) + 10,5% (NLĐ) |

---

## 2. DANH MỤC TRƯỜNG DỮ LIỆU BẮT BUỘC KHI THIẾT LẬP BẢNG LƯƠNG

> Nguyên tắc: bảng lương khi setup phải khai báo **đủ toàn bộ trường dữ liệu** dưới đây — gồm nhóm THAM SỐ kỳ lương, nhóm NHẬP TAY theo từng nhân sự và nhóm CÔNG THỨC tự tính. Không được thiết lập kiểu chỉ nhập mỗi số tiền thực nhận, vì như vậy không tính được thuế, bảo hiểm, chi phí công ty và không kiểm soát/đối chiếu được số liệu.

### 2.1. Nhóm THAM SỐ theo kỳ lương (khai báo 1 lần/tháng)

| Trường | Kiểu | Ghi chú |
|---|---|---|
| Kỳ lương (từ ngày – đến ngày) | Ngày | VD: 01/06/2026 – 30/06/2026 |
| Số công làm việc chuẩn tháng | Số | 22 (tháng 6/2026), 21 (tháng 5/2026) — thay đổi từng tháng |
| Mức giảm trừ bản thân | Tiền | 15.500.000 đ/tháng |
| Mức giảm trừ người phụ thuộc | Tiền | 6.200.000 đ/người/tháng |
| Đơn giá ăn trưa | Tiền | 35.000 đ/ngày |
| Tỷ lệ BH công ty trả | % | 21,5% |
| Tỷ lệ BH NLĐ trả | % | 10,5% |
| Biểu thuế lũy tiến + bảng quy đổi NET→GROSS | Bảng | Xem Bước 6, Bước 7 |

### 2.2. Nhóm NHẬP TAY theo từng nhân sự (dữ liệu gốc — bắt buộc khai báo khi setup)

| Cột | Trường | Kiểu | Ghi chú |
|---|---|---|---|
| A | STT | Số | |
| B | Họ tên | Text | |
| C | Loại lao động | Danh mục | **Chính thức toàn thời gian / Thử việc / Bán thời gian / Khoán / Chuyên gia** |
| D | Loại lương (Status) | Danh mục | NET / GROSS |
| E | Hệ số lương | Số | Chính thức = 1 ; **Thử việc = 0,85** |
| F | Lương ngày công (lương cơ bản thỏa thuận) | Tiền | Căn cứ HĐLĐ; với Khoán/Chuyên gia là số tiền khoán tháng |
| G | Lương đóng BHXH | Tiền | Có thể ≠ F; **trống** nếu không thuộc diện đóng (thử việc, bán thời gian, khoán, chuyên gia) |
| H | Số công làm việc thực tế | Số | Từ bảng chấm công, nhận số lẻ (VD 11,5) |
| (J) | Số ngày ăn tại công ty | Số | Nhập tay, có thể khác số công |
| L | Giảm trừ bản thân | Tiền | 15.500.000 nếu đăng ký giảm trừ tại công ty; trống nếu không |
| M | Số người phụ thuộc | Số | Theo hồ sơ đăng ký NPT |
| V | TK hạch toán chi phí | Danh mục | 6421 (QLDN) / 6411 (bán hàng), đối ứng 334 |
| — | MST cá nhân, Cư trú/Không cư trú, Ghi chú | Text/Cờ | Quyết định mức khấu trừ thuế của bán thời gian (10% / 20%) — xem mục 4.3 |

*(Bản GROSS đầy đủ như sheet SALARY / 07 2024 còn thêm các cột nhập tay: Thưởng/trợ cấp khác, Điện thoại, Xăng xe, KPI.)*

### 2.3. Nhóm CÔNG THỨC tự tính (không nhập tay — khóa công thức khi setup)

| Cột | Trường | Công thức (chi tiết ở Mục 3) |
|---|---|---|
| I | Lương thực tế | `ROUND(F×E/Công chuẩn×H, 0)` |
| J | Phụ cấp ăn trưa | `Số ngày ăn × 35.000` |
| K | Tổng thu nhập chưa trừ thuế, BH | `I + J` |
| N | Tổng các khoản giảm trừ | `L + 6.200.000 × M` |
| O | Thu nhập làm căn cứ quy đổi | `MAX(K − N − J, 0)` |
| P | Thu nhập tính thuế (gross-up) | Theo loại lao động — Bước 6 và Mục 4 |
| Q | Thuế TNCN | Theo loại lao động — Bước 7 và Mục 4 |
| R | BH công ty trả | `ROUND(G × 21,5%, 0)` |
| S | BH NLĐ trả | `ROUND(G × 10,5%, 0)` |
| T | Thực lĩnh | NET: `= K` ; GROSS: `= K − Q − S` |
| U | Thu nhập chịu thuế (kê khai) | `K + Q + S − J` |
| Dòng cuối | TỔNG CỘNG | `SUM()` từng cột F → U |

---

## 3. CÔNG THỨC LÕI (áp dụng cho mọi nhân sự)

Ký hiệu theo cột của sheet `Salary 06.2026` (dòng 9 là dòng đầu tiên):

### Bước 1 — Lương thực tế theo ngày công

```
Lương thực tế (I) = ROUND( Lương ngày công (F) × Hệ số lương (E) / Số công chuẩn (H7) × Số công thực tế (H) , 0 )
```
Excel gốc: `I9 = ROUND(F9*E9/$H$7*H9,0)`

- **Hệ số lương (E)**: nhân viên chính thức = `1` ; **thử việc = `0,85`** (nhận 85% lương).
- Nghỉ không lương → giảm Số công thực tế (H). VD: Phạm Thị Yến lương 20.000.000, đi làm 10/22 công → I = 20.000.000 × 10/22 = **9.090.909 đ**.
- Với **Khoán / Chuyên gia**: F là số tiền khoán tháng, E = 1, H = công chuẩn → I = nguyên số tiền khoán.

### Bước 2 — Phụ cấp ăn trưa

```
Phụ cấp ăn trưa (J) = Số ngày ăn tại công ty × 35.000
```
Excel gốc: `J9 = 21*35000` (số ngày ăn nhập tay từng người, có thể khác số công). Chỉ áp dụng cho nhân viên chính thức và thử việc.

### Bước 3 — Tổng thu nhập (chưa trừ thuế, BH)

```
Lương thực lĩnh chưa trừ thuế TNCN, BHXH (K) = I + J
```
Excel gốc: `K9 = SUM(I9:J9)` (sheet SALARY cũ còn cộng thêm Thưởng/trợ cấp khác, Điện thoại nếu có).

### Bước 4 — Tổng giảm trừ gia cảnh

```
Tổng giảm trừ (N) = Giảm trừ bản thân (L = 15.500.000) + 6.200.000 × Số người phụ thuộc (M)
```
Excel gốc: `N9 = L9 + $M$7*M9`

> Lưu ý trong file: chỉ nhân sự đăng ký giảm trừ tại công ty mới điền `L = 15.500.000`; người không đăng ký (VD dòng 9 — Đoàn Ngọc Anh) để trống → toàn bộ thu nhập vào diện quy đổi tính thuế. Bán thời gian / Khoán / Chuyên gia không áp dụng giảm trừ.

### Bước 5 — Thu nhập làm căn cứ quy đổi (do trả lương NET)

```
Thu nhập làm căn cứ quy đổi (O) = MAX( K − N − J , 0 )
```
Excel gốc: `O9 = IF(K9-N9-J9>0, K9-N9-J9, 0)`

(Trừ phụ cấp ăn trưa J vì đây là khoản miễn thuế.)

### Bước 6 — Quy đổi lương NET → Thu nhập tính thuế (GROSS-UP)

*Chỉ áp dụng cho Chính thức toàn thời gian và Thử việc; các loại còn lại quy đổi theo mức riêng ở Mục 4.*

```
Thu nhập tính thuế (P):
  O ≤ 9.500.000                 → P = O / 0,95
  9.500.000 < O ≤ 27.500.000    → P = (O − 500.000) / 0,9
  27.500.000 < O ≤ 51.500.000   → P = (O − 3.500.000) / 0,8
  51.500.000 < O ≤ 79.500.000   → P = (O − 9.500.000) / 0,7
  O > 79.500.000                → P = (O − 14.500.000) / 0,65
```
Excel gốc:
```excel
P9 =IF(O9<=9500000,O9/0.95,
   IF(AND(O9>9500000,O9<=27500000),(O9-500000)/0.9,
   IF(AND(O9>27500000,O9<=51500000),(O9-3500000)/0.8,
   IF(AND(O9>51500000,O9<=79500000),(O9-9500000)/0.7,
   IF(O9>79500000,(O9-14500000)/0.65)))))
```

### Bước 7 — Thuế TNCN (biểu lũy tiến từng phần 5 bậc)

```
Thuế TNCN (Q):
  P < 10.000.000                → Q = P × 5%
  10.000.000 ≤ P < 30.000.000   → Q = P × 10% − 500.000
  30.000.000 ≤ P < 60.000.000   → Q = P × 20% − 3.500.000
  60.000.000 ≤ P < 100.000.000  → Q = P × 30% − 9.500.000
  P ≥ 100.000.000               → Q = P × 35% − 14.500.000
  (P < 0 → Q = 0)
```
Excel gốc:
```excel
Q9 =IF(P9<0,0,
   IF(P9<10000000,P9*0.05,
   IF(P9<30000000,P9*0.1-500000,
   IF(P9<60000000,P9*0.2-3500000,
   IF(P9<100000000,P9*0.3-9500000,P9*0.35-14500000)))))
```

### Bước 8 — Bảo hiểm bắt buộc

```
BH công ty trả (R)  = ROUND( Lương đóng BHXH (G) × 21,5% , 0 )
BH NLĐ trả (S)      = ROUND( Lương đóng BHXH (G) × 10,5% , 0 )
```
Excel gốc: `R10 = ROUND(G10*$R$7,0)` ; `S10 = ROUND(G10*$S$7,0)`

- **Lương đóng BHXH (G)** nhập riêng từng người (thường = lương ngày công F, nhưng có thể khác).
- Chỉ **nhân viên chính thức toàn thời gian** đóng BHXH; Thử việc / Bán thời gian / Khoán / Chuyên gia để trống G → R = S = 0.

### Bước 9 — Thực lĩnh và chi phí quy đổi

Vì công ty trả **lương NET** (công ty chịu thay thuế TNCN + BH phần NLĐ):

```
Thực lĩnh (T) = K   (đúng bằng lương thỏa thuận + phụ cấp ăn)
Thu nhập chịu thuế quy đổi để kê khai (U) = K + Q + S − J
```
Excel gốc: `T9 = K9` ; `U9 = K9 + Q9 + S9 - J9`

> **Tổng chi phí công ty cho 1 nhân sự** = K (thực lĩnh) + Q (thuế nộp thay) + S (BH phần NLĐ nộp thay) + R (BH phần công ty).

---

## 4. CÔNG THỨC THEO TỪNG LOẠI LAO ĐỘNG

### 4.1. CHÍNH THỨC TOÀN THỜI GIAN, lương NET

Áp dụng đầy đủ Bước 1 → 9, với **Hệ số E = 1**, có Lương đóng BHXH (G), có phụ cấp ăn trưa, có giảm trừ gia cảnh nếu đăng ký.

**Ví dụ thật (Tạ Trường Xuân):** F = 25.000.000; H = 22/22 công; J = 21 ngày ăn × 35.000 = 735.000; 1 người phụ thuộc.

- I = 25.000.000 × 1 × 22/22 = 25.000.000
- K = 25.000.000 + 735.000 = 25.735.000
- N = 15.500.000 + 6.200.000 × 1 = 21.700.000
- O = 25.735.000 − 21.700.000 − 735.000 = 3.300.000
- P = 3.300.000 / 0,95 = 3.473.684
- Q = 3.473.684 × 5% = **173.684 đ** (công ty nộp thay)
- R = 25.000.000 × 21,5% = 5.375.000 ; S = 25.000.000 × 10,5% = 2.625.000 (công ty nộp thay)
- **Thực lĩnh T = 25.735.000 đ**

### 4.2. THỬ VIỆC

Giống 4.1 nhưng:

```
Hệ số lương (E) = 0,85   →   Lương thử việc = 85% lương chính thức
Lương đóng BHXH (G) = trống  →  không đóng BHXH trong thời gian thử việc (R = S = 0)
```

Excel gốc: dòng 16–17 (`E16 = 0.85`, G trống); sheet cũ 07 2024 ghi thẳng `E8 = 12987000*85%`.

**Ví dụ thật (Nguyễn Yến Chi):** F = 13.500.000; E = 0,85; H = 11,5/22 công.

- I = 13.500.000 × 0,85 × 11,5/22 = **5.998.295 đ**
- K = 5.998.295 + 9 × 35.000 = 6.313.295 → sau giảm trừ 15.500.000 → O = 0 → **thuế = 0**
- Thực lĩnh T = **6.313.295 đ**

### 4.3. BÁN THỜI GIAN (parttime), lương NET

Đặc điểm: **không** phụ cấp ăn trưa (J trống), **không** giảm trừ gia cảnh (L, M trống), **không** đóng BHXH (G trống). Thuế khấu trừ toàn phần theo đối tượng cư trú:

| Đối tượng | Quy đổi NET → gross | Thuế TNCN | Ví dụ trong file |
|---|---|---|---|
| Cá nhân **cư trú** — khấu trừ **10%** | `P = ROUND(O/0,9, 0)` | `Q = ROUND(P × 10%, 0)` | Vũ Văn Tiến Tuyền: O = 10.000.000 → P = 11.111.111 → Q = 1.111.111 |
| Cá nhân **không cư trú** (người nước ngoài) — khấu trừ **20%** | `P = ROUND(O/0,8, 0)` | `Q = ROUND(P × 20%, 0)` | Koshioka Hiroshi: O = 3.000.000 → P = 3.750.000 → Q = 750.000 |

```
Lương parttime (I) = ROUND( F × E / Công chuẩn × Số công thực tế , 0 )
Thực lĩnh (T) = I   (NET — công ty nộp thay thuế)
Thu nhập chịu thuế kê khai (U) = K + Q + S
```

### 4.4. LƯƠNG KHOÁN

Trường hợp **Nguyễn Thị Khương** (dòng 20): nhận mức khoán cố định hàng tháng, không phụ cấp, không giảm trừ, không BHXH, **không khấu trừ thuế**.

```
Thu nhập khoán (I) = số tiền khoán tháng (F)
P = 0 ; Q = 0
Thực lĩnh (T) = nguyên số tiền khoán
Chi phí công ty = số tiền khoán
```
Excel gốc: `P20 = 0` → `Q20 = 0`.

**Ví dụ thật:** khoán 5.000.000/tháng → thực lĩnh **5.000.000 đ**, không phát sinh thuế và bảo hiểm.

### 4.5. LƯƠNG CHUYÊN GIA

Trường hợp **Chu Văn Hiếu (lớn)** — ghi chú sheet SALARY: *"chi trả dạng chuyên gia"*: thù lao NET, không phụ cấp, không giảm trừ, không BHXH, công ty nộp thay thuế khấu trừ **10%** trên thu nhập đã quy đổi:

```
Thù lao chuyên gia NET (O) = toàn bộ số tiền chi trả
Quy đổi gross:  P = O / 0,9
Thuế TNCN:      Q = P × 10%
Thực lĩnh = số tiền NET thỏa thuận
Chi phí công ty = O + Q
```
Excel gốc: `P14 = O14/0.9` ; `Q14 = P14*0.1`

**Ví dụ thật:** thù lao 30.000.000 NET → P = 33.333.333 → thuế nộp thay Q = **3.333.333 đ**.

### 4.6. LƯƠNG NET (tổng quát)

Toàn bộ bảng lương hiện tại trả theo NET (cột Status = "NET"): số thỏa thuận là số **thực nhận**, công ty gross-up để nộp thay thuế + BH phần NLĐ.

```
Thực lĩnh  = Lương thỏa thuận theo công + phụ cấp
Thuế TNCN  = tính trên thu nhập ĐÃ QUY ĐỔI (Bước 6–7 với chính thức/thử việc; /0,9 hoặc /0,8 với bán thời gian/chuyên gia; = 0 với khoán)
Chi phí công ty = Thực lĩnh + Thuế nộp thay + BH NLĐ nộp thay + BH phần công ty
Thu nhập chịu thuế kê khai (U) = Thực lĩnh + Thuế + BH NLĐ − Phụ cấp ăn miễn thuế
```

### 4.7. LƯƠNG GROSS

Khi thỏa thuận GROSS thì **bỏ bước quy đổi** (Bước 6): thuế tính thẳng trên thu nhập sau giảm trừ, và NLĐ tự chịu thuế + BH phần mình. Cấu trúc này chính là sheet **07 2024** trong file:

```
Thu nhập trước thuế GROSS (L) = Lương theo công + Ăn trưa + Điện thoại + Xăng xe + KPI + Thưởng
                                 L7 = SUM(G7:K7)
Thu nhập chịu thuế (M) = GROSS − Ăn trưa − Điện thoại        [M7 = L7-H7-I7]
Thu nhập tính thuế (P) = MAX( M − Giảm trừ bản thân − Giảm trừ phụ thuộc − BH NLĐ đóng , 0 )
Thuế TNCN (Q) = biểu lũy tiến từng phần trên P               [như Bước 7]
BH NLĐ (S) = Lương đóng BHXH × 10,5%
THỰC LĨNH (T) = GROSS − Thuế TNCN − BH NLĐ                  [T7 = ROUND(L7-Q7-S7,-3)]
```

> Sheet 07 2024 là bảng cũ (công ty S-TEC) dùng biểu thuế và mức giảm trừ cũ (11.000.000/4.400.000, 7 bậc 5–35%). Khi áp GROSS cho kỳ hiện tại thì thay bằng tham số mới ở Mục 1 và biểu thuế 5 bậc ở Bước 7.

**Chuyển đổi nhanh GROSS ↔ NET:**

```
NET  = GROSS − Thuế TNCN(GROSS) − BH NLĐ (10,5%)
GROSS = quy đổi ngược từ NET theo bảng Bước 6 (sau đó cộng lại BH NLĐ nếu thỏa thuận NET sau BH)
```

---

## 5. CÔNG THỨC TỔNG HỢP CUỐI BẢNG

```
Dòng TỔNG CỘNG:      =SUM(cột 9 : cột 20)  cho từng cột F → U
Tổng chi BHXH phải nộp = Tổng R + Tổng S    (đối chiếu sheet BHXH: Lương đóng BHXH × 32%)
Phân bổ hạch toán:   SUMIF theo TK (6421 - QLDN / 6411 - bán hàng), đối ứng 334
```

---

## 6. BẢNG TRA NHANH — CHỌN CÔNG THỨC THEO LOẠI LAO ĐỘNG

| Loại lao động | Hệ số E | BHXH (G) | Giảm trừ (L,M) | Phụ cấp ăn (J) | Cách tính thuế | Ví dụ trong file |
|---|---|---|---|---|---|---|
| Chính thức toàn thời gian, NET | 1 | Có (21,5% + 10,5%) | Có | Có (35k/ngày) | Quy đổi bậc (B6) → lũy tiến 5 bậc (B7) | Tạ Trường Xuân |
| Thử việc | **0,85** | Không | Có (nếu đăng ký) | Có | Như chính thức | Phan Thị Thu Lan, Nguyễn Yến Chi |
| Bán thời gian, cư trú | 1 | Không | Không | Không | O/0,9 × 10% | Vũ Văn Tiến Tuyền |
| Bán thời gian, không cư trú (nước ngoài) | 1 | Không | Không | Không | O/0,8 × 20% | Koshioka Hiroshi |
| Khoán | 1 | Không | Không | Không | Không khấu trừ (Q = 0) | Nguyễn Thị Khương |
| Chuyên gia | 1 | Không | Không | Không | O/0,9 × 10% trên toàn bộ | Chu Văn Hiếu (lớn) |
| Lương GROSS | 1 | Có | Có | Có | Thuế trực tiếp, NLĐ tự chịu: Thực lĩnh = GROSS − Q − S | Sheet 07 2024 |

---

*Tài liệu chuẩn hóa ngày 28/07/2026, trích xuất nguyên trạng công thức từ file bảng lương 06.2026.*
