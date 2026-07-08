# Spec: Quy trình công tác — "Công Tác" (Business Trip) DocType + duyệt + thanh toán

> Status: **DRAFT for approval (Phase 1 / SPECIFY).** Do not plan/implement until reviewed.
> Companion to the shipped attendance-code + Bảng Công Tháng features. Saved under `spec/`.

## Objective

Số hoá quy trình cử cán bộ đi công tác của bệnh viện: một chuyến công tác **nhiều người**, đăng ký
→ COO duyệt trong hệ thống → Hành chính–Nhân sự (HCNSPC) ra **QĐ cử đi công tác** + **giấy đi đường**
→ từng người làm **đề nghị thanh toán công tác phí** (Expense Claim) → COO duyệt chi → HCNSPC thanh toán.

**Users:** người đăng ký (một cán bộ đi công tác); COO (người duyệt); HCNSPC (ra QĐ, thanh toán).
**Success:** một chuyến = một chứng từ cho nhiều người; luồng duyệt COO→HCNSPC chạy trong hệ thống với
thông báo tự động; in được QĐ + giấy đi đường; mỗi người tách được công tác phí qua Expense Claim riêng.

## Scope & locked decisions (confirmed 2026-07-08)

- **New DocType `Cong Tac`** (Travel Request là 1-người → không dùng). ✅
- **Frappe Workflow** nhiều trạng thái điều khiển duyệt + docstatus. ✅
- **Mỗi người đi công tác = 1 Expense Claim riêng** link về chuyến (tách chi phí từng người). ✅
- **Geofence / check-in vị trí = spec RIÊNG** (Employee Checkin đã có latitude/longitude/geolocation;
  geofence chỉ còn validate vị trí so với địa điểm cho phép). Ngoài phạm vi tài liệu này. ✅

## Assumptions to confirm

- COO = 1 user cụ thể chọn ở field `approver_coo`; hành động "Duyệt" trên workflow do **Role "COO"**.
- HCNSPC = **Role** (ai có role đó nhận noti, ra QĐ, thanh toán). Người chi trả **cấu hình được**
  (mặc định HCNSPC; sau này chuyển sang Role "Accounts User" khi có Kế toán độc lập).
- Desk-only (DocType + Workflow + Notification + Print Format). Không đụng frontend Vue, không đụng payroll.

## Data model

### `Cong Tac` (Business Trip) — submittable, workflow-driven

| field | type | notes |
|---|---|---|
| `naming_series` | Select | `CT-.YYYY.-.#####` |
| `purpose` | Small Text / Link Purpose of Travel | Mục đích công tác |
| `destination` | Data | Nơi đến |
| `from_date` / `to_date` | Date | Thời gian công tác (reqd) |
| `company` / `department` | Link | |
| `registered_by` | Link Employee | Người đăng ký (mặc định = employee của user hiện tại) |
| `travelers` | Table → `Cong Tac Traveler` | **Danh sách người đi (nhiều người)** |
| `transport` | Data / Select | Phương tiện |
| `estimated_cost` | Currency | Dự trù kinh phí (tổng) |
| `approver_coo` | Link User | Người duyệt (COO) — nhận noti + ToDo |
| `decision_no` | Data | Số QĐ (HCNSPC điền khi ra QĐ) |
| `decision_date` | Date | Ngày QĐ |
| `workflow_state` | Select (read-only) | do Frappe Workflow quản lý |
| `remarks` | Small Text | |
| `amended_from` | Link Cong Tac | submittable |

### `Cong Tac Traveler` (istable)

| field | type | notes |
|---|---|---|
| `employee` | Link Employee | reqd |
| `employee_name` | Data | fetch |
| `is_registrant` | Check | người đăng ký |
| `estimated_cost` | Currency | dự trù/người (để đối chiếu khi tách chi phí) |
| `expense_claim` | Link Expense Claim | read-only — đề nghị thanh toán của người này (điền khi tạo) |
| `notes` | Data | |

## Workflow — "Cong Tac Approval" (Frappe Workflow doc, shipped standard)

