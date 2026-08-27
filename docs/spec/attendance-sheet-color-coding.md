# Spec: Mã màu cho bảng chấm công (report + bản in)

> Status: **APPROVED (Phase 1 / SPECIFY).** Chốt trong phiên 2026-07-23. Nối tiếp bộ VN
> attendance-code đã ship (`docs/spec/attendance-code-timekeeping.md`, `docs/spec/bang-cong-thang-doctype.md`,
> `docs/spec/vn-holiday-and-symbol-standardization.md`). Lưu dưới `docs/spec/` theo quy ước repo.

## Objective

Bảng chấm công hiện ra dạng lưới chữ đen–trắng: một ô `1/2P` (nghỉ phép nửa ngày + làm nửa
ngày) lẫn giữa hàng trăm ô `X` thì không nhìn ra. Thêm **mã màu nền** cho mỗi ô mã công để trạng
thái mỗi ngày đọc được bằng mắt trong một cái liếc — đi làm đủ, nghỉ phép, làm nửa ngày, vắng…

Đây là thay đổi **thuần hiển thị**: KHÔNG đổi bất cứ dữ liệu nào (không `status` / `leave_type` /
`half_day_status` / field nào), KHÔNG schema, KHÔNG migration, KHÔNG fixtures. Additive và
`git revert`-được. **Không phải cổng sign-off lương** (payroll đọc `status`/`leave_type`/
`half_day_status`, không đọc gì mới; số liệu bảng công `get_sheet_rows` không đổi).

**Success (đợt này):**
1. Report **"Monthly Attendance Report"** (xem trên Desk) tô nền mỗi ô mã công theo trạng thái ngày.
2. **Bản in** của DocType **"Monthly Attendance Sheet"** (Bảng Công Tháng — print format
   `monthly_attendance_sheet`) tô cùng bảng màu đó; in giấy/PDF có màu, đọc tốt.
3. Bảng màu + logic map **định nghĩa một chỗ duy nhất** (Python), report và print format cùng dùng —
   không lặp map ở 2 nơi.
4. `get_sheet_rows` (mã công + tổng theo loại) **bất biến** trước/sau; có test chứng minh.

## Locked decisions (2026-07-23)

1. **Phạm vi = report trên màn hình + bản in.** KHÔNG tô lưới child-table trên form DocType (grid
   Frappe), KHÔNG động Vue PWA — tính năng bảng công là Desk-only theo thiết kế cũ.
2. **9 trạng thái màu** (nền pastel + chữ đậm, đọc tốt khi in, đủ cả nền sáng & tối của Desk):

   | Trạng thái (state key) | Ý nghĩa | Mã công gộp vào |
   |---|---|---|
   | `work` — 🟢 xanh lá | Đi làm đủ / công tác | X · CT |
   | `half` — 🟣 tím | **Làm nửa ngày** (bất kỳ ô nào có nửa buổi đi làm) | 1/2P · 1/2K · NN · ô ghép kiểu `X/P` |
   | `leave` — 🟡 vàng | Nghỉ phép năm | P |
   | `sick` — 🟠 cam | Nghỉ ốm / thai sản / TNLĐ / chăm con | Ô · Cô · TS · T |
   | `absent` — 🔴 đỏ | Vắng | V |
   | `unpaid` — 🌸 hồng đậm | Nghỉ không lương | K |
   | `comp` — 🟩 xanh ngọc | Nghỉ bù | NB |
   | `holiday` — 🔵 xanh dương | Nghỉ lễ (có lương) | NL (marker) |
   | `off` — ⚪ xám | Nghỉ tuần / sau nghỉ việc | `–` (marker) |

   Ngoài ra: ô trống (chưa vào làm / không dữ liệu) → không tô.
3. **Ô nửa ngày tô nguyên ô màu tím** (theo lời HR "tím = có làm nửa ngày"). KHÔNG chia đôi ô hai
   tông màu — đã cân nhắc, bỏ vì phức tạp và in kém chắc chắn; có thể nâng cấp sau nếu HR muốn.
4. **Map trạng thái suy từ `category` của Attendance Code** (đã có sẵn trong `get_code_map()`), KHÔNG
   hard-code từng mã. Mã mới HR thêm về sau, chỉ cần đặt đúng `category`, là tự có màu. Marker calendar
   (`–`, `NL`) và ô ghép `A/B` xử lý riêng trong hàm phân loại.
