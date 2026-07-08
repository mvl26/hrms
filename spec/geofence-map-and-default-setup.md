# Spec: Geofence check-in map improvement + default post-install setup

> Status: **DRAFT for approval (Phase 1 / SPECIFY).** Two independent features in one doc; each can
> be planned/built as its own `/build auto` run. Saved under `spec/`. Do not implement until reviewed.

## Objective

Two things that make the HRMS deployment production-ready:

**A. Geofence check-in — visual map + radius circle.** HRMS already enforces a circular geofence
(`Shift Location.checkin_radius` + `Employee Checkin.validate_distance_from_shift_location`, gated by
`HR Settings.allow_geolocation_tracking`, using the Leaflet/OpenStreetMap `Geolocation` field). The
gap is **visibility**: admins can't *see* the geofence area, and check-ins don't show where they
happened relative to it. Improve the map UX so the allowed area + the check-in point are visible.

**B. Default setup on install.** Everything this fork adds (VN attendance codes, leave types, CT/V
codes, Công Tác workflow + COO role, custom fields, plus sensible HR Settings and starter master
data) should be present and correct on a fresh `bench install-app hrms` — no manual steps.

**Users:** HR/admin configuring geofences and sites; employees checking in; whoever installs the app.

## Scope & locked decisions (confirmed 2026-07-08)

- **A. Geofence:** ONLY the **visual map + radius circle** improvement (map shows check-in point + the
  geofence circle; pick location by clicking the map). NOT multi-location, NOT reverse-geocode,
  NOT warn-instead-of-block. Existing radius enforcement is kept as-is.
