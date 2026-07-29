# Spec: Geofence check-in map improvement + default post-install setup

> Status: **APPROVED (Phase 1 / SPECIFY complete).** 4 open questions resolved by the user on
> 2026-07-09 (see *Decisions*). Two independent features in one doc; Part A and Part B are built and
> tested together on `feat/skip-attendance-diag`. Plan/tasks live in `tasks/plan-geofence-and-defaults.md`.

## Objective

Two things that make the HRMS deployment production-ready:

**A. Geofence check-in — visual map + radius circle.** HRMS already enforces a circular geofence
(`Shift Location.checkin_radius` + `Employee Checkin.validate_distance_from_shift_location`, gated by
`HR Settings.allow_geolocation_tracking`, using the Leaflet/OpenStreetMap `Geolocation` field). The
gap is **visibility**: admins can't *see* the geofence area, and check-ins don't show where they
happened relative to it. Make the allowed area + the check-in point visible, and let the admin pick a
location by clicking the map.

**B. Default setup on install.** Everything this fork adds (VN attendance codes, leave types, CT/V
codes, Công Tác workflow + COO role, custom fields) must be present and self-heal on a fresh
`bench install-app hrms` and on every `bench migrate` — no manual steps, no dependence on one-time
patch-log state.

**Users:** HR/admin configuring geofences and sites; employees checking in; whoever installs the app.

## Decisions (locked 2026-07-09 — resolves the 4 open questions)

1. **Part A scope = visual radius circle + click-to-set + check-in overlay.** No address search /
   Nominatim reverse-geocode, no multi-location, no warn-instead-of-block. Reuse Frappe's bundled
   Leaflet/OSM — **no new map/geocoding libraries.** Existing radius enforcement kept as-is.
2. **`allow_geolocation_tracking` stays OFF by default.** Ship it off; the admin enables it after
   configuring Shift Locations. Rationale: enabling it forces GPS on *every* check-in and would block
   check-ins / biometric-device syncs that send no coordinates. → **Part B does NOT mutate HR Settings
   at all** (removes the fresh-install guard the draft proposed).
3. **Do NOT seed a sample Holiday List, and (for consistency) no sample Shift Location.** Admin creates
   real master data. Part B is limited to the code/workflow master data this fork owns.
4. **Master-data ensure runs on every `bench migrate` (idempotent), plus on install.** Wired via the
   `after_migrate` hook list + `after_install`.

> Consequence of #2: on a fresh site the Shift Location map fields are hidden until the admin turns on
> `allow_geolocation_tracking` (existing `shift_location.js` behavior, kept). That is the intended first
> step; Part A makes the map useful *once tracking is on*.

## Part A — geofence map + radius circle

Data model unchanged (reuse `Shift Location` + `Employee Checkin` geolocation). Key implementation
insight: **Frappe's `ControlGeolocation` already renders circles.** Its `point_to_layer` turns a GeoJSON
feature whose `properties.point_type == "circle"` (with a `radius`) into `L.circle(latlng, {radius})`,
and it exposes the live `.map` (Leaflet map) + `.editableLayers` on the field control. So:

- **Server (`hrms/hr/utils.py::set_geolocation_from_coordinates`)** — when the doc has a positive
  `checkin_radius` (i.e. a Shift Location), emit the point feature as a **circle** feature
  (`point_type: "circle"`, `radius: checkin_radius`) so the existing control draws the geofence area
  natively; keep a plain **Point** for Employee Checkin (the check-in marker). Robust, no client redraw.
- **Server helper `get_checkin_geofence(employee)`** in `employee_checkin.py` → whitelisted, read-only,
  returns `{location_name, latitude, longitude, checkin_radius}` for the employee's active
  shift-assignment Shift Location, or `None` (no location / radius ≤ 0). Unit-testable.
- **Shift Location client JS (`shift_location.js`)** — click the map to set `latitude`/`longitude`
  (then regenerate the circle via the existing `set_geolocation` call + refresh the field); regenerate
  when `checkin_radius`/`latitude`/`longitude` change so the admin sees the exact area update.
- **Employee Checkin client JS (`employee_checkin.js`)** — after render, fetch `get_checkin_geofence`
  and overlay a read-only `L.circle` on the map so HR sees in/out-of-area at a glance around the
  check-in point.
- Uses the Leaflet already bundled by Frappe's Geolocation control; OSM tiles load from the browser.

## Part B — default post-install setup

A single idempotent entry point `hrms/setup_vn_defaults.py::ensure_defaults()`:

1. **Workflow + role (the real new value — self-healing, every migrate):** ensure the Công Tác approval
   workflow + `COO` role + its Workflow States/Actions by delegating to the existing
   `hrms.patches.v15_0.setup_cong_tac_workflow.ensure_workflow()` (already idempotent). Previously this
   only ran once via the patch log; now it re-ensures on every migrate, so a deleted workflow/role is
   restored.
