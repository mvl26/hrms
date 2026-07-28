# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt
"""Tests for the VN annual-leave entitlement layer (spec/leave-entitlement-vn.md).
Runs via the rollback harness — writes are rolled back, never committed."""

import json
import os

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

ANNUAL_LEAVE = "Nghỉ phép năm"
FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "..", "fixtures", "leave_type.json")


def load_fixture_types():
	with open(FIXTURE_PATH) as f:
		return {row["name"]: row for row in json.load(f)}


class TestAnnualLeaveEarnedFixture(FrappeTestCase):
	"""T1 — 'Nghỉ phép năm' becomes a monthly earned leave; the other 7 types stay untouched."""

	def test_fixture_json_flags(self):
		types = load_fixture_types()
		annual = types[ANNUAL_LEAVE]
		self.assertEqual(annual["is_earned_leave"], 1)
		self.assertEqual(annual["earned_leave_frequency"], "Monthly")
		# rounding rỗng = không làm tròn: bậc thâm niên 13/14 ngày (13/12=1.083/tháng) phải
		# cộng đủ định mức cuối năm — rounding "0.5" từng làm mất ngày thâm niên (Điều 114)
		self.assertEqual(annual["rounding"], "")
		self.assertEqual(annual["allocate_on_day"], "Last Day")
		# payroll-relevant flags stay untouched
		self.assertEqual(annual["is_lwp"], 0)
		self.assertEqual(annual["is_carry_forward"], 0)
		# every other type keeps is_earned_leave = 0
		for name, row in types.items():
			if name != ANNUAL_LEAVE:
				self.assertEqual(row["is_earned_leave"], 0, f"{name} must not become earned leave")

	def test_fixture_is_lwp_truth_table(self):
		# is_lwp / is_ppl are the ONLY Leave Type levers payroll reads (they build the LWP map that
		# docks payment_days). Lock every type's value so an accidental flip — e.g. making Nghỉ ốm
		# unpaid, or clearing Nghỉ không lương — is caught here instead of on a Salary Slip.
		expected = {
			# leave type: (is_lwp, is_ppl)
			"Nghỉ phép năm": (0, 0),
			"Nghỉ ốm": (0, 0),
			"Nghỉ chăm con ốm": (0, 0),
			"Nghỉ thai sản": (0, 0),
			"Nghỉ tai nạn lao động": (0, 0),
			"Nghỉ bù": (0, 0),
			"Nghỉ kết hôn": (0, 0),
			"Nghỉ con kết hôn": (0, 0),
			"Nghỉ tang": (0, 0),
			"Nghỉ không lương": (1, 0),
		}
		types = load_fixture_types()
		self.assertEqual(set(types), set(expected), "the set of VN leave types changed — update the table")
		for name, (lwp, ppl) in expected.items():
			self.assertEqual(types[name].get("is_lwp", 0), lwp, f"{name}: is_lwp must be {lwp}")
			self.assertEqual(types[name].get("is_ppl", 0), ppl, f"{name}: is_ppl must be {ppl}")

	def test_fixture_matches_leave_type_meta(self):
		# the fixture keys must be real Leave Type fields so `bench migrate` can apply them
		# (applying to the live site is the deploy step — sign-off gated, run manually)
		meta = frappe.get_meta("Leave Type")
		for key in ("is_earned_leave", "earned_leave_frequency", "rounding", "allocate_on_day"):
			self.assertTrue(meta.has_field(key), f"Leave Type has no field {key}")