- **Internet available** → use OpenStreetMap tiles (Frappe's Geolocation field already does) + Nominatim
  if ever needed. No offline/self-hosted tiles.
- **B. Default setup (all four):** ensure VN codes + leave types + CT/V; ensure Công Tác workflow + COO
  role + custom fields; default-enable `allow_geolocation_tracking` + `allow_employee_checkin_from_mobile_app`;
  seed one sample Shift Location + one sample VN Holiday List.
- Desk + mobile check-in. GPS captured client-side (browser Geolocation API) — unchanged.

## Assumptions to confirm

- We MAY edit `hrms/install.py::after_install` and add to the `after_migrate` hook list (this fork owns them).
- Settings defaults (`allow_geolocation_tracking`, mobile checkin) are set **only on fresh install**, never
  re-forced on later migrates (so an admin who turns them off stays off). Idempotent data (codes/workflow/
  role/samples) may be ensured on every migrate.
- Sample Shift Location + Holiday List are **starters** (admin edits real coordinates/holidays); created
  only if none already exist.

## Part A — geofence map + radius circle

Data model unchanged (reuse `Shift Location` + `Employee Checkin` geolocation). Add:

- **Server helper** `hrms.hr.doctype.employee_checkin.employee_checkin.get_checkin_geofence(employee)`
  → `{location_name, latitude, longitude, checkin_radius}` for the employee's current shift-assignment
  Shift Location (or None). Whitelisted, read-only — unit-testable.
- **Shift Location client JS** (`shift_location.js`): on the `geolocation` Leaflet map, draw a **circle of
  `checkin_radius`** around (latitude, longitude); update live when radius/lat/long change; clicking the
  map (or the existing *Fetch Geolocation* button) sets lat/long + recenters. Admin sees the exact area.
- **Employee Checkin client JS** (`employee_checkin.js`): render the check-in point and overlay the
  applicable geofence circle (via `get_checkin_geofence`) so HR sees in/out-of-area at a glance.
- Uses Leaflet already bundled by Frappe's Geolocation control; OSM tiles load from the browser.

## Part B — default post-install setup

A single idempotent entry point `hrms.setup_vn_defaults.ensure_defaults()`:

1. **Master data (idempotent, safe every migrate):** ensure the VN Attendance Codes (X…CT/V) and 7 VN
   Leave Types exist (fixtures already sync on migrate — this is a safety net / no-op if present); ensure
   Công Tác workflow + COO role via `setup_cong_tac_workflow.ensure_workflow`.
2. **HR Settings (fresh install only):** set `allow_geolocation_tracking = 1` and
   `allow_employee_checkin_from_mobile_app = 1` if this is a first install (guard with a one-time marker,
   e.g. a flag in a private setting/`HR Settings` untouched-check, so later migrates don't re-force).
3. **Starter master data (only if absent):** one sample `Shift Location` ("Cơ sở chính", radius 200m,
   placeholder coords) + one sample VN `Holiday List` for the install year (Sundays weekly-off + fixed VN
   public holidays: Tết dương 1/1, 30/4, 1/5, 2/9; Tết âm noted as TODO for admin).

**Wiring:** call `ensure_defaults()` from `hrms/install.py::after_install`; add the idempotent
master-data part to the `after_migrate` hook list. Settings + samples run install-only.

## Commands

```
Fresh install (exercises after_install):  bench --site <s> install-app hrms
Migrate (exercises after_migrate + fixtures + patches):  bench --site miyano migrate
Test (rollback harness, NEVER bench run-tests on miyano):  console harness
```

## Project structure (files)

```
hrms/hr/doctype/shift_location/shift_location.js          (new — draw radius circle)
hrms/hr/doctype/employee_checkin/employee_checkin.js      (extend — overlay geofence)
hrms/hr/doctype/employee_checkin/employee_checkin.py      (add get_checkin_geofence)
hrms/setup_vn_defaults.py                                 (ensure_defaults + helpers + tests)
hrms/install.py                                           (call ensure_defaults in after_install)
hrms/hooks.py                                             (after_migrate += idempotent ensure)
```

## Code style

Match the shipped features: ASCII module names, VN labels/strings; tab indent; idempotent guards
(`frappe.db.exists` before create); reuse Frappe controls (Geolocation/Leaflet) — no new map libs;
server helpers small + whitelisted + typed.

## Testing strategy (rollback harness — NEVER `bench run-tests` on `miyano`)

- **A:** unit-test `get_checkin_geofence` (returns the right Shift Location circle for an employee with a
  shift assignment; None when no location / tracking off). Map/circle rendering is **client-side** →
  verified manually in Desk (Chrome), not unit-tested.
- **B:** unit-test `ensure_defaults` idempotency — run twice on a temp state, assert: codes/leave types
  present, workflow + COO role present, a sample Shift Location + Holiday List created once (not
  duplicated), and it never raises. Assert settings-writes happen only under the fresh-install guard.
  Assert `ensure_defaults` touches **no** payroll/attendance transactional data.

## Boundaries

- **Always:** idempotent setup; reuse existing geofence + Geolocation field; VN labels; test via harness.
- **Ask first:** enabling `allow_geolocation_tracking` by default (blocks check-ins lacking a Shift
  Location — confirm rollout); any change to `Employee Checkin.validate_distance_from_shift_location`.
- **Never:** hard-block behavior changes without a flag; commit secrets/API keys; add a paid map/geocoding
  provider; force-override admin settings on every migrate; touch payroll.

## Success criteria (specific, testable)

- [ ] Shift Location form shows a live radius circle on the map; clicking the map sets lat/long (manual verify).
- [ ] Employee Checkin form shows the check-in point + applicable geofence circle (manual verify).
- [ ] `get_checkin_geofence(employee)` returns the correct circle / None (unit test).
- [ ] Fresh `install-app` (or `ensure_defaults`) yields: all VN codes + leave types, Công Tác workflow +
      COO role + custom fields, geolocation + mobile-checkin enabled, one sample Shift Location + VN
      Holiday List — verified on a temp state.
- [ ] `ensure_defaults` is idempotent (run twice → no duplicates, no error) and payroll-neutral (unit test).
- [ ] Reversible via `git revert`; verified on dev `miyano`.

## Open questions (before Plan)

1. **Enable geolocation tracking by default?** It makes check-ins REQUIRE being within a Shift Location
   radius. On sites without Shift Locations configured that would block all check-ins. Confirm: enable by
   default (needs Shift Locations set up first), or ship it OFF and let admin enable after configuring?
2. **Sample Holiday List:** include lunar Tết dates (need per-year input) or only fixed-date holidays +
   Sundays, leaving Tết for the admin?
3. **Sample Shift Location coords:** a placeholder (0,0 / hospital HQ) the admin must edit — acceptable?
4. **after_migrate idempotent ensure:** OK to run the master-data ensure on every migrate (fast, no-op if
   present), or restrict to install only?

## Task breakdown (for /build auto — after approval)

1. `get_checkin_geofence` server helper + unit test.
2. Shift Location `.js`: draw + edit radius circle on the map.
3. Employee Checkin `.js`: overlay geofence circle on the check-in point.
4. `hrms/setup_vn_defaults.py::ensure_defaults` (master data + workflow/role) + idempotency test.
5. HR Settings defaults + sample Shift Location + sample VN Holiday List (install-only guard) + test.
6. Wire `after_install` + `after_migrate`; migrate `miyano`; E2E verify + docs.
