# Spec: Chuẩn hoá chấm công & nghỉ lễ theo chuẩn Việt Nam — Holiday List (WS1) + ký hiệu VN / logic nửa ngày (WS2)

> Status: **DRAFT for approval (Phase 1 / SPECIFY).** Scope + 6 quyết định chốt trong phiên
> 2026-07-14. Nối tiếp bộ VN attendance-code đã ship (`spec/attendance-code-timekeeping.md`,
> `spec/bang-cong-thang-doctype.md`). Lưu dưới `spec/` theo quy ước repo. **Không plan/implement
> tới khi được duyệt.**

## Objective

Chuẩn hoá phần **chấm công + nghỉ lễ** cho đúng thông lệ / luật Việt Nam **bằng chính các doctype
của ERP** (không thêm doctype mới). Hai workstream độc lập nhưng bổ trợ:

- **WS1 — Lịch nghỉ lễ VN (Holiday List).** Hôm nay site `miyano` **không có Holiday List thật nào**
  (chỉ 3 list test), nên mọi thứ phụ thuộc nó đều "trống": auto-attendance không biết ngày lễ/CN, báo
  cáo bảng công không tô được **CN/NL**, và (về sau) payroll không tính đúng nghỉ lễ. WS1 tạo một
  Holiday List VN đúng chuẩn (ngày nghỉ hàng tuần + nghỉ lễ Điều 112 BLLĐ 2019) và rà soát logic resolve
  lịch cho từng nhân viên.
- **WS2 — Ký hiệu (HR chốt) + logic nửa ngày.** Giữ nguyên bộ mã hiện có (X, P, Ô…), chỉ (a) hiển thị
  **ngày nghỉ = "-"** trên bảng công, (b) thêm **mã N** = nghỉ việc riêng có lương (kết hôn/tang), (c) làm
  **chính xác logic nửa ngày** (đi làm nửa ngày vs nghỉ phép nửa ngày vs tổ hợp sáng/chiều) — tất cả
  **bất biến lương** (payroll-neutral), có test chứng minh. TT200 (01a-LĐTL) chỉ là tham chiếu, **không**
  rename hàng loạt.

**Success (đợt này):**
1. HR tạo được **một Holiday List VN / công ty / năm** qua một helper idempotent: ngày nghỉ hàng tuần
   (CN, hoặc T7+CN) + các ngày lễ **dương lịch** cố định tự sinh; **Tết Âm lịch + Giỗ Tổ HR nhập tay**.
2. Báo cáo/bảng công tô đúng **"-" (ngày nghỉ) / "NL" (lễ)** từ Holiday List đó; auto-attendance bỏ qua
   ngày lễ đúng.
3. **X giữ nguyên**; ngày nghỉ hiển thị **"-"**; **mã N** (việc riêng có lương) + Leave Type nền hoạt động;
   mọi tổ hợp nửa ngày tính `custom_cong` đúng; **payroll bất biến** trước/sau (cổng invariance mở rộng).
4. WS1 để lại một Holiday List **đúng** làm nền cho bước chẩn đoán payroll "nghỉ lễ có lương" sau này.

## Locked decisions (2026-07-14)

1. **Phạm vi = WS1 + WS2.** Tự động cấp phép năm 12 ngày + thâm niên (Điều 113/114) → **hoãn sang spec
   riêng.**
2. **Giữ nguyên doctype ERP** (`Holiday List`, `Attendance`, `Attendance Code`, `Shift Type`, `Salary
   Slip`). Không tạo doctype mới; chỉ thêm fixtures/helper/config + chỉnh sửa nhỏ có kiểm soát.
3. **Cơ sở tính lương** = lương tháng cố định, **chia theo số ngày làm việc thực của tháng** (mẫu số =
   ngày làm việc, không kể ngày nghỉ hàng tuần). → nghỉ lễ phải được tính là **công hưởng lương**.