| State | docstatus | Ai thấy/hành động |
|---|---|---|
| Nháp | 0 | Người đăng ký soạn, thêm người đi |
| Chờ COO duyệt | 0 | gửi duyệt → noti COO + HCNSPC |
| COO đã duyệt | 1 | COO bấm Duyệt (submit) → noti HCNSPC |
| Đã ra QĐ | 1 | HCNSPC điền số QĐ, in QĐ + giấy đi đường |
| Hoàn tất | 1 | kết thúc (sau khi thanh toán xong) |
| Từ chối | 0 | COO từ chối (kèm lý do) → về người đăng ký |

**Transitions (action → by Role):** Gửi duyệt (Nháp→Chờ COO duyệt, HR User/registrant) · Duyệt
(Chờ COO duyệt→COO đã duyệt, **COO**) · Từ chối (Chờ COO duyệt→Từ chối, **COO**) · Ra QĐ (COO đã
duyệt→Đã ra QĐ, **HCNSPC**) · Hoàn tất (Đã ra QĐ→Hoàn tất, **HCNSPC**). `approver_coo` phải khớp
user đang duyệt (validate) để đúng người COO được chỉ định.

## Notifications & assignment

Frappe **Notification** (system + email) + **ToDo assignment**:
- Vào "Chờ COO duyệt": notify `approver_coo` + Role HCNSPC; `assign` chứng từ cho `approver_coo`.
- Vào "COO đã duyệt": notify Role HCNSPC (để ra QĐ).
- Vào "Đã ra QĐ": notify `registered_by` + các travelers (để làm đề nghị thanh toán).

## Expense Claim integration (thanh toán công tác phí)

- **Custom field trên Expense Claim:** `custom_business_trip` (Link `Cong Tac`), export fixture
  (additive, giống các custom field attendance). Cho phép gắn claim vào chuyến + tổng hợp/tách chi phí.
- **Nút "Tạo đề nghị thanh toán"** trên `Cong Tac` (khi ≥ "Đã ra QĐ"): tạo một **Expense Claim** cho
  **user hiện tại** (nếu là traveler), prefill `employee`, `company`, `custom_business_trip = chuyến`,
  `expense_approver = approver_coo`; ghi ngược `traveler.expense_claim`. Mỗi người tự bấm cho mình →
  tách chi phí từng người tự nhiên.
- **Duyệt & chi:** dùng luồng sẵn có của Expense Claim (COO = `expense_approver` duyệt → HCNSPC ghi
  Payment/`is_paid`). Người chi cấu hình được (HCNSPC → Accounts sau này). **Không** làm lại luồng chi.

## Print formats (standard, Jinja)

- **QĐ cử đi công tác** — trên `Cong Tac`: căn cứ, danh sách người đi (bảng travelers), thời gian, nơi
  đến, mục đích, số/ngày QĐ, nơi ký (Giám đốc/HCNSPC).
- **Giấy đi đường** — trên `Cong Tac`, **một tờ / người đi** (lặp travelers hoặc in theo từng traveler):
  họ tên, nơi đến, thời gian, phương tiện, ô xác nhận nơi đến.

## Roles needed

Tạo (nếu chưa có) Role **"COO"** và **"HCNSPC"**; gán vào workflow transitions + Notification. Quyền
DocType `Cong Tac`: HR User (tạo/sửa nháp), COO (đọc/duyệt), HCNSPC (đọc/ra QĐ/hoàn tất), System Manager.

## Commands

```
Migrate (nạp doctype/workflow/print/fixtures): bench --site miyano migrate
Reload 1 doctype khi dev: frappe.reload_doc("hr","doctype","cong_tac")
Test (an toàn, KHÔNG bench run-tests trên miyano): rollback harness trong console
```

## Project structure (files to create)

```
hrms/hr/doctype/cong_tac/               cong_tac.json/.py/.js/__init__.py/test_cong_tac.py
hrms/hr/doctype/cong_tac_traveler/      cong_tac_traveler.json/.py/__init__.py
hrms/hr/workflow/cong_tac_approval/     cong_tac_approval.json      (Workflow, standard)
hrms/hr/print_format/{qd_cu_di_cong_tac,giay_di_duong}/  *.json
hrms/fixtures/custom_field.json         (+ Expense Claim-custom_business_trip)
hrms/fixtures/{role,workflow_state,workflow_action_master}.json  (COO/HCNSPC + states/actions nếu cần)
```

