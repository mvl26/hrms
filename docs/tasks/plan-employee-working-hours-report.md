# Employee Working Hours Report — Implementation Plan

> Spec: `docs/spec/employee-working-hours-report.md`. Nhánh `feat/skip-attendance-diag`.
> Test qua **rollback harness** (KHÔNG `bench --site miyano run-tests`).
>
> **STATUS 2026-07-31 — XONG.** 17 test xanh; tổng giờ 7/2026 = 829,8h khớp 100% với number
> card `get_total_working_hours_card`. Report + link workspace đã nạp lên site miyano (chưa
> `bench migrate` — nạp riêng lẻ để không kéo theo các thay đổi khác đang chờ deploy).
>
> **SỬA 2026-07-31 (HR báo TB sai):** giờ của report từng lấy `Attendance.working_hours` — con số
> đã bị `classify_day` cap ở khung ca, tức GIỜ QUY CÔNG, nên TB thành công tháng chứ không phải
> giờ ở văn phòng (99/131 ngày lệch). Nay tính lại giờ CÓ MẶT từ giờ vào/ra, thêm cột đối chiếu
> "Giờ tính công", và bỏ ngày không có punch khỏi mẫu số. 22 test xanh; TB khớp công cụ JS của HR
> tới 0,01h.

**Goal:** Script Report `Employee Working Hours` cho HR xem giờ vào / giờ ra / tổng giờ / TB giờ
mỗi ngày của toàn bộ nhân viên Active, hai chế độ Summary và Detail.

**Architecture:** Report chỉ đọc Attendance (`docstatus = 1`), tính giờ net bằng
`hrms.hr.working_hours.compute_net_hours` có sẵn (không viết công thức mới), gom nhóm trong
`employee_working_hours.py`. Không ghi DB → payroll-neutral.

**Tech Stack:** Frappe v15 Script Report (`execute(filters)` → columns, data, None, None,
report_summary), `frappe.qb`, `frappe.get_all`.

## Global Constraints

- Chỉ đọc: không ghi/insert/update bất kỳ doctype nào.
- Tên report + fieldname tiếng Anh; label tiếng Việt qua `hrms/translations/vi.csv`.
- Định dạng: tab, nháy kép, dòng ≤ 110 ký tự, ruff (pre-commit).
- Additive + `git revert`-able; không sửa file upstream nào ngoài `vi.csv`.
- Không hard-code danh sách nhân viên loại trừ.

---

### Task 1: Lõi tính giờ theo ngày + gom nhóm theo nhân viên

**Files:**
- Create: `hrms/hr/report/employee_working_hours/__init__.py`
- Create: `hrms/hr/report/employee_working_hours/employee_working_hours.py`
- Test: `hrms/hr/report/employee_working_hours/test_employee_working_hours.py`

**Interfaces:**
- Consumes: `hrms.hr.working_hours.compute_net_hours(status, in_time, out_time, working_hours, is_split=False)`
- Produces:
  - `prepare_filters(filters) -> frappe._dict` (mặc định from/to = tháng hiện tại, `view="Summary"`)
  - `get_daily_rows(filters) -> list[dict]` — mỗi Attendance một dict:
    `{employee, employee_name, department, attendance_date, day_of_week, shift, status, in_time, out_time, hours}`
  - `get_summary_rows(filters) -> list[dict]` — mỗi nhân viên một dict:
    `{employee, employee_name, department, days_counted, total_hours, avg_hours, avg_in_time, avg_out_time}`

- [x] **Step 1: Viết test đỏ** — Present 8h, Half Day không trừ trưa, Absent 0h và không vào mẫu số,
      ca split không trừ hai lần, NV Active 0 giờ vẫn có dòng, TB = tổng ÷ ngày có giờ > 0,
      lọc ngày/phòng ban/nhân viên/ca, `docstatus != 1` bị loại.
- [x] **Step 2: Chạy harness → FAIL (ModuleNotFoundError)**
- [x] **Step 3: Cài đặt tối thiểu** `prepare_filters` / `get_daily_rows` / `get_summary_rows`.
- [x] **Step 4: Chạy harness → PASS**
- [x] **Step 5: Commit** `git add hrms/hr/report/employee_working_hours spec tasks`

### Task 2: Report chuẩn (JSON + JS filter + execute)

**Files:**
- Create: `hrms/hr/report/employee_working_hours/employee_working_hours.json`
- Create: `hrms/hr/report/employee_working_hours/employee_working_hours.js`
- Modify: `hrms/hr/report/employee_working_hours/employee_working_hours.py` (thêm `execute`, cột,
  report summary)
- Test: cùng file test trên

**Interfaces:**
- Produces: `execute(filters) -> (columns, data, None, None, report_summary)`;
  `get_summary_columns()`, `get_detail_columns()`.

- [x] **Step 1: Test đỏ** — `execute` với `view="Summary"` trả cột `total_hours`/`avg_hours`;
      `view="Detail"` trả `in_time` dạng `HH:MM`; report summary có 3 thẻ.
- [x] **Step 2: Chạy harness → FAIL**
- [x] **Step 3: Cài đặt** `execute` + cột + JSON (`report_type: Script Report`,
      `ref_doctype: Attendance`, roles HR User / HR Manager / System Manager) + JS filters.
- [x] **Step 4: Chạy harness → PASS**
- [x] **Step 5: Commit**

### Task 3: Nhãn tiếng Việt

**Files:**
- Modify: `hrms/translations/vi.csv`
- Test: `hrms/tests/test_vn_translations.py` (đã có: cấm trùng key, cấm dòng sai định dạng)

- [x] **Step 1: Thêm dòng** `Employee Working Hours,Giờ làm việc nhân viên` + nhãn cột/filter còn
      thiếu; kiểm tra không trùng source string đã có.
- [x] **Step 2: Chạy `hrms.tests.test_vn_translations` → PASS**
- [x] **Step 3: Commit**

### Task 4: Verify trên dữ liệu thật + đối chiếu dashboard

- [x] **Step 1:** `bench --site miyano migrate` để nạp report mới (report chuẩn đọc từ file, nhưng
      migrate tạo bản ghi Report).
- [x] **Step 2:** Chạy `execute` trên dữ liệu tháng 7/2026 thật, đối chiếu **Tổng giờ** với
      `get_total_working_hours_card` (cùng công thức → phải khớp).
- [x] **Step 3:** `pre-commit run --all-files` (ruff) và chạy lại toàn bộ test của report.
- [x] **Step 4:** Commit cuối + hướng dẫn user review trên desk.
