# Spec: Gộp một quỹ phép năm — mọi nghỉ có lương (trừ miễn trừ) rút từ phép năm

> Status: **Bậc 2 BUILT trên nhánh 2026-07-24** (feat/skip-attendance-diag, commits `bd2fbae`+`T5-6`);
> 6 test xanh qua harness rollback; bảng công (feature cũ) 20 test không hỏng. **CHƯA deploy** (field
> fixture + hook + cấu hình cần migrate/restart + hoà giải allocation = cổng ký, xem cuối plan).
> Mô hình chốt qua Q&A phiên 2026-07-24.
> Nối tiếp và **dựa trên** `spec/leave-entitlement-vn.md` (WS3 — cấp quỹ 12+thâm niên) làm bậc nền.
> Lưu dưới `spec/` theo quy ước repo. **Cổng sign-off cứng:** đụng Leave Type + cầu nối mã-công↔lương
> trên site production có lương đang chạy — mỗi bậc phải chứng minh **lương bất biến** và **không
> deploy khi chưa duyệt**.

## Objective

Miyano quản lý phép theo mô hình **một quỹ**: mỗi nhân viên có **một số dư "Nghỉ phép năm"**
(12 ngày + thâm niên); **mọi loại nghỉ có lương — trừ nhóm miễn trừ — đều rút từ quỹ này**, chỉ khác
nhau ở *lý do* (mã công) để bảng công đọc rõ. Hết quỹ thì **không cho xin nghỉ nữa** (phải chuyển
nghỉ không lương). Nghỉ không lương không trừ quỹ.

Đây là quyết định **nghiệp vụ có chủ đích của Miyano**, đơn giản hoá so với luật (ốm/chăm con ốm vốn
là chế độ BHXH riêng) — được chủ doanh nghiệp chốt để dễ quản lý phép năm.

**Success:**
1. Nhân viên nộp **Đơn xin nghỉ (Leave Application)**, chọn lý do (Ốm / Chăm con ốm / Phép năm); đơn
   rút quỹ **"Nghỉ phép năm"**; Frappe **tự chặn** khi hết số dư (`allow_negative = 0`).
2. Duyệt đơn → Attendance tự sinh → bảng công hiện **đúng mã** (Ô / Cô / P) dù cùng rút một quỹ.
3. Nhóm **miễn trừ** (Thai sản, Việc riêng cưới/tang, TNLĐ) nghỉ **có lương, KHÔNG** rút quỹ phép năm.
4. **Nghỉ bù (NB)** giữ nguyên cơ chế hiện tại — không liên quan quỹ phép.
5. **Nghỉ không lương (K)** không rút quỹ, is_lwp.
6. **Lương bất biến** ở mỗi bậc (gate `status`/`leave_type`/`half_day_status` không đổi ngoài ý muốn).

## Mô hình chốt (2026-07-24)

| Nhóm | Mã công | Rút quỹ phép năm? | Lương | leave_type dùng cho Đơn xin nghỉ |
|---|---|---|---|---|
| **Trừ quỹ** | P, 1/2P, Ô, Cô | ✅ | Có (tới khi hết quỹ) | **"Nghỉ phép năm"** (chung) |
| **Miễn trừ** | TS (thai sản), N (cưới/tang), T (TNLĐ) | ❌ | Có | loại nghỉ riêng của từng mã |
| **Riêng** | NB (nghỉ bù) | ❌ | Có | giữ nguyên cơ chế hiện tại |
| **Không lương** | K, 1/2K | ❌ | Không | "Nghỉ không lương" (is_lwp) |

- **Hết quỹ:** Frappe chặn nộp Đơn xin nghỉ rút quỹ (số dư 0 + `allow_negative=0`). NV chuyển sang
  "Nghỉ không lương" hoặc không nghỉ. HR **không** đánh mã trừ-quỹ vượt số dư.
- Nhóm miễn trừ dùng loại nghỉ riêng, cấu hình để **không** chặn theo quỹ phép (nghỉ chế độ).