4. **Ký hiệu do HR chốt (2026-07-14); TT200 (01a-LĐTL) chỉ là *tham chiếu* — KHÔNG rename hàng loạt:**
   - **X** = ngày làm việc đủ/bình thường → **giữ nguyên** (không đổi sang "+").
   - **"-"** = **ngày nghỉ** (nghỉ hàng tuần / ngày không làm việc không có bản ghi) → hiển thị dấu gạch
     trên bảng công (thay marker "CN" cũ). Đây là **marker suy từ lịch** (không phải Attendance Code, không
     tạo bản ghi).
   - **N** = **nghỉ việc riêng có lương** (kết hôn, đám tang — Điều 115) → **mã công mới** gắn một **Leave
     Type có lương** ("Nghỉ việc riêng"/hiếu hỉ, `is_lwp = 0`).
   - Các mã còn lại **giữ nguyên** (P, 1/2P, Ô, Cô, TS, T, NB, K, 1/2K, NN, V, CT) — **không** đổi K→KL,
     **không** thêm H trừ khi HR yêu cầu sau. → tránh migrate mã hàng loạt + rủi ro vận hành.
   - Xung đột "N" cũ (báo cáo dùng N = *đã nghỉ việc*): **N nay = việc riêng**; ngày sau `relieving_date`
     hiển thị **"-"** (ngày nghỉ) thay vì "N".
5. **Ngày lễ âm lịch (Tết, Giỗ Tổ) = HR nhập tay hằng năm.** Helper chỉ tự sinh ngày nghỉ hàng tuần +
   lễ **dương lịch** (01/01, 30/04, 01/05, 02/09 ×2). Không cần thư viện/âm lịch.
6. **Phần "nghỉ lễ có lương" (đụng payroll) = TÁCH RA, KHÔNG build đợt này.** Trình tự bắt buộc: (a) build
   Holiday List đúng ở WS1 → (b) chẩn đoán trên **salary slip prod thật** cách nghỉ lễ đang vào
   `payment_days` → (c) sửa **tối thiểu** qua **cổng bất biến lương + ký duyệt**. Ghi lại thành spec/tài
   liệu chẩn đoán riêng.
7. **Ngày nghỉ hàng tuần**: mặc định **CN** (`weekly_off = "Sunday"`); nếu tuần 5 ngày thì thêm **T7**.
   Tham số của helper, chốt theo từng site.

## Bối cảnh kỹ thuật (đã điều tra phiên này — không giả định)

- **Ngày làm việc trong tuần + nghỉ hàng tuần + nghỉ lễ đều nằm trong `Holiday List`**, không phải trên
  ca. `Holiday List.weekly_off` (một thứ trong tuần) + nút *Get Weekly Off Dates* sinh các dòng
  `weekly_off = 1`; nghỉ lễ là dòng `weekly_off = 0`. **`Shift Type` chỉ *link* một `holiday_list`**
  (không có cấu hình ngày-làm-việc-theo-tuần). Nhân viên nhận lịch qua
  `get_holiday_list_for_employee`: **Employee → Department → Company** (ERPNext chuẩn).
- **Giới hạn ERP:** `weekly_off` chỉ chọn **một** thứ/lần → muốn cả **T7 + CN** phải chạy sinh 2 lần
  (lý do nên có helper).
- **Giới hạn cho payroll nghỉ lễ:** Salary Slip chỉ có **một** cờ `include_holidays_in_total_working_days`
  áp **chung** cho cả CN lẫn lễ (`salary_slip.py:471-474, 539, 590`) — **không** tách được "tính lễ mà
  không tính CN". Đây chính là nút thắt của phần payroll đã **hoãn** (quyết định #6).
- **Live `miyano`:** `payroll_based_on = 'Leave'`, `include_holidays_in_total_working_days = 0`,
  `consider_unmarked_attendance_as = 'Present'`; **chỉ có Holiday List test**. (Đây là bản dev gần trống:
  10 nhân viên, 0 salary structure/slip — dữ liệu thật ở prod.)
- **Ký hiệu "N" — đã chốt lại:** báo cáo cũ dùng N = *đã nghỉ việc* (suy từ `relieving_date`,
  `spec/attendance-code-timekeeping.md:98`). HR chốt (2026-07-14): **N = nghỉ việc riêng có lương
  (kết hôn/tang)**; ngày sau `relieving_date` chuyển hiển thị **"-"** (ngày nghỉ). (TT200 dùng N = ngừng
  việc — Miyano không dùng khái niệm này.)

## WS1 — Holiday List VN

### Helper (idempotent, on-demand — KHÔNG tự chạy khi migrate)

`hrms/setup_vn_holiday.py::create_vn_holiday_list(year, company, weekly_off_days=("Sunday",), name=None)`
→ tạo/cập nhật một `Holiday List`:

1. `from_date = 01/01/year`, `to_date = 31/12/year`, tên mặc định `f"VN {company} {year}"`.
2. Với mỗi thứ trong `weekly_off_days` (VD `("Sunday",)` hoặc `("Saturday","Sunday")`): set
   `weekly_off` rồi gọi cơ chế sẵn có sinh các dòng `weekly_off = 1` (chạy lặp cho từng thứ).
