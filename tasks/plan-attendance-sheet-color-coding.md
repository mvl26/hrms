# Implementation Plan: Mã màu cho bảng chấm công (report + bản in)

Spec: `spec/attendance-sheet-color-coding.md` (APPROVED 2026-07-23). Nhánh: `feat/skip-attendance-diag`.

## Overview

Thêm mã màu nền cho từng ô mã công ở **hai chỗ hiển thị**: report "Monthly Attendance Report" (xem
Desk) và print format "Monthly Attendance Sheet" (bản in HR ký). Thuần hiển thị — không đổi dữ
liệu/schema/lương. Một nguồn màu Python (`day_state` + `STATE_STYLE` + `CATEGORY_STATE`) dùng chung.

## Architecture Decisions

- **Nguồn màu duy nhất trong `hrms/hr/report/monthly_attendance_report/monthly_attendance_report.py`.**
  Report và print format cùng gọi vào đó — không lặp map ở JS/Jinja.
- **Phân loại theo `work_fraction` trước, rồi `category`** (không hard-code từng mã):
  - `symbol` rỗng → `None` (không tô); `–` → `off`; `NL` → `holiday`.
  - ô ghép `A/B`: nếu **có nửa nào là mã đi làm** (`work_fraction > 0`) → `half`; nếu không, lấy
    `category` của nửa sáng → `CATEGORY_STATE`.
  - ô đơn `c`: nếu `0 < work_fraction < 1` → `half` (bắt 1/2P, 1/2K, NN); nếu không → `CATEGORY_STATE[c.category]`.
  - `CATEGORY_STATE`: Công→`work`, Phép→`leave`, Ốm/Thai sản/Tai nạn LĐ→`sick`, Nghỉ bù→`comp`,
    Không lương→`unpaid`, Vắng→`absent`, **Việc riêng→`leave`** (mặc định, xem Open Questions).
- **Report on-screen:** `execute()` tính sẵn `_state_<day>` cho mỗi dòng (không thêm cột hiển thị); một
  whitelisted `get_color_map()` trả `STATE_STYLE`; `formatter` trong `.js` đọc `_state_<day>` từ `data`
  rồi tô nền. → toàn bộ logic phân loại nằm ở Python, JS chỉ tra màu.
- **Bản in:** phơi `day_state`+style ra **một Jinja method** qua `hooks.py` (`jinja.methods`), print
  format gọi `{{ attendance_cell_style(cell) }}` cho mỗi ô ngày. Không thêm field vào DocType Detail.
- **Màu:** `STATE_STYLE` giữ cả cặp sáng/tối; report dùng biến hợp nền Desk, bản in dùng bản sáng.

## Task List

### Phase 1: Nền màu (Python, TDD)

#### Task 1: Model màu + hàm phân loại `day_state`
**Description:** Thêm `CATEGORY_STATE`, `STATE_STYLE` (9 state, cặp bg/fg sáng+tối theo mockup đã duyệt),
và `day_state(symbol, code_map) -> state_key | None` vào `monthly_attendance_report.py`. Không đụng
`get_sheet_rows`/`execute` ở task này.

**Acceptance criteria:**
- [ ] `day_state` trả đúng state cho: X·CT→`work`; 1/2P·1/2K·NN→`half`; P→`leave`; Ô·Cô·TS·T→`sick`;
      V→`absent`; K→`unpaid`; NB→`comp`; N→`leave`; `–`→`off`; `NL`→`holiday`; rỗng→`None`.
- [ ] Ô ghép: `X/P`,`X/Ô`→`half`; `P/Ô` (không nửa đi làm)→`sick` (theo category nửa sáng).
- [ ] Mọi `category` của Attendance Code hiện có đều có trong `CATEGORY_STATE` (test completeness fail nếu thiếu).

**Verification:**
- [ ] `test_day_state_*` xanh (bảng phủ toàn mã + marker + split) qua harness rollback.
- [ ] `get_sheet_rows` output không đổi (chưa động tới).

**Dependencies:** None · **Files:** `monthly_attendance_report.py`, `test_monthly_attendance_report.py` · **Scope:** S

### Checkpoint: Phase 1
- [ ] Test phân loại xanh; chưa có thay đổi hành vi report/print.

### Phase 2: Tô màu report trên màn hình