## Code style

Theo convention đã dùng: thư mục doctype ASCII (`cong_tac`), label VN trong JSON; tab indent; controller
có docstring nêu "why"; tái dùng cơ chế Frappe (Workflow/Notification/Expense Claim) thay vì tự code.

## Testing strategy (rollback harness — NEVER `bench run-tests` trên miyano)

- Tạo `Cong Tac` nhiều travelers → workflow_state chạy đúng qua các transition (mô phỏng
  `apply_workflow`); role bị chặn nếu sai (COO-only mới Duyệt được).
- Nút "Tạo đề nghị thanh toán" tạo Expense Claim với `custom_business_trip` + `expense_approver` đúng,
  ghi ngược `traveler.expense_claim`; **không** tạo claim trùng cho cùng người.
- Print QĐ + giấy đi đường render không lỗi, chứa danh sách người đi.
- **Không đụng payroll/attendance:** tạo/duyệt chuyến không sinh/sửa Attendance hay Salary Slip.

## Boundaries

- **Always:** tái dùng Workflow/Notification/Expense Claim; fixtures additive; label VN + folder ASCII;
  test qua rollback harness.
- **Ask first:** thêm custom field vào **Expense Claim** (core doctype, fixture → mọi site); tạo Role mới;
  mọi deploy fixtures/workflow lên **production**.
- **Never:** đụng payroll/attendance/status gốc; tự viết lại luồng duyệt-chi của Expense Claim; commit secrets.

## Success criteria (specific, testable)

- [ ] `Cong Tac` + `Cong Tac Traveler` cài được; thêm được nhiều người vào 1 chuyến.
- [ ] Workflow: Nháp→Chờ COO duyệt→COO đã duyệt→Đã ra QĐ→Hoàn tất (+ Từ chối) đúng docstatus; chỉ Role
      COO Duyệt/Từ chối được, chỉ HCNSPC Ra QĐ/Hoàn tất được (test-proven).
- [ ] Vào "Chờ COO duyệt" → có Notification + ToDo cho `approver_coo`; vào các bước sau → noti đúng nhóm.
- [ ] Nút tạo Expense Claim cho từng traveler với `custom_business_trip` + `expense_approver=COO`; tách
      chi phí từng người truy được qua `custom_business_trip`.
- [ ] In được QĐ cử đi công tác + giấy đi đường (có danh sách/tên người đi).
- [ ] Tạo/duyệt chuyến KHÔNG sinh/sửa Attendance hay Salary Slip (payroll-neutral).
- [ ] Reversible qua `git revert`; verify trên dev `miyano`.

## Open questions (need human input before Plan)

1. **Role names:** dùng đúng "COO"/"HCNSPC" hay map vào role sẵn có (vd HR Manager)? Có sẵn user COO chưa?
2. **Giấy đi đường:** một tờ/người (in lặp) hay một tờ chung cả đoàn? Mẫu cụ thể (các ô xác nhận nơi đến)?
3. **QĐ số:** HCNSPC tự nhập số QĐ, hay sinh tự động theo series riêng?
4. **Ngày công khi đi công tác:** chuyến công tác có tự sinh mã công (vd "CT") trên bảng chấm công cho
   những ngày đi không, hay tách rời hoàn toàn khỏi chấm công? (Ảnh hưởng liên kết ngược về feature chấm công.)
5. **Expense payment approver:** COO duyệt chi có luôn = `approver_coo` của chuyến, hay approver Expense
   Claim theo cấu hình sẵn có của HRMS?

## Task breakdown (for /build auto — after approval)

1. `Cong Tac Traveler` child DocType.
2. `Cong Tac` parent DocType (fields + validate: dates, ≥1 traveler, approver required to submit).
3. Workflow "Cong Tac Approval" + Roles COO/HCNSPC (states/transitions/docstatus) + tests.
4. Notifications + ToDo assignment on state changes + tests.
5. Expense Claim custom field `custom_business_trip` (fixture) + "Tạo đề nghị thanh toán" button/method + tests.
6. Print formats: QĐ cử đi công tác + giấy đi đường + render tests.
7. Permissions/fixtures + migrate `miyano` + end-to-end verify + docs.
