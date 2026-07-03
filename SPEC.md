# Spec: Re-enable auto attendance for check-ins when a blocking Attendance is cancelled

## Objective

**Problem.** Users report that many Employee Checkins get `skip_auto_attendance = 1`
even though nobody ticked the box. Investigation (see
`hrms/skip_attendance_diag.py` and memory `project-skip-auto-attendance-diagnosis`)
showed this is **intentional** stock behaviour: during `ShiftType.process_auto_attendance()`,
if creating the `Attendance` raises a `frappe.ValidationError` — most commonly
`DuplicateAttendanceError` (an Attendance already exists for that employee+date) or
`OverlappingShiftAttendanceError` — the job rolls back, sets `skip_auto_attendance = 1`
on the whole shift-group of check-ins, and writes a Comment with the reason
(`employee_checkin.py -> handle_attendance_exception`).

**The gap.** That skip is **permanent**. If the user later cancels the Attendance that
was blocking those check-ins (e.g. it was a wrong manual record, or a leave that got
withdrawn), the check-ins stay `skip_auto_attendance = 1` forever and are never
reprocessed — the user must hunt them down and untick each one by hand.

**This change.** When an Attendance is **cancelled**, automatically reset
`skip_auto_attendance = 0` on the check-ins that were auto-skipped and are still unlinked
for the **same employee + attendance date**, so the next `process_auto_attendance` run
(hourly, or manual) reprocesses them.

**Success looks like:** cancelling the blocking Attendance is enough to get the
check-ins reprocessed on the next run — no manual unticking.

## Scope & non-goals

- **In scope:** additive recovery on `Attendance.on_cancel`. The *decision* to skip is
  left exactly as upstream ships it.
- **Explicitly NOT changing** `handle_attendance_exception` / the skip-setting logic, so
  the existing upstream tests that assert `skip_auto_attendance == 1`
  (`test_skip_auto_attendance_for_duplicate_record`,
  `test_skip_auto_attendance_for_overlapping_shift`) keep passing. No fork of core skip
  behaviour, no upstream-merge conflicts.
- **Out of scope (future):** resetting on delete of a *draft* Attendance
  (`after_delete`); a Shift Type toggle; auto-triggering processing immediately on cancel
  (we rely on the existing scheduled/manual run).

## Tech Stack

Frappe/ERPNext HRMS (v15), Python. DoctypeControllers + `frappe.qb`. Existing test
framework: Frappe's `unittest`-based runner.

## Commands

```
Run the new test:      bench --site miyano run-tests --module "hrms.hr.doctype.shift_type.test_shift_type" --test test_reset_skip_auto_attendance_on_cancel
Run regression tests:  bench --site miyano run-tests --module "hrms.hr.doctype.shift_type.test_shift_type" --test test_skip_auto_attendance_for_duplicate_record
                       bench --site miyano run-tests --module "hrms.hr.doctype.shift_type.test_shift_type" --test test_skip_auto_attendance_for_overlapping_shift
```

## Design

In `hrms/hr/doctype/attendance/attendance.py`:

```python
def on_cancel(self):
    self.unlink_attendance_from_checkins()
    self.reset_skipped_checkins()

def reset_skipped_checkins(self):
    """Re-enable auto attendance for check-ins that were auto-skipped (and are still
    unlinked) for this employee & date, so the next process_auto_attendance run can
    reprocess them — this Attendance may have been the record that blocked them."""
    EmployeeCheckin = frappe.qb.DocType("Employee Checkin")
    (
        frappe.qb.update(EmployeeCheckin)
        .set(EmployeeCheckin.skip_auto_attendance, 0)
        .where(
            (EmployeeCheckin.employee == self.employee)
            & (EmployeeCheckin.skip_auto_attendance == 1)
            & (EmployeeCheckin.attendance.isnull() | (EmployeeCheckin.attendance == ""))
            & (Date(EmployeeCheckin.shift_start) == self.attendance_date)
        )
    ).run()
```

Matching key = `employee` + `DATE(shift_start) == attendance_date`, restricted to
skipped + unlinked check-ins. `shift_start` (not the raw `time`) is used because that is
the shift date the auto-attendance grouping keys on, which is what `attendance_date`
represents (correct for night shifts crossing midnight). Skipped check-ins always have
`shift_start` set (they passed `fetch_shift` before being grouped).

## Testing Strategy

TDD. New test `test_reset_skip_auto_attendance_on_cancel` in
`hrms/hr/doctype/shift_type/test_shift_type.py`, mirroring
`test_skip_auto_attendance_for_duplicate_record`:

1. Pre-create an Attendance (Present) for employee+date.
2. Create check-ins + shift assignment; run `process_auto_attendance()`.
3. Assert check-ins are skipped (`skip_auto_attendance == 1`) — existing behaviour.
4. **Cancel** the pre-created Attendance.
5. Assert the check-ins are now `skip_auto_attendance == 0` (the new behaviour).

RED before the code change, GREEN after. Regression: the two existing skip tests must
still pass.

## Boundaries

- **Always:** run the new test + the two existing skip tests before committing; stage only
  the files this change touches (never `git add -A`) so pre-existing uncommitted work is
  not absorbed.
- **Ask first:** any change to `handle_attendance_exception` or the skip-setting logic;
  adding a Shift Type field; anything that alters upstream-tested behaviour.
- **Never:** delete/relax the existing skip tests to make things pass; touch the
  unrelated dirty files in the working tree (frontend/*, expense_claim.json,
  expense_invoice/).

## Success Criteria

- [ ] `test_reset_skip_auto_attendance_on_cancel` passes.
- [ ] `test_skip_auto_attendance_for_duplicate_record` still passes.
- [ ] `test_skip_auto_attendance_for_overlapping_shift` still passes.
- [ ] Change is confined to `attendance.py` (+ the new test) and is reversible via
      `git revert`.