#### Task 2: Precompute state trong `execute` + `get_color_map` + formatter JS
**Description:** `execute()` gắn `_state_<day>` cho mỗi dòng data (từ `day_state`), không thêm cột nhìn
thấy. Thêm `@frappe.whitelist() get_color_map()` trả `STATE_STYLE`. Trong `monthly_attendance_report.js`
thêm `formatter` tô nền các cột `day_*` theo `_state_<day>`, màu nạp một lần ở `onload`.

**Acceptance criteria:**
- [ ] Mỗi dòng `execute` có `_state_<day>` khớp `day_state` của ô đó; các cột hiển thị (`day_*`, `cat_*`) **giữ nguyên**.
- [ ] `get_color_map()` trả đủ 9 state với cặp màu sáng+tối.
- [ ] Formatter chỉ tô cột ngày, không tô cột NV/tổng; ô rỗng không tô.

**Verification:**
- [ ] `get_sheet_rows`/`execute` (symbols + totals) **bất biến** so với trước (test so sánh).
- [ ] Test `get_color_map` có đủ state.
- [ ] Manual: mở report tháng thật trên `miyano` → ô 1/2P tím, X xanh, V đỏ, `–` xám, `NL` xanh dương (cả nền sáng/tối).

**Dependencies:** Task 1 · **Files:** `monthly_attendance_report.py`, `monthly_attendance_report.js`, `test_monthly_attendance_report.py` · **Scope:** M

### Checkpoint: Phase 2
- [ ] Report có màu; số liệu bất biến; `bench build --app hrms` sạch.

### Phase 3: Tô màu bản in

#### Task 3: Jinja method + print format có màu + chú giải màu
**Description:** Phơi helper `attendance_cell_style(symbol)` (dựa `day_state`+`STATE_STYLE` bản sáng) làm
Jinja method qua `hooks.py`. Sửa print format `monthly_attendance_sheet` html: mỗi `<td>` ngày thêm
`style` nền màu; thêm khối chú giải màu (9 state) cuối trang.

**Acceptance criteria:**
- [ ] `attendance_cell_style("1/2P")` trả style nền tím; `"X"`→xanh; `"-"`→xám; `""`→rỗng (không style).
- [ ] Print format render mỗi ô ngày có nền đúng state; hàng tổng + chú thích mã giữ nguyên; thêm chú giải màu.
- [ ] Không thêm field nào vào Monthly Attendance Sheet / Detail.

**Verification:**
- [ ] Test Jinja method trả style đúng cho mẫu symbol.
- [ ] E2E: render print format một Bảng Công Tháng thật (`miyano`, chỉ đọc) → mắt thấy màu; đối chiếu report cùng tháng khớp màu.

**Dependencies:** Task 1 · **Files:** `hooks.py`, `hrms/hr/print_format/monthly_attendance_sheet/monthly_attendance_sheet.json`, test · **Scope:** S–M

### Checkpoint: Complete
- [ ] Cả report + bản in cùng bảng màu; số liệu bất biến; toàn bộ additive/`git revert`-được.
- [ ] Ghi chú deploy: report `.js` cần `bench build --app hrms`; print format + hooks jinja cần
      `bench --site miyano migrate` (re-sync print format) — **migrate re-sync fixtures = cổng ask-first**,
      xin xác nhận trước khi chạy trên site. Dev có thể reload_doc print format để xem trước.

## Risks and Mitigations
| Risk | Impact | Mitigation |
|---|---|---|
| Frappe strip key lạ (`_state_*`) khỏi row → formatter không thấy state | Med | Xác nhận ở Task 2; nếu bị, đổi sang JS tự phân loại từ symbol + map `code→category` fetch (logic nhỏ), vẫn giữ style ở Python. |
| Print format là standard (`standard:"Yes"`) → deploy cần migrate (re-sync fixtures) | Med | Tách bước; dev dùng `reload_doc`; migrate trên site chỉ chạy khi có sign-off. |
| HR thêm Attendance Code category mới sau này quên gán màu | Low | Test completeness `CATEGORY_STATE` fail → nhắc bổ sung. |
| Màu nền tối Desk khó tương phản | Low | `STATE_STYLE` có cặp riêng cho nền tối; kiểm ở Task 2 manual. |

## Open Questions
- **Mã N (Việc riêng, nghỉ hiếu hỉ có lương) tô màu gì?** Mặc định plan: gộp `leave` (vàng, như phép).
  Nếu HR muốn màu riêng (VD nâu/xanh dương khác) → đổi 1 dòng `CATEGORY_STATE`. Không chặn build.
