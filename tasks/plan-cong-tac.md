# Plan: Công Tác (business trip) workflow (Phase 5b)

Derived from `spec/business-trip-workflow.md`. Branch: `feat/skip-attendance-diag`.
Additive Desk feature — never touches payroll/attendance. Tests via rollback harness.

**⚠ Gated:** Tasks 1–2 are unblocked (additive doctypes). Task 3+ need answers to the spec's
open questions — esp. **Q1 role names (COO/HCNSPC)** = an auth/permission decision → STOP for sign-off.
Task 5 adds a custom field to core **Expense Claim** = ask-first.

- [x] Task 1: `Cong Tac Traveler` child DocType (employee, is_registrant, estimated_cost,
      expense_claim, notes). Files: `hrms/hr/doctype/cong_tac_traveler/*`.
- [ ] Task 2: `Cong Tac` parent DocType (fields + validate: dates, ≥1 traveler, approver required
      before leaving Nháp). Files: `hrms/hr/doctype/cong_tac/*`. Depends: Task 1.
- [ ] 🔒 Task 3: Workflow "Cong Tac Approval" + Roles COO/HCNSPC + tests. **SIGN-OFF (auth): needs
      Q1 answer (create COO/HCNSPC vs map existing).** Depends: Task 2.
- [ ] 🔒 Task 4: Notifications + ToDo assignment on state changes + tests. Depends: Task 3.
- [ ] 🔒 Task 5: Expense Claim custom field `custom_business_trip` (fixture, ASK-FIRST) + "Tạo đề nghị
      thanh toán" button/method + tests. Depends: Task 2.
- [ ] Task 6: Print formats QĐ cử đi công tác + giấy đi đường + render tests. Depends: Task 2.
- [ ] Task 7: Permissions/fixtures + migrate miyano + E2E verify + docs. Depends: all.