3. Thêm các **ngày lễ dương lịch cố định** (`weekly_off = 0`): **01/01** Tết Dương lịch, **30/04** Ngày
   Giải phóng, **01/05** Quốc tế Lao động, **02/09 + 01/09 (hoặc 03/09)** Quốc khánh (2 ngày, Điều 112).
4. **KHÔNG** tự thêm Tết Âm lịch (5 ngày) + Giỗ Tổ (10/3 âm) → để trống + ghi chú nhắc HR nhập tay
   (quyết định #5). Helper **idempotent**: chạy lại không nhân đôi dòng (dedup theo `holiday_date`).

**Cách dùng:** `bench --site <s> execute hrms.setup_vn_holiday.create_vn_holiday_list --kwargs "{...}"`,
hoặc một nút trên Desk / bước onboarding. **Không** nhét vào `ensure_defaults`/`after_migrate` — tạo
Holiday List là **tạo dữ liệu**, đụng công ty thật → **ask-first** (nhất quán với quyết định #3 của
`spec/geofence-map-and-default-setup.md`: "Do NOT seed a sample Holiday List").

### Rà soát resolve + tiêu thụ

- Test + tài liệu hoá: nhân viên **không set `holiday_list`** → rơi về **Company default**; đảm bảo báo
  cáo bảng công (CN/NL) + auto-attendance (bỏ qua ngày lễ) đọc đúng list này.
- Không sửa `get_holiday_list_for_employee` (ERP chuẩn) trừ khi test phát hiện sai; nếu sai → sửa nhỏ,
  có test.

## WS2 — Ký hiệu (HR chốt) + logic nửa ngày

Phạm vi WS2 đã **thu hẹp** theo chốt của HR (2026-07-14): **giữ nguyên bộ mã hiện có**, chỉ (a) thêm
marker **"-"** cho ngày nghỉ, (b) thêm **mã N** cho việc riêng có lương, (c) làm chính xác logic nửa ngày.
**Không** rename hàng loạt theo TT200 → **không** migrate mã cũ.

### Thay đổi ký hiệu (chốt)

| Ký hiệu | Nghĩa | Loại | Hành động |
|---|---|---|---|
| **X** | Đi làm đủ công | Attendance Code (đã có) | **Giữ nguyên.** |
| **"-"** | **Ngày nghỉ** (nghỉ hàng tuần / ngày trống không bản ghi / sau `relieving_date`) | **Marker suy từ lịch** (không tạo bản ghi) | **Thêm ở báo cáo/bảng công** thay marker "CN"; ngày lễ vẫn hiển thị **"NL"** riêng (vì có lương). |
| **N** | **Nghỉ việc riêng có lương** (kết hôn 3, con kết hôn 1, tang 3 — Điều 115) | **Attendance Code mới** + **Leave Type mới** ("Nghỉ việc riêng", `is_lwp = 0`, có lương) | **Thêm fixture** (`maps_to_status = On Leave`, `is_paid = 1`, `work_fraction = 0`) + bridge test. |
| P, 1/2P, Ô, Cô, TS, T, NB, K, 1/2K, NN, V, CT | (như hiện tại) | Attendance Code (đã có) | **Giữ nguyên — KHÔNG đổi** (không K→KL, không thêm H). |

> Hệ quả: **không có patch migrate mã** trong đợt này (không đổi giá trị `custom_*_code` cũ). "-" là thay
> đổi **hiển thị** ở lớp báo cáo; "N" là **thêm mới** (không đụng bản ghi cũ). Cả hai payroll-neutral.

### Hai diễn giải cần anh xác nhận (nếu sai thì sửa spec)

1. **"-" chỉ cho ngày nghỉ hàng tuần**; **ngày lễ vẫn hiển thị "NL"** (để phân biệt "lễ có lương" với
   "nghỉ thường"). Nếu anh muốn ngày lễ cũng là "-" thì nói.
2. **Leave Type mới "Nghỉ việc riêng"** (`is_lwp = 0`, có lương) làm nền cho mã **N** — thêm vào
   `leave_type.json` + fixtures filter. (Thêm Leave Type mới = ask-first theo CLAUDE.md; đây là *create-if-
   missing*, không sửa Leave Type đang có.)

### Logic nửa ngày / sáng–chiều (làm chính xác)

- Kiểm chứng **forward bridge** cho mọi tổ hợp sáng/chiều: `X|P` (đi làm nửa + phép nửa → Half Day,
  `half_day_status=Present`, `leave_type=phép`, `cong=0.5`), `X|Ô`, `X|K`, `X|N` (việc riêng nửa ngày),
  `NN`, `1/2P`, `1/2K`…
- `custom_cong = Σ (work_fraction × 0.5)` đúng cho từng nửa; mỗi cột nghỉ = `Σ (1 − work_fraction) × 0.5`
  theo `category` (đã có ở `attendance.py`; đợt này **verify + phủ test**, không viết lại).
- **Bất biến lương:** mã **N** mới + mọi tổ hợp nửa ngày phải qua
  `test_attendance_code_payroll_invariance.py` mở rộng (payment_days / absent_days / LWP byte-identical so
  với nhập native).

### Không migrate mã cũ trong đợt này

Vì **không rename** mã nào (K, X… giữ nguyên) → **không cần patch migrate dữ liệu**. Chỉ **thêm** mã `N`
(không đụng bản ghi cũ) + đổi **hiển thị** ngày nghỉ sang "-" ở lớp báo cáo. Nếu về sau HR muốn align sâu
hơn theo TT200 (K→KL, thêm H) thì đó là spec/patch riêng, kèm runner chụp payroll trước/sau (0 thay đổi).

## Tech Stack

Frappe/ERPNext HRMS v15, Python (controllers + `frappe.qb`), fixtures JSON. Test qua **rollback harness**
trong console (KHÔNG `bench run-tests` trên `miyano`).

## Commands

```bash
cd /home/miyano/frappe-bench
# WS1: tạo Holiday List VN cho 1 năm/công ty (on-demand, ask-first trên prod)
bench --site miyano execute hrms.setup_vn_holiday.create_vn_holiday_list \
      --kwargs "{'year': 2026, 'company': 'Miyano', 'weekly_off_days': ['Sunday']}"
bench --site miyano migrate           # nạp fixtures mã công đã chuẩn hoá + custom field (nếu có)
# Test: rollback harness trong console (monkeypatch frappe.db.commit→noop; savepoint/rollback mỗi test)
bench build --app hrms                # nếu sửa .js bảng công/print
```

## Project structure (files)

```
hrms/setup_vn_holiday.py                             (mới — create_vn_holiday_list + test)
hrms/fixtures/leave_type.json                        (sửa — + "Nghỉ việc riêng" is_lwp=0, create-if-missing)
hrms/fixtures/attendance_code.json                   (sửa — + mã "N" (On Leave, is_paid, →"Nghỉ việc riêng"))
hrms/hooks.py                                        (sửa — fixtures filter thêm Leave Type mới)
hrms/hr/doctype/attendance/attendance.py             (verify bridge N + nửa ngày — sửa nhỏ nếu test đòi)
hrms/hr/report/bang_cham_cong_thang/…                (marker "-" thay "CN"; sau relieving_date → "-"; giữ "NL")
hrms/hr/doctype/bang_cong_thang/…                    (marker "-" trong print/grid nếu cần đồng bộ report)
hrms/payroll/doctype/salary_slip/test_attendance_code_payroll_invariance.py  (mở rộng: mã N + nửa ngày)
spec/vn-holiday-and-symbol-standardization.md        (spec này)
```
> Chỉ tạo file khi task tương ứng cần. **Không** rename/đổi mã đã có → **không** có patch migrate đợt này.

## Code style

Theo convention đã dùng: thư mục/mã doctype ASCII, **label + ký hiệu VN** trong JSON; tab indent; helper
nhỏ, có docstring nêu "why"; guard idempotent (`frappe.db.exists` trước khi tạo); tái dùng cơ chế Frappe
(Holiday List `get_weekly_off_dates`) thay vì tự code lịch.

## Testing strategy (rollback harness — NEVER `bench run-tests` trên `miyano`)

- **WS1:** `create_vn_holiday_list` sinh đúng số dòng weekly_off (CN → ~52; T7+CN → ~104) + 5 dòng lễ
  dương lịch; **idempotent** (chạy 2 lần không nhân đôi); resolve Company-default cho nhân viên trống
  `holiday_list`; báo cáo tô CN/NL từ list này.
- **WS2 (bất biến lương — GATE):** mở rộng payroll-invariance cho **mã N** + các tổ hợp nửa ngày (`X|P`,
  `X|N`, `NN`, `1/2P`, `1/2K`): dựng Salary Slip trên data cố định, ghi `payment_days`/`absent_days`/LWP,
  chạy bridge, dựng lại → **giống hệt** (mã N có lương → không dock; nửa ngày đúng fraction). Bridge
  unit-test cho từng tổ hợp sáng/chiều + mã N cả ngày.
- **Report marker:** ngày `weekly_off` → "-"; ngày lễ (`weekly_off=0`) → "NL"; ngày sau `relieving_date`
  → "-"; ngày có Attendance vẫn ưu tiên mã của bản ghi. Test `_resolve_day` cho 4 case này.
- Chạy song song 1 tháng với quy trình cũ trước khi cut-over (WS1 Holiday List).

## Boundaries

- **Always:** giữ doctype ERP; helper idempotent; **cổng bất biến lương** trước mọi thay đổi bridge/mã;
  fixtures additive; **stage đúng file của task** (không `git add -A`); test qua rollback harness; revert
  được bằng `git revert`.
- **Ask first (STOP ký duyệt):** chạy `create_vn_holiday_list` / migrate đổi mã trên **prod**; phần
  **payroll "nghỉ lễ có lương"** (quyết định #6 — chẩn đoán prod trước); mọi sửa Leave Type đang có; deploy
  fixtures/print lên prod; đổi `include_holidays_in_total_working_days` hay logic Salary Slip.
- **Never:** đổi `status`/`leave_type`/`half_day_status` semantics; sửa logic payroll khi chưa qua gate +
  ký duyệt; nới lỏng test bất biến để "cho xanh"; tự thêm thư viện âm lịch/geocoding; seed Holiday List tự
  động khi migrate; commit secrets.

## Success Criteria (đợt này)

- [ ] `create_vn_holiday_list(year, company, weekly_off_days)` tạo Holiday List VN đúng (weekly-off + 5 lễ
      dương lịch), idempotent, có test; Tết/Giỗ Tổ để HR nhập tay (có ghi chú).
- [ ] Nhân viên không set `holiday_list` resolve về Company default; báo cáo bảng công tô đúng
      **"-" (ngày nghỉ) / "NL" (lễ)**; auto-attendance bỏ qua ngày lễ — có test/kiểm chứng.
- [ ] **Ký hiệu chốt**: X giữ nguyên; ngày nghỉ → **"-"**; **mã N** = việc riêng có lương (+ Leave Type
      "Nghỉ việc riêng" `is_lwp=0`); các mã khác giữ nguyên. Không rename → không migrate mã.
- [ ] Mọi tổ hợp nửa ngày/sáng-chiều + **mã N** tính `custom_cong` đúng; **payroll bất biến** (gate mở
      rộng xanh: N có lương không dock, nửa ngày đúng fraction).
- [ ] Tất cả reversible `git revert`; fixtures additive; verify trên dev `miyano` qua rollback harness.

## Out of scope (spec/đợt sau)

- **Payroll "nghỉ lễ có lương"** — chẩn đoán prod + sửa tối thiểu (quyết định #6).
- **Tự động cấp phép năm 12 ngày + thâm niên +1/5 năm** (Điều 113/114) — WS3, spec riêng.
- BHXH benefit calc (ốm/thai sản 75%/100%); carry-forward phép năm; nghỉ lễ trùng CN được nghỉ bù.
- Âm lịch tự sinh (Tết/Giỗ Tổ) — HR nhập tay đợt này.

## Open Questions (còn lại — 2 diễn giải + 1 config)

1. **"-" có áp cho ngày lễ không?** Diễn giải mặc định: **không** — ngày nghỉ hàng tuần = "-", **ngày lễ
   vẫn = "NL"** (phân biệt lễ có lương). Nếu HR muốn lễ cũng hiển thị "-" thì sửa.
2. **Leave Type nền cho mã N** tên chính xác là gì? Mặc định **"Nghỉ việc riêng"** (`is_lwp=0`, có lương),
   create-if-missing. Có cần tách cưới/tang thành 2 loại, hay chung 1 loại đủ cho bảng công?
3. **Ngày nghỉ hàng tuần theo site:** mặc định **CN**; nếu Miyano tuần 5 ngày thì thêm **T7** (tham số của
   helper — chốt khi tạo Holiday List thật, không chặn plan).

> Đã chốt (2026-07-14): X giữ nguyên · ngày nghỉ = "-" · N = việc riêng có lương · các mã khác giữ nguyên
> (không rename TT200) · payroll nghỉ lễ tách ra · Tết/Giỗ Tổ nhập tay.