5. **Bảng màu do phiên này chốt (mockup đã duyệt)** — cả biến thể nền sáng và nền tối.

## Design

### Nguồn màu duy nhất (Python, trong module report `monthly_attendance_report`)

- `CATEGORY_STATE: {category → state_key}` — map `category` của Attendance Code sang một trong 9 state
  (`Công`→`work`, `Phép`→`leave`, `Ốm`/`Thai sản`/`Tai nạn LĐ`→`sick`, `Không lương`→`unpaid`,
  `Nghỉ bù`→`comp`, `Vắng`→`absent`, `Nghỉ lễ`→`holiday`). `Công tác`/CT → `work`.
- `STATE_STYLE: {state_key → {label, bg_light, fg_light, bg_dark, fg_dark}}` — 9 màu đã duyệt.
- `day_state(symbol, code_map) → state_key | None` — hàm phân loại **một ô đã hiển thị**:
  - marker `–` → `off`; `NL` → `holiday`; rỗng → `None` (không tô);
  - ô ghép `A/B`: nếu **bất kỳ** nửa là mã "Công" mà `work_fraction < 1` **hoặc** hai nửa khác nhau →
    `half` (tím); nếu cả hai nửa cùng một mã đủ công → theo category của mã đó;
  - ô đơn: nếu là mã Công với `work_fraction < 1` (NN) → `half`; ngược lại theo `CATEGORY_STATE[category]`.
  - Quy tắc chốt cho `half`: **cứ có phần đi làm nửa buổi thì tím** (1/2P, 1/2K, NN, ghép sáng/chiều).

### Hai chỗ hiển thị cùng dùng nguồn trên

1. **Report "Monthly Attendance Report"** (`monthly_attendance_report.js`): thêm `formatter(value, row,
   column, data, default_formatter)`. Chỉ tô các cột ngày (`day_1..day_31`). Formatter tra `state` của
   ô rồi trả HTML nền màu. Map `symbol→state` + `state→màu` nạp một lần trong `onload` qua một
   whitelisted method (`get_color_map()`), không hard-code trong JS. Màu dùng biến theo nền sáng/tối
   của Desk (`data-theme` / `prefers-color-scheme`), hoặc chọn cặp bg/fg tương phản đủ cho cả hai.
2. **Print format `monthly_attendance_sheet`** (Jinja, server-side): với mỗi ô ngày gọi `day_state` +
   `STATE_STYLE` để gắn `style="background:...;color:..."`. Bản in mặc định nền sáng (in giấy) → dùng
   `bg_light`/`fg_light`. Có **chú giải màu** cuối trang.

### Payroll-neutral & an toàn

- Không hàm nào ghi dữ liệu; chỉ đọc `get_sheet_rows` như hiện tại. Không thêm/sửa field, doctype, patch,
  fixtures. Thuần thêm `.js` formatter + một khối Python (hằng số + `day_state` + `get_color_map`) +
  chỉnh print format `.json`/Jinja. Toàn bộ `git revert`-được.

## Testing

- **Unit `day_state()`** — bảng phủ: 12 mã enterable + CT + 3 marker (`–`, `NL`, rỗng) + ô ghép
  (`X/P`, `X/Ô`, `P/Ô`) → đúng state kỳ vọng. Đặc biệt: 1/2P, 1/2K, NN, và mọi ô ghép → `half`.
- **Bất biến số liệu** — `get_sheet_rows(filters)` trả totals/day-symbols **y hệt** trước/sau khi thêm
  code màu (không regress logic report).
- **Map đầy đủ** — mọi `category` của Attendance Code hiện có đều có mặt trong `CATEGORY_STATE` (test
  fail nếu HR thêm category mới mà quên map → nhắc bổ sung màu).
- **E2E render** — chạy report + render print format cho một tháng thật trên `miyano` (qua harness
  rollback / bench execute, chỉ đọc), mắt xác nhận ô 1/2P ra tím, X ra xanh, V ra đỏ…

## Out of scope (đợt này)

- Tô lưới child-table trên form DocType (grid Frappe) — chỉ report + bản in.
- Vue PWA / roster.
- Ô chia đôi hai tông màu cho ca ghép (nâng cấp tương lai nếu HR muốn).
- Đổi mã / category / logic nghiệp vụ — không đụng.