class TestEntitlementAndLeavePeriod(FrappeTestCase):
	"""T2 — entitlement tiers (Điều 113/114) + idempotent Leave Period helper."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		import erpnext

		cls.company = erpnext.get_default_company() or frappe.get_all("Company", limit=1)[0].name

	def _emp(self, doj):
		from erpnext.setup.doctype.employee.test_employee import make_employee

		return make_employee(f"vn_leave_{doj}@example.com", company=self.company, date_of_joining=doj)

	def test_entitlement_tiers(self):
		from hrms.setup_vn_leave import entitlement_for

		on_date = "2026-01-01"
		# < 5 năm thâm niên -> 12 ngày
		self.assertEqual(entitlement_for(self._emp("2023-03-15"), on_date), 12)
		# đủ 5 năm -> 13
		self.assertEqual(entitlement_for(self._emp("2021-01-01"), on_date), 13)
		# 5 năm chưa đủ (thiếu 1 ngày) -> 12
		self.assertEqual(entitlement_for(self._emp("2021-01-02"), on_date), 12)
		# đủ 10 năm -> 14
		self.assertEqual(entitlement_for(self._emp("2015-12-31"), on_date), 14)

	def test_create_leave_period_idempotent(self):
		from hrms.setup_vn_leave import create_leave_period

		name1 = create_leave_period(2027, self.company)
		period = frappe.get_doc("Leave Period", name1)
		self.assertEqual(str(period.from_date), "2027-01-01")
		self.assertEqual(str(period.to_date), "2027-12-31")
		self.assertEqual(period.is_active, 1)
		self.assertEqual(period.company, self.company)
		# chạy lại -> cùng bản ghi, không nhân đôi
		name2 = create_leave_period(2027, self.company)
		self.assertEqual(name1, name2)
		self.assertEqual(
			len(frappe.get_all("Leave Period", {"company": self.company, "from_date": "2027-01-01"})), 1
		)


class TestAssignAnnualLeave(FrappeTestCase):
	"""T3 — bulk yearly grant: tiered policies + LPA + initial passed-months allocation; idempotent."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		import erpnext

		cls.company = erpnext.get_default_company() or frappe.get_all("Company", limit=1)[0].name

	def setUp(self):
		enable_earned_leave_flags()
		self._old_current_date = frappe.flags.current_date
		# giữa tháng 6/2026 -> 5 tháng trọn (1-5) đã qua với allocate_on_day="Last Day"
		frappe.flags.current_date = "2026-06-15"

	def tearDown(self):
		frappe.flags.current_date = self._old_current_date

	def _emp(self, email, doj):
		from erpnext.setup.doctype.employee.test_employee import make_employee

		return make_employee(email, company=self.company, date_of_joining=doj)

	def test_creates_tiered_policy_assignment_and_allocation(self):
		from hrms.setup_vn_leave import assign_annual_leave

		emp12 = self._emp("vn_assign_t12@example.com", "2024-03-01")  # <5 năm -> 12
		emp13 = self._emp("vn_assign_t13@example.com", "2019-05-01")  # >=5 năm -> 13
		report = assign_annual_leave(2026, self.company, employees=[emp12, emp13])

		self.assertEqual(report[emp12]["status"], "created")
		self.assertEqual(report[emp12]["entitlement"], 12)
		self.assertEqual(report[emp13]["entitlement"], 13)

		for emp, days in ((emp12, 12), (emp13, 13)):
			assignment = frappe.get_doc("Leave Policy Assignment", report[emp]["assignment"])
			self.assertEqual(assignment.docstatus, 1)
			self.assertEqual(assignment.leaves_allocated, 1)
			policy = frappe.get_doc("Leave Policy", assignment.leave_policy)
			self.assertEqual(policy.title, f"VN Phép năm {days} ngày")
			self.assertEqual(policy.leave_policy_details[0].annual_allocation, days)

		# allocation ban đầu = số phép các tháng đã qua (T1-T5 = 5 tháng, bậc 12 -> 1.0/tháng)
		alloc = frappe.get_value(
			"Leave Allocation",
			{"employee": emp12, "leave_type": ANNUAL_LEAVE, "docstatus": 1},
			["new_leaves_allocated", "to_date", "carry_forward"],
			as_dict=True,
		)
		self.assertEqual(alloc.new_leaves_allocated, 5.0)
		self.assertEqual(str(alloc.to_date), "2026-12-31")
		self.assertEqual(alloc.carry_forward, 0)

	def test_idempotent_and_picks_up_new_employee(self):
		from hrms.setup_vn_leave import assign_annual_leave

		emp1 = self._emp("vn_idem_1@example.com", "2024-01-01")
		r1 = assign_annual_leave(2026, self.company, employees=[emp1])
		self.assertEqual(r1[emp1]["status"], "created")

		r2 = assign_annual_leave(2026, self.company, employees=[emp1])
		self.assertEqual(r2[emp1]["status"], "skipped")
		self.assertEqual(
			len(frappe.get_all("Leave Policy Assignment", {"employee": emp1, "docstatus": ("<", 2)})), 1
		)

		emp2 = self._emp("vn_idem_2@example.com", "2024-01-01")
		r3 = assign_annual_leave(2026, self.company, employees=[emp1, emp2])
		self.assertEqual(r3[emp1]["status"], "skipped")
		self.assertEqual(r3[emp2]["status"], "created")

	def test_guard_requires_earned_leave_flags_in_db(self):
		"""Chạy assign khi site CHƯA migrate fixture (is_earned_leave=0) phải throw ngay —
		nếu không, upstream cấp cả năm một cục và allocation bị khóa không sửa được."""
		from hrms.setup_vn_leave import assign_annual_leave

		frappe.db.set_value("Leave Type", ANNUAL_LEAVE, "is_earned_leave", 0, update_modified=False)
		frappe.clear_document_cache("Leave Type", ANNUAL_LEAVE)
		emp = self._emp("vn_guard@example.com", "2024-01-01")
		self.assertRaises(frappe.ValidationError, assign_annual_leave, 2026, self.company, [emp])

	def test_draft_assignment_reported_distinctly(self):
		"""LPA draft (docstatus 0) không được tính là 'đã cấp' — báo 'draft_exists' để HR xử lý,
		không im lặng bỏ đói nhân viên."""
		from hrms.setup_vn_leave import assign_annual_leave, create_leave_period, ensure_leave_policy

		emp = self._emp("vn_draft@example.com", "2024-01-01")
		period = create_leave_period(2026, self.company)
		frappe.get_doc(
			{
				"doctype": "Leave Policy Assignment",
				"employee": emp,
				"assignment_based_on": "Leave Period",
				"leave_policy": ensure_leave_policy(12),
				"leave_period": period,
				"carry_forward": 0,
			}
		).insert(ignore_permissions=True)  # KHÔNG submit -> draft

		report = assign_annual_leave(2026, self.company, employees=[emp])
		self.assertEqual(report[emp]["status"], "draft_exists")
		self.assertEqual(
			len(frappe.get_all("Leave Policy Assignment", {"employee": emp, "docstatus": ("<", 2)})), 1
		)

	def test_existing_manual_allocation_skips_cleanly(self):
		"""Nhân viên đã có Leave Allocation 'Nghỉ phép năm' thủ công cho năm đó (không qua LPA)
		-> skip có lý do, không error; dry_run dự đoán đúng."""
		from hrms.setup_vn_leave import assign_annual_leave, create_leave_period

		emp = self._emp("vn_manualalloc@example.com", "2024-01-01")
		create_leave_period(2026, self.company)
		frappe.get_doc(
			{
				"doctype": "Leave Allocation",
				"employee": emp,
				"leave_type": ANNUAL_LEAVE,
				"from_date": "2026-01-01",
				"to_date": "2026-12-31",
				"new_leaves_allocated": 12,
			}
		).insert(ignore_permissions=True).submit()

		dry = assign_annual_leave(2026, self.company, employees=[emp], dry_run=True)
		self.assertEqual(dry[emp]["status"], "skipped_allocation_exists")
		report = assign_annual_leave(2026, self.company, employees=[emp])
		self.assertEqual(report[emp]["status"], "skipped_allocation_exists")
		self.assertEqual(
			len(frappe.get_all("Leave Policy Assignment", {"employee": emp, "docstatus": ("<", 2)})), 0
		)

	def test_joining_date_assignment_skips_not_error(self):
		"""LPA assignment_based_on='Joining Date' (leave_period NULL) chồng lấn năm
		-> 'skipped_overlapping_assignment', không phải 'error' + Error Log spam."""
		from hrms.setup_vn_leave import assign_annual_leave, ensure_leave_policy

		emp = self._emp("vn_joindate@example.com", "2025-10-01")
		lpa = frappe.get_doc(
			{
				"doctype": "Leave Policy Assignment",
				"employee": emp,
				"assignment_based_on": "Joining Date",
				"leave_policy": ensure_leave_policy(12),
				"carry_forward": 0,
			}
		).insert(ignore_permissions=True)
		lpa.submit()  # effective 2025-10-01 -> 2026-09-30, chồng lấn 2026

		report = assign_annual_leave(2026, self.company, employees=[emp])
		self.assertEqual(report[emp]["status"], "skipped_overlapping_assignment")

	def test_sanity_checks_on_explicit_employee_list(self):
		"""Company khác -> skipped_other_company; DOJ sau kỳ cấp -> skipped_doj_after_period."""
		from hrms.setup_vn_leave import assign_annual_leave
		from hrms.tests.test_utils import create_company

		other_co = create_company("_VN Other Co").name
		emp_other = self._emp("vn_otherco@example.com", "2024-01-01")
		frappe.db.set_value("Employee", emp_other, "company", other_co)
		emp_future = self._emp("vn_futuredoj@example.com", "2027-03-01")

		report = assign_annual_leave(2026, self.company, employees=[emp_other, emp_future])
		self.assertEqual(report[emp_other]["status"], "skipped_other_company")
		self.assertEqual(report[emp_future]["status"], "skipped_doj_after_period")

	def test_dry_run_writes_nothing(self):
		from hrms.setup_vn_leave import assign_annual_leave

		emp = self._emp("vn_dry@example.com", "2024-01-01")
		before = frappe.get_all("Leave Policy Assignment", {"employee": emp})
		report = assign_annual_leave(2026, self.company, employees=[emp], dry_run=True)
		self.assertEqual(report[emp]["status"], "would_create")
		self.assertEqual(report[emp]["entitlement"], 12)
		self.assertEqual(frappe.get_all("Leave Policy Assignment", {"employee": emp}), before)


