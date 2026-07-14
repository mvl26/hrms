# Spec: Chuẩn hoá chấm công & nghỉ lễ theo chuẩn Việt Nam — Holiday List (WS1) + ký hiệu TT200 / logic nửa ngày (WS2)

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
- **WS2 — Ký hiệu bảng chấm công theo TT200 + logic nửa ngày.** Đối chiếu 13 mã công hiện có với **mẫu
  bảng chấm công 01a-LĐTL (Thông tư 200/2014/TT-BTC)**, thống nhất ký hiệu, vá các chỗ lệch/thiếu, và
  làm **chính xác logic nửa ngày** (đi làm nửa ngày vs nghỉ phép nửa ngày vs tổ hợp sáng/chiều) — tất cả
  **bất biến lương** (payroll-neutral), có test chứng minh.

**Success (đợt này):**
1. HR tạo được **một Holiday List VN / công ty / năm** qua một helper idempotent: ngày nghỉ hàng tuần
   (CN, hoặc T7+CN) + các ngày lễ **dương lịch** cố định tự sinh; **Tết Âm lịch + Giỗ Tổ HR nhập tay**.
2. Báo cáo/bảng công tô đúng **CN/NL** từ Holiday List đó; auto-attendance bỏ qua ngày lễ đúng.
3. Bộ mã công được **thống nhất theo TT200** (đổi/bổ sung có tài liệu hoá), mọi tổ hợp nửa ngày tính
   `custom_cong` đúng, và **payroll bất biến** trước/sau (cổng invariance mở rộng).
4. WS1 để lại một Holiday List **đúng** làm nền cho bước chẩn đoán payroll "nghỉ lễ có lương" sau này.

## Locked decisions (2026-07-14)

1. **Phạm vi = WS1 + WS2.** Tự động cấp phép năm 12 ngày + thâm niên (Điều 113/114) → **hoãn sang spec
   riêng.**
2. **Giữ nguyên doctype ERP** (`Holiday List`, `Attendance`, `Attendance Code`, `Shift Type`, `Salary
   Slip`). Không tạo doctype mới; chỉ thêm fixtures/helper/config + chỉnh sửa nhỏ có kiểm soát.
3. **Cơ sở tính lương** = lương tháng cố định, **chia theo số ngày làm việc thực của tháng** (mẫu số =
   ngày làm việc, không kể ngày nghỉ hàng tuần). → nghỉ lễ phải được tính là **công hưởng lương**.
4. **Chuẩn ký hiệu = bám sát TT200 (01a-LĐTL)**, chỉ **mở rộng** cho khái niệm TT200 không có
   (nửa ngày, công tác, vắng — vẫn giữ vì bộ máy Miyano cần).
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
- **Xung đột ký hiệu "N":** TT200 **N = Ngừng việc**; báo cáo Miyano đang dùng **N = đã nghỉ việc**
  (suy từ `relieving_date`, `spec/attendance-code-timekeeping.md:98`). Phải giải quyết ở WS2.

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

## WS2 — Ký hiệu TT200 + logic nửa ngày

### Bảng đối chiếu 13 mã hiện có ↔ TT200 (bản nháp để anh chốt)

Mẫu TT200 (01a-LĐTL) quy định: **+/X** lương thời gian · **Ô** ốm · **Cô** con ốm · **TS** thai sản ·
**T** tai nạn · **P** nghỉ phép · **H** hội nghị/học tập · **NB** nghỉ bù · **KL** không lương ·
**N** ngừng việc · **LĐ** nghĩa vụ.

| Miyano hiện tại | Nghĩa | TT200 | Hành động đề xuất |
|---|---|---|---|
| X | Đi làm đủ công | +/X | **Giữ X** (TT200 chấp nhận X). |
| Ô, Cô, TS, T, P, NB | ốm / con ốm / thai sản / TNLĐ / phép / nghỉ bù | Ô,Cô,TS,T,P,NB | **Khớp — giữ.** |
| K | Nghỉ không lương cả ngày | **KL** | **Đổi K → KL** (khớp TT200). ⚠ cần migrate dữ liệu cũ. |
| — (thiếu) | Hội nghị / học tập (có lương) | **H** | **Thêm mã H** + (tuỳ) Leave Type/không, maps_to Present/WFH, paid. |
| — (thiếu) | Việc riêng có lương (cưới 3, con cưới 1, tang 3 — Điều 115) | (ngoài TT200) | **Thêm mã** (VD **R**) + Leave Type "Nghỉ việc riêng có lương" (`is_lwp = 0`). |
| N (báo cáo) | **đã nghỉ việc** | N = **ngừng việc** | **Giải xung đột:** đổi marker "đã nghỉ việc" sang ký hiệu khác (VD giữ nội bộ / dùng khác), trả **N** về đúng nghĩa TT200 hoặc bỏ nếu không dùng ngừng việc. |
| NN, 1/2P, 1/2K, V, CT | nửa ngày / vắng / công tác | (TT200 không có) | **Giữ — mở rộng Miyano**, tài liệu hoá là phần ngoài TT200. |

> Ghi chú: "bám sát TT200" = dùng ký hiệu TT200 ở đâu TT200 có; những khái niệm TT200 **không** định nghĩa
> (nửa ngày, công tác, vắng) vẫn giữ mã Miyano. Bảng cuối cùng do anh duyệt trước khi sửa fixtures.

### Logic nửa ngày / sáng–chiều (làm chính xác)

- Kiểm chứng **forward bridge** cho mọi tổ hợp sáng/chiều: `X|P` (đi làm nửa + phép nửa → Half Day,
  `half_day_status=Present`, `leave_type=phép`, `cong=0.5`), `X|K(L)`, `X|Ô`, `NN`, `1/2P`, `1/2K`, `H`…
