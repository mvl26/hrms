# Plan: Geofence map improvement + default post-install setup

Spec: `spec/geofence-map-and-default-setup.md` (Phase 1 approved, decisions locked 2026-07-09).
Branch: `feat/skip-attendance-diag`. All additive + `git revert`-able. Test via the rollback harness
(NEVER `bench run-tests` on `miyano`).

## Dependency graph / order

```
T1 (server: circle + get_checkin_geofence + tests)  ─┐
                                                      ├─→ T2 (Shift Location JS)  ─┐
                                                      └─→ T3 (Employee Checkin JS) ─┤
T4 (setup_vn_defaults.ensure_defaults + tests) ───────────────────────────────────┼─→ T5 (wire hooks + migrate + E2E + commit)
```

T1 is the foundation for T2/T3 (they consume the circle rendering + `get_checkin_geofence`). T4 is
independent of Part A. T5 wires everything and verifies end-to-end. T1 and T4 can be built in parallel;
T2/T3 depend on T1; T5 depends on all.

## Tasks

### T1 — Server: circle-feature geolocation + `get_checkin_geofence`
- **Files:** `hrms/hr/utils.py`, `hrms/hr/doctype/employee_checkin/employee_checkin.py`,
  `hrms/hr/doctype/employee_checkin/test_employee_checkin.py` (add cases).
- **Do:**
  - In `set_geolocation_from_coordinates(doc)`: if `getattr(doc, "checkin_radius", 0)` is a positive
    number, set the feature's `properties` to `{"point_type": "circle", "radius": doc.checkin_radius}`
    (geometry stays the Point at [long, lat]); otherwise keep the bare Point. No behavior change for
    Employee Checkin (no `checkin_radius`).
  - Add `@frappe.whitelist()` `get_checkin_geofence(employee)` → find the employee's active
    submitted Shift Assignment with a `shift_location`, return that location's
    `{location_name, latitude, longitude, checkin_radius}` or `None` when tracking off / no location /
    `checkin_radius <= 0`. Reuse the same filter shape as `validate_distance_from_shift_location`.
- **Acceptance:** circle emitted iff `checkin_radius > 0`; `get_checkin_geofence` returns correct dict / None.
- **Verify:** harness unit tests (geojson shape assertions; helper returns).

### T2 — Shift Location JS: click-to-set + live circle
- **Files:** `hrms/hr/doctype/shift_location/shift_location.js`.
- **Do:** on `refresh` (when tracking on), bind the Geolocation control's `.map` `click` → set
  `latitude`/`longitude` from `e.latlng` → `frm.call("set_geolocation")` → re-render the field. Also
  regenerate on `checkin_radius`/`latitude`/`longitude` change. Defensive: poll briefly for
  `frm.get_field("geolocation").map` (created on field render); degrade gracefully if absent (Fetch
  Geolocation button + server circle still work).
- **Acceptance:** clicking the map moves the point + circle; changing radius resizes the circle.
- **Verify:** manual, Chrome (Desk). `bench build --app hrms` first.

### T3 — Employee Checkin JS: overlay geofence circle
- **Files:** `hrms/hr/doctype/employee_checkin/employee_checkin.js`.
- **Do:** on `refresh` (tracking on, saved doc with lat/long), call `get_checkin_geofence(employee)`;
  if it returns a location, overlay a read-only `L.circle([lat,long], {radius})` on the field's `.map`
  (not in `editableLayers`) so HR sees the check-in marker inside/outside the allowed area.
- **Acceptance:** overlay circle appears around the check-in when a geofence applies; nothing when none.
- **Verify:** manual, Chrome.

### T4 — `setup_vn_defaults.ensure_defaults` + tests
- **Files:** `hrms/setup_vn_defaults.py` (new), `hrms/tests/test_setup_vn_defaults.py` (new).
- **Do:**
  - `ensure_defaults()`: call `ensure_workflow()` (import from
    `hrms.patches.v15_0.setup_cong_tac_workflow`) to self-heal workflow + `COO` role; then an
    integrity check that the Attendance Codes, the 6 VN Leave Types, and the 5 Custom Fields exist,
    `frappe.log_error`/`frappe.logger().warning` if any are missing (do NOT recreate). Return a small
    summary dict for testability. No HR Settings writes, no sample data.
- **Acceptance:** run twice → workflow + COO role present, not duplicated, no exception; missing-data
  check reports correctly; no payroll/attendance rows created.
- **Verify:** harness unit tests (idempotency + presence + structural payroll-neutrality).

### T5 — Wire hooks + migrate + E2E + commit
- **Files:** `hrms/install.py`, `hrms/hooks.py`.
- **Do:** `after_install` → call `ensure_defaults()` after base `setup()`. `after_migrate` → convert the
  single string to a list `["hrms.setup.update_select_perm_after_install", "hrms.setup_vn_defaults.ensure_defaults"]`.
- **Acceptance:** `bench --site miyano migrate` runs clean; workflow + COO role + fixture data present.
- **Verify:** `bench --site miyano migrate`; `bench execute` a check of the defaults; manual browser
  verify of T2/T3 maps; then commit each task with the repo's `feat(hr): …` message style.

## Boundaries reminder
Ask-first / never: don't touch `validate_distance_from_shift_location` logic; don't enable
`allow_geolocation_tracking`; don't recreate fixture data; don't touch payroll. All changes additive.
