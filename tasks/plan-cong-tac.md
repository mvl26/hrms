# Plan: Công Tác (business trip) workflow (Phase 5b)

Derived from `spec/business-trip-workflow.md`. Branch: `feat/skip-attendance-diag`.
Additive Desk feature — never touches payroll/attendance. Tests via rollback harness.

**Open questions RESOLVED 2026-07-08:** COO = new Role, HCNSPC = HR Manager (existing); giấy đi đường
1 tờ/người; số QĐ nhập tay; `expense_approver` = `approver_coo`; **trip approval auto-generates "CT"
attendance** (Task 8, payroll-adjacent → invariance gate). Task 5 Expense-Claim custom field additive
fixture (user OK'd). Proceeding autonomously; Task 8 must pass the payroll-invariance gate.

- [x] Task 1: `Cong Tac Traveler` child DocType (employee, is_registrant, estimated_cost,
      expense_claim, notes). Files: `hrms/hr/doctype/cong_tac_traveler/*`.
- [x] Task 2: `Cong Tac` parent DocType (fields + validate: dates, ≥1 traveler, approver required
      before leaving Nháp). Files: `hrms/hr/doctype/cong_tac/*`. Depends: Task 1.
- [ ] Task 3: Role "COO" (new) + Workflow "Cong Tac Approval" (states/transitions/docstatus;
      COO duyệt, HR Manager ra QĐ) + tests. Depends: Task 2.
- [ ] Task 4: Notifications + ToDo assignment on state changes + tests. Depends: Task 3.
- [ ] Task 5: Expense Claim custom field `custom_business_trip` (fixture) + "Tạo đề nghị thanh toán"
      button/method (expense_approver = approver_coo) + tests. Depends: Task 2.
- [ ] Task 6: Print formats QĐ cử đi công tác + giấy đi đường (1 tờ/người) + render tests. Depends: Task 2.
- [ ] Task 8: Auto-generate "CT" attendance on trip approval (add CT code; create Attendance for travel
      days skipping holidays/existing) + **payroll-invariance gate**. Depends: Task 3.
- [ ] Task 7: Permissions/fixtures + migrate miyano + E2E verify + docs. Depends: all.