2. **Integrity check on fixture-backed data (no duplication):** the VN Attendance Codes, the 6 VN Leave
   Types, and the 5 Custom Fields are already synced on every migrate/install by the existing
   `fixtures` mechanism (`hooks.py`). `ensure_defaults` asserts they are present and logs a warning if
   any are missing (a fixture-sync problem) — it does **not** recreate them (avoids partial/dup rows).
3. **No HR Settings writes. No sample Shift Location. No sample Holiday List.** (Decisions #2, #3.)

**Wiring:** call `ensure_defaults()` from `hrms/install.py::after_install` (after base setup); convert the
`after_migrate` hook to a list and append `hrms.setup_vn_defaults.ensure_defaults`.

## Commands

```
Fresh install (exercises after_install):  bench --site <s> install-app hrms
Migrate (exercises after_migrate + fixtures + patches):  bench --site miyano migrate
Test (rollback harness — NEVER `bench run-tests` on miyano): console harness
  (bench --site miyano console; flags.in_test=True; monkeypatch frappe.db.commit→noop;
   per-test savepoint via a TextTestResult subclass; frappe.db.rollback() in finally)
Build JS assets after editing .js:  bench build --app hrms   (or the desk dev asset build)
```

## Project structure (files)

```
hrms/hr/utils.py                                         (edit — emit circle feature when checkin_radius>0)
hrms/hr/doctype/employee_checkin/employee_checkin.py     (add get_checkin_geofence + unit tests)
hrms/hr/doctype/shift_location/shift_location.js         (edit — click-to-set + regenerate circle)
hrms/hr/doctype/employee_checkin/employee_checkin.js     (edit — overlay geofence circle)
hrms/setup_vn_defaults.py                                (new — ensure_defaults + tests)
hrms/install.py                                          (call ensure_defaults in after_install)
hrms/hooks.py                                            (after_migrate → list += ensure_defaults)
```

## Code style

Match the shipped features: ASCII module names, VN labels/strings; tab indent; idempotent guards
(`frappe.db.exists` before create); reuse Frappe controls (Geolocation/Leaflet) — no new map libs;
server helpers small, whitelisted, and read-only where possible.

## Testing strategy (rollback harness — NEVER `bench run-tests` on `miyano`)

- **A (server):** unit-test `set_geolocation_from_coordinates` → circle feature when `checkin_radius>0`,
  plain Point otherwise / when tracking off. Unit-test `get_checkin_geofence` → correct Shift Location
  circle for an employee with an active shift assignment; `None` when no location / radius ≤ 0 / tracking
  off. Map/circle *rendering* is client-side → verified manually in Desk (Chrome), not unit-tested.
- **B:** unit-test `ensure_defaults` idempotency — run twice on a temp (rolled-back) state and assert:
  Công Tác workflow + `COO` role present and **not duplicated**, never raises, and the fixture-backed
  master data present-check behaves. Assert `ensure_defaults` touches **no** payroll/attendance
  transactional data (structural: it imports/creates only Workflow/Role/Workflow State/Action).

## Boundaries

- **Always:** idempotent setup; reuse existing geofence + Geolocation field; VN labels; test via harness;
  additive + `git revert`-able.
- **Ask first:** any change to `Employee Checkin.validate_distance_from_shift_location`; enabling
  `allow_geolocation_tracking` by default (decided: NO); adding any dependency.
- **Never:** hard-block behavior changes without a flag; commit secrets/API keys; add a paid or external
  geocoding provider; force-override admin HR Settings; recreate fixture data (risk of dup rows); touch
  payroll/attendance transactional data.

## Success criteria (specific, testable)

- [ ] Shift Location form shows a live radius **circle** on the map (once tracking is on); clicking the
      map sets `latitude`/`longitude` and the circle re-centers (manual verify in Chrome).
- [ ] Employee Checkin form shows the check-in point + the applicable geofence circle overlay (manual verify).
- [ ] `set_geolocation_from_coordinates` emits a circle feature iff `checkin_radius > 0` (unit test).
- [ ] `get_checkin_geofence(employee)` returns the correct circle / `None` (unit test).
- [ ] `ensure_defaults()` yields: Công Tác workflow + `COO` role present; fixture-backed VN codes/leave
      types/custom fields present — verified on a temp state; is idempotent (run twice → no dup, no error)
      and payroll-neutral (unit test).
- [ ] `after_install` + `after_migrate` wired; `bench --site miyano migrate` clean; defaults present E2E.
- [ ] Reversible via `git revert`; verified on dev `miyano`.

## Task breakdown (see `tasks/plan-geofence-and-defaults.md` for detail)

1. Server: circle-feature geolocation + `get_checkin_geofence` helper + unit tests.
2. Shift Location `.js`: click-to-set lat/long + regenerate circle on field change (manual verify).
3. Employee Checkin `.js`: overlay geofence circle on the check-in point (manual verify).
4. `hrms/setup_vn_defaults.py::ensure_defaults` (workflow/role + integrity check) + idempotency/neutrality tests.
5. Wire `after_install` + `after_migrate`; `bench migrate miyano`; E2E + browser verify; docs/commit.
