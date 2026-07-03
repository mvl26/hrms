# Plan: skip-recovery-on-Attendance-cancel

Derived from `SPEC.md`. One vertical slice; additive change to `Attendance.on_cancel`.

- [x] Task 0: Write SPEC.md + this plan. Commit as preparatory commit.
  - Files: SPEC.md, tasks/plan.md

- [x] Task 1: Reset skipped check-ins when a blocking Attendance is cancelled (TDD).
  - Acceptance:
    - New `test_reset_skip_auto_attendance_on_cancel` passes.
    - Existing `test_skip_auto_attendance_for_duplicate_record` and
      `test_skip_auto_attendance_for_overlapping_shift` still pass.
  - Verify:
    - RED: run new test before code change → fails.
    - GREEN: run new test after change → passes.
    - Regression: run the two existing skip tests → pass.
  - Files: `hrms/hr/doctype/attendance/attendance.py`,
    `hrms/hr/doctype/shift_type/test_shift_type.py`
  - Depends on: Task 0.