## Bổ sung 2026-07-25 — Required "Loại nghỉ" (VN) tự suy mã + nghỉ nửa ngày sáng/chiều

- **Loại nghỉ bắt buộc (tiếng Việt):** field mới `custom_leave_reason` (Select), **hiện + bắt buộc khi
  `leave_type = "Nghỉ phép năm"`**, đúng **3** loại trừ-quỹ ở VN (không thừa không thiếu):
  **Nghỉ phép năm→P · Nghỉ ốm→Ô · Nghỉ chăm con ốm→Cô**. Hệ thống **tự suy mã công** (không nhập mã tay);
  `validate_pool_code` bắt buộc chọn Loại nghỉ hợp lệ. Field cũ `custom_attendance_code` (Link mã) trên
  Leave Application chuyển **ẩn + read-only** (deprecated — mã suy từ Loại nghỉ, không nhập tay).
- **Nghỉ nửa ngày:** field `custom_half_day_period` (Select Sáng/Chiều), **bắt buộc khi `half_day=1`**.
  Hook tách mã theo buổi lên Attendance ngày nửa: nghỉ **Sáng** → morning=mã, afternoon=X; nghỉ **Chiều**
  → morning=X, afternoon=mã. Payroll giữ Half Day + `half_day_status`="Present" (db_set thuần hiển thị)
  → **lương bất biến**.
- Test: **12 test xanh** qua harness. Deploy: cần `bench migrate` để 2 field mới (`custom_leave_reason`,
  `custom_half_day_period`) lên site + **restart** để hook mới live.
- **Bậc 3 PWA — ĐÃ build:** `frontend/src/views/leave/Form.vue` ẩn/hiện + `reqd` `custom_leave_reason`
  theo `leave_type=="Nghỉ phép năm"` và `custom_half_day_period` theo `half_day` (FormView không đọc
  `depends_on` như desk nên wire tay, mirror `half_day_date`); guard field-missing → **no-op trước
  migrate**. Desk form dùng `depends_on`/`mandatory_depends_on` native, không cần JS. PWA compile sạch.
  Deploy PWA = `yarn build` (ghi đè bundle live) đi kèm migrate + restart.

## Mấu chốt kỹ thuật: "một quỹ" nhưng "hiện riêng"

Đơn xin nghỉ chỉ có **một** `leave_type` để trừ số dư. Muốn Ô/Cô/P cùng rút quỹ "Nghỉ phép năm"
nhưng vẫn hiện **riêng** trên bảng công:

- Đơn xin nghỉ nhóm trừ-quỹ luôn đặt `leave_type = "Nghỉ phép năm"` → Frappe trừ đúng một quỹ + tự
  chặn khi hết. (Reverse-derive từ status+leave_type **không** phân biệt được Ô/Cô/P vì cùng
  leave_type — nên lý do phải mang **tường minh**, không suy ngược.)
- Thêm **custom field trên Leave Application**: `custom_attendance_code` (Link "Attendance Code",
  lọc theo các mã trừ-quỹ: P/Ô/Cô). Bắt buộc khi `leave_type = "Nghỉ phép năm"`.
- **Điểm hook đã xác minh:** `LeaveApplication.on_submit → update_attendance() →
  create_or_update_attendance()` (leave_application.py:101/250/283) tạo/cập nhật Attendance. Một
  hook `Leave Application` (doc_events) sau bước này **gắn `custom_attendance_code`** từ field trên
  đơn vào Attendance vừa tạo → cầu nối `before_validate` sẵn có tính `custom_cong`, và bảng công hiện
  Ô/Cô/P đúng. Bảng công phân nhóm theo **category của Attendance Code** (Ốm/Phép…), không theo
  leave_type → hiển thị + màu **không đổi**.

## Kiến trúc 3 bậc (làm tuần tự, mỗi bậc một checkpoint + gate lương)