class TestMonthlyAccrualAndCap(FrappeTestCase):
	"""T4 — scheduler stock cộng dồn 1 ngày/tháng (bậc 12) và cap tại định mức năm."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		import erpnext

		cls.company = erpnext.get_default_company() or frappe.get_all("Company", limit=1)[0].name

	def setUp(self):
		enable_earned_leave_flags()
		self._old_current_date = frappe.flags.current_date

	def tearDown(self):
		frappe.flags.current_date = self._old_current_date

	def test_accrues_monthly_and_caps_at_entitlement(self):
		from erpnext.setup.doctype.employee.test_employee import make_employee

		from hrms.hr.utils import allocate_earned_leaves
		from hrms.setup_vn_leave import assign_annual_leave

		frappe.flags.current_date = getdate("2026-06-15")
		emp = make_employee("vn_accrual@example.com", company=self.company, date_of_joining="2024-01-01")
		report = assign_annual_leave(2026, self.company, employees=[emp])
		alloc_name = frappe.db.get_value(
			"Leave Allocation", {"employee": emp, "leave_type": ANNUAL_LEAVE, "docstatus": 1}, "name"
		)
		self.assertEqual(report[emp]["status"], "created")
		self.assertEqual(frappe.db.get_value("Leave Allocation", alloc_name, "total_leaves_allocated"), 5.0)

		# chạy scheduler tại cuối mỗi tháng còn lại -> +1.0/tháng, chạm đúng 12.0 cuối năm
		for last_day in (
			"2026-06-30",
			"2026-07-31",
			"2026-08-31",
			"2026-09-30",
			"2026-10-31",
			"2026-11-30",
			"2026-12-31",
		):
			frappe.flags.current_date = getdate(last_day)
			allocate_earned_leaves()

		self.assertEqual(frappe.db.get_value("Leave Allocation", alloc_name, "total_leaves_allocated"), 12.0)

		# chạy thêm lần nữa -> không vượt định mức năm (cap upstream)
		allocate_earned_leaves()
		self.assertEqual(frappe.db.get_value("Leave Allocation", alloc_name, "total_leaves_allocated"), 12.0)

	def test_seniority_tier_accrues_full_entitlement_by_year_end(self):
		"""Điều 114: bậc 13 ngày phải nhận đủ 13 ngày sau 12 tháng cộng dồn.
		Regression cho bug rounding 0.5: 13/12=1.083 bị tròn xuống 1.0/tháng -> mất ngày thâm niên."""
		from erpnext.setup.doctype.employee.test_employee import make_employee

		from hrms.hr.utils import allocate_earned_leaves
		from hrms.setup_vn_leave import assign_annual_leave

		frappe.flags.current_date = getdate("2026-01-15")
		emp = make_employee("vn_accrual_t13@example.com", company=self.company, date_of_joining="2019-05-01")
		report = assign_annual_leave(2026, self.company, employees=[emp])
		self.assertEqual(report[emp]["entitlement"], 13)
		alloc_name = frappe.db.get_value(
			"Leave Allocation", {"employee": emp, "leave_type": ANNUAL_LEAVE, "docstatus": 1}, "name"
		)

		for month, day in (
			(1, 31),
			(2, 28),
			(3, 31),
			(4, 30),
			(5, 31),
			(6, 30),
			(7, 31),
			(8, 31),
			(9, 30),
			(10, 31),
			(11, 30),
			(12, 31),
		):
			frappe.flags.current_date = getdate(f"2026-{month:02d}-{day:02d}")
			allocate_earned_leaves()

		total = frappe.db.get_value("Leave Allocation", alloc_name, "total_leaves_allocated")
		self.assertAlmostEqual(total, 13.0, delta=0.05)

	def test_midyear_joiner_gets_prorated_initial_allocation(self):
		"""Nhân viên vào giữa năm: assignment không throw, allocation pro-rata từ DOJ."""
		from erpnext.setup.doctype.employee.test_employee import make_employee

		from hrms.setup_vn_leave import assign_annual_leave

		frappe.flags.current_date = getdate("2026-06-15")
		emp = make_employee("vn_midyear@example.com", company=self.company, date_of_joining="2026-03-10")
		report = assign_annual_leave(2026, self.company, employees=[emp])
		self.assertEqual(report[emp]["status"], "created")
		total = frappe.db.get_value(
			"Leave Allocation",
			{"employee": emp, "leave_type": ANNUAL_LEAVE, "docstatus": 1},
			"total_leaves_allocated",
		)
		# T3 (partial, từ 10/03) + T4 + T5 đã qua -> ~2.5 ngày; quan trọng: > 0 và <= 12
		self.assertGreater(total, 0)
		self.assertLessEqual(total, 12)


class TestUnlockedLeaveFlows(FrappeTestCase):
	"""T5 — với định mức đã cấp: Leave Application phép năm submit được (Attendance mang mã P);
	Compensatory Leave Request submit được (Leave Period + Holiday List + Attendance ngày lễ)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		import erpnext

		cls.company = erpnext.get_default_company() or frappe.get_all("Company", limit=1)[0].name

	def setUp(self):
		enable_earned_leave_flags()
		self._old_current_date = frappe.flags.current_date

	def tearDown(self):
		frappe.flags.current_date = self._old_current_date

	def _emp(self, email, doj="2024-01-01"):
		from erpnext.setup.doctype.employee.test_employee import make_employee

		return make_employee(email, company=self.company, date_of_joining=doj)

	def test_leave_application_submits_and_attendance_gets_code_P(self):
		from hrms.setup_vn_leave import assign_annual_leave

		frappe.flags.current_date = getdate("2026-06-15")
		emp = self._emp("vn_unlock_la@example.com")
		assign_annual_leave(2026, self.company, employees=[emp])

		# holiday list rỗng cho nhân viên -> ngày nghỉ chọn chắc chắn là ngày làm việc
		hl = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": "VN empty HL for LA test",
				"from_date": "2026-01-01",
				"to_date": "2026-12-31",
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Employee", emp, "holiday_list", hl.name)

		leave_date = "2026-07-08"  # thứ Tư, quá khứ so với hôm nay -> Attendance được sinh ngay
		la = frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": emp,
				"leave_type": ANNUAL_LEAVE,
				"custom_leave_reason": "Nghỉ phép năm",  # quỹ phép năm bắt buộc chọn Loại nghỉ (single-pool)
				"from_date": leave_date,
				"to_date": leave_date,
				"description": "test unlock",
				"company": self.company,
				"status": "Approved",
				"leave_approver": "Administrator",
			}
		).insert(ignore_permissions=True)
		la.submit()
		self.assertEqual(la.docstatus, 1)

		att = frappe.db.get_value(
			"Attendance",
			{"employee": emp, "attendance_date": leave_date, "docstatus": 1},
			["status", "leave_type", "custom_attendance_code"],
			as_dict=True,
		)
		self.assertIsNotNone(att, "Leave Application phải sinh Attendance cho ngày quá khứ")
		self.assertEqual(att.status, "On Leave")
		self.assertEqual(att.leave_type, ANNUAL_LEAVE)
		self.assertEqual(att.custom_attendance_code, "P")

	def test_compensatory_leave_request_submits_and_credits_nghi_bu(self):
		from hrms.setup_vn_holiday import create_vn_holiday_list
		from hrms.setup_vn_leave import create_leave_period

		emp = self._emp("vn_unlock_clr@example.com")
		create_leave_period(2026, self.company)
		hl = create_vn_holiday_list(2026, self.company, weekly_off_days=("Sunday",))
		frappe.db.set_value("Employee", emp, "holiday_list", hl)

		work_date = "2026-07-05"  # Chủ nhật (weekly off), quá khứ
		frappe.get_doc(
			{
				"doctype": "Attendance",
				"employee": emp,
				"attendance_date": work_date,
				"status": "Present",
				"company": self.company,
			}
		).insert(ignore_permissions=True).submit()

		clr = frappe.get_doc(
			{
				"doctype": "Compensatory Leave Request",
				"employee": emp,
				"leave_type": "Nghỉ bù",
				"work_from_date": work_date,
				"work_end_date": work_date,
				"reason": "làm bù Chủ nhật",
			}
		).insert(ignore_permissions=True)
		clr.submit()
		self.assertEqual(clr.docstatus, 1)

		alloc = frappe.db.get_value(
			"Leave Allocation",
			{"employee": emp, "leave_type": "Nghỉ bù", "docstatus": 1},
			["total_leaves_allocated"],
			as_dict=True,
		)
		self.assertIsNotNone(alloc, "CLR submit phải tạo allocation Nghỉ bù")
		self.assertEqual(alloc.total_leaves_allocated, 1.0)


def enable_earned_leave_flags():
	"""Apply the fixture's earned-leave flags inside the current (rolled-back) transaction,
	so tests exercise the post-migrate behaviour without touching the live site.
	Reads the values FROM the fixture JSON — single source of truth."""
	annual = load_fixture_types()[ANNUAL_LEAVE]
	frappe.db.set_value(
		"Leave Type",
		ANNUAL_LEAVE,
		{
			"is_earned_leave": annual["is_earned_leave"],
			"earned_leave_frequency": annual["earned_leave_frequency"],
			"rounding": annual["rounding"],
			"allocate_on_day": annual["allocate_on_day"],
		},
		update_modified=False,
	)
	frappe.clear_document_cache("Leave Type", ANNUAL_LEAVE)