- `custom_cong = Σ (work_fraction × 0.5)` đúng cho từng nửa; mỗi cột nghỉ = `Σ (1 − work_fraction) × 0.5`
  theo `category` (đã có ở `attendance.py`; đợt này **verify + phủ test**, không viết lại).
- **Bất biến lương:** mọi mã/tổ hợp mới phải qua `test_attendance_code_payroll_invariance.py` mở rộng
  (payment_days / absent_days / LWP byte-identical so với nhập native).

### Migrate dữ liệu đổi mã (nếu đổi K→KL, thêm H/R, đổi N)

- Đổi **giá trị hiển thị** `custom_attendance_code`/`custom_morning_code`/`custom_afternoon_code` trên
  Attendance cũ — **các field này KHÔNG feed payroll** → **payroll-neutral** (giống backfill patch
  `hrms/patches/v15_0/backfill_attendance_codes.py`). Vẫn **ask-first** khi chạy trên prod, có runner
  chụp payroll trước/sau chứng minh 0 thay đổi, idempotent, revert được bằng cách map ngược.

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
hrms/fixtures/attendance_code.json                   (sửa — chuẩn hoá theo TT200: KL, H, R, giải N)
hrms/fixtures/leave_type.json                        (sửa — +"Nghỉ việc riêng có lương" nếu chốt mã R)
hrms/hr/doctype/attendance/attendance.py             (verify/tighten bridge nửa ngày — sửa nhỏ nếu cần)
hrms/hr/report/bang_cham_cong_thang/…                (giải marker "đã nghỉ việc" vs N; hiển thị KL/H/R)
hrms/hr/doctype/bang_cong_thang/…                    (thêm cột/category nếu bộ mã đổi — nếu cần)
hrms/patches/v15_0/normalize_attendance_codes.py     (mới — migrate mã cũ→TT200, ask-first) + test
hrms/payroll/doctype/salary_slip/test_attendance_code_payroll_invariance.py  (mở rộng test)
spec/vn-holiday-and-symbol-standardization.md        (spec này)
```
> Chỉ tạo file khi task tương ứng cần; không đổi mã nào chưa chốt ở bảng đối chiếu.

## Code style

Theo convention đã dùng: thư mục/mã doctype ASCII, **label + ký hiệu VN** trong JSON; tab indent; helper
nhỏ, có docstring nêu "why"; guard idempotent (`frappe.db.exists` trước khi tạo); tái dùng cơ chế Frappe
(Holiday List `get_weekly_off_dates`) thay vì tự code lịch.

## Testing strategy (rollback harness — NEVER `bench run-tests` trên `miyano`)

- **WS1:** `create_vn_holiday_list` sinh đúng số dòng weekly_off (CN → ~52; T7+CN → ~104) + 5 dòng lễ
  dương lịch; **idempotent** (chạy 2 lần không nhân đôi); resolve Company-default cho nhân viên trống
  `holiday_list`; báo cáo tô CN/NL từ list này.
- **WS2 (bất biến lương — GATE):** mở rộng payroll-invariance cho **mọi** mã/tổ hợp mới (KL, H, R, X|P,
  NN, 1/2P, 1/2K): dựng Salary Slip trên data cố định, ghi `payment_days`/`absent_days`/LWP, chạy bridge,
  dựng lại → **giống hệt**. Bridge unit-test cho từng tổ hợp sáng/chiều.
- **Migrate mã:** runner chụp payroll trước/sau đổi `custom_*_code` → **0 thay đổi**; idempotent.
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
- [ ] Nhân viên không set `holiday_list` resolve về Company default; báo cáo bảng công tô đúng **CN/NL**;
      auto-attendance bỏ qua ngày lễ — có test/kiểm chứng.
- [ ] Bộ mã công **thống nhất theo TT200** (đổi K→KL, thêm H + việc-riêng-có-lương, giải xung đột N) theo
      bảng đối chiếu **anh đã duyệt**; các mã Miyano ngoài TT200 được tài liệu hoá.
- [ ] Mọi tổ hợp nửa ngày/sáng-chiều tính `custom_cong` đúng; **payroll bất biến** (gate mở rộng xanh).
- [ ] Nếu đổi mã: patch migrate `custom_*_code` chứng minh **0 thay đổi payroll**, idempotent, ask-first
      khi chạy prod.
- [ ] Tất cả reversible `git revert`; verify trên dev `miyano` qua rollback harness.

## Out of scope (spec/đợt sau)

- **Payroll "nghỉ lễ có lương"** — chẩn đoán prod + sửa tối thiểu (quyết định #6).
- **Tự động cấp phép năm 12 ngày + thâm niên +1/5 năm** (Điều 113/114) — WS3, spec riêng.
- BHXH benefit calc (ốm/thai sản 75%/100%); carry-forward phép năm; nghỉ lễ trùng CN được nghỉ bù.
- Âm lịch tự sinh (Tết/Giỗ Tổ) — HR nhập tay đợt này.

## Open Questions (cần chốt khi review spec)

1. **Ngày nghỉ hàng tuần theo site:** CN, hay T7+CN? (mặc định CN; xác nhận cho Miyano.)
2. **Bảng ký hiệu cuối cùng:** duyệt bảng đối chiếu WS2 (đặc biệt: mã cho "việc riêng có lương" = **R**?
   và cách giải **N** — trả N về "ngừng việc" hay đổi marker "đã nghỉ việc"?).
3. **Có thực sự đổi X và K không**, hay giữ X + chỉ đổi K→KL? (đổi mã đã quen = migrate + rủi ro vận hành.)