### Bậc 1 (NỀN) — Cấp quỹ phép năm 12 + thâm niên
= **`spec/leave-entitlement-vn.md` (WS3), build nguyên trạng.** An toàn nhất, không đụng lương
(allocation không chạm status/leave_type/half_day). Không có bước này thì không gì để trừ.
**Hoà giải hiện trạng:** site đã có **7 Leave Allocation tạo tay** (5 phép + 2 ốm) + vài đơn đã nộp
(có thể do phiên khác) — helper `assign_annual_leave` phải **idempotent, không đạp lên** allocation
đang có; bước plan phải soi kỹ và quyết định gộp/giữ.

### Bậc 2 — Gộp quỹ + mã lý do + hook
- Field `custom_attendance_code` trên Leave Application (+ fixture custom_field, cập nhật bộ lọc
  fixtures ở hooks.py cho khớp — `test_setup_vn_defaults` enforce).
- Đơn nhóm trừ-quỹ đặt `leave_type = "Nghỉ phép năm"`; validate bắt buộc chọn mã P/Ô/Cô.
- Hook doc_events `Leave Application` gắn mã vào Attendance sau `update_attendance`.
- Cấu hình loại nghỉ: miễn trừ (TS/N/T) không chặn theo quỹ; K is_lwp. **Đổi `leave_type` của
  Attendance Code Ô/Cô → "Nghỉ phép năm"** (fixture, ask-first) để đường HR-đánh-mã-tay (nếu có) và
  reverse-derive cũng nhất quán với quỹ chung; `category` giữ nguyên (Ốm) nên bảng công/màu không đổi.
  Loại nghỉ "Nghỉ ốm"/"Nghỉ chăm con ốm" cũ thành không dùng cho số dư (giữ hay xoá = quyết ở plan).
- **Gate lương bất biến** trước/sau: Salary Slip payment_days/absent_days/LWP không đổi.

### Bậc 3 — PWA cho nhân viên chọn lý do
- Form xin nghỉ trong `frontend/` hiện field "Mã chấm công" khi loại = Nghỉ phép năm; build lại PWA
  (fork frontend tối thiểu như lần gỡ Attendance Request).

## Rủi ro & cổng

| Rủi ro | Mức | Xử lý |
|---|---|---|
| Đụng Leave Type + cầu nối lương trên PROD có lương thật | Cao | Mỗi bậc gate lương bất biến; không deploy khi chưa ký; làm tuần tự. |
| Phiên khác (hivx) đang sửa payroll/allocation song song | Cao | Trước mỗi bậc: đọc lại hiện trạng site; chỉ stage file mình đụng; idempotent. |
| Reverse-derive không phân biệt Ô/Cô/P (cùng leave_type) | TB | Mang mã tường minh qua field + hook, không suy ngược. |
| Đổi leave_type map của Ô/Cô = sửa fixture đang có | TB | Ask-first; giữ category để bảng công/màu không đổi. |
| Nhóm miễn trừ (TS 6 tháng…) vẫn cần allocation để nộp đơn | TB | Cấu hình loại nghỉ miễn trừ không phụ thuộc quỹ (max/allow theo chế độ). |

## Testing

- **Bậc 1:** entitlement 12 + floor(thâm niên/5); allocation cộng dồn; idempotent không đạp allocation cũ.
- **Bậc 2:** đơn Ốm/Chăm con/Phép cùng trừ "Nghỉ phép năm"; hết quỹ → chặn nộp; duyệt → Attendance
  ra đúng mã Ô/Cô/P; TS/N/T không trừ quỹ; K không trừ, is_lwp; **lương bất biến** (gate hiện có).
- **Bảng công:** hiển thị + màu + tổng nhóm **không đổi** (category-based).
- Chạy qua **harness rollback** (env python), KHÔNG `bench run-tests` trên miyano.

## Out of scope (đợt này)

- BHXH 75%/100%, chốt số ngày ốm theo luật riêng (đã gộp vào quỹ theo chính sách Miyano).
- Encashment phép chưa dùng khi thôi việc (Điều 113 k3).
- Carry-forward (giữ `is_carry_forward=0`, phép hết năm là hết).
- Đổi `payroll_based_on` hay logic Salary Slip.
