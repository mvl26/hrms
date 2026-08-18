app_name = "hrms"
app_title = "Miyano HR"
app_publisher = "Miyano Việt Nam"
app_description = "Phần mềm Nhân sự & Tiền lương Miyano"
app_email = "info@miyano.com.vn"
app_license = "Proprietary"
required_apps = ["frappe/erpnext"]

add_to_apps_screen = [
	{
		"name": "hrms",
		"logo": "/assets/hrms/images/miyano-hr-logo.png",
		"title": "Miyano HR",
		"route": "/app/hr",
		"has_permission": "hrms.hr.utils.check_app_permission",
	}
]

# Nạp vào <head> của desk
app_include_js = [
	"hrms.bundle.js",
]
app_include_css = "hrms.bundle.css"

# Script bổ sung cho form của từng doctype
doctype_js = {
	"Employee": "public/js/erpnext/employee.js",
	"Company": "public/js/erpnext/company.js",
	"Department": "public/js/erpnext/department.js",
	"Timesheet": "public/js/erpnext/timesheet.js",
	"Payment Entry": "public/js/erpnext/payment_entry.js",
	"Journal Entry": "public/js/erpnext/journal_entry.js",
	"Delivery Trip": "public/js/erpnext/delivery_trip.js",
	"Bank Transaction": "public/js/erpnext/bank_transaction.js",
}

calendars = ["Leave Application"]

# Tự sinh trang web cho từng bản ghi của doctype này
website_generators = ["Job Opening"]

website_route_rules = [
	{"from_route": "/hrms/<path:app_path>", "to_route": "hrms"},
	{"from_route": "/hr/<path:app_path>", "to_route": "roster"},
]

# Hàm và bộ lọc bổ sung cho môi trường Jinja
jinja = {
	"methods": [
		"hrms.utils.get_country",
		# màu ô + chú giải cho print format bảng chấm công (thuần hiển thị)
		"hrms.hr.report.monthly_attendance_report.monthly_attendance_report.attendance_cell_style",
		"hrms.hr.report.monthly_attendance_report.monthly_attendance_report.attendance_state_styles",
	],
}

# Cài đặt
after_install = [
	"hrms.install.after_install",
	# MVL payroll: đóng gói cấu hình lương (component + 6 cấu trúc theo loại + custom fields + tham số)
	# sẵn NGAY khi cài app (không chờ migrate đầu). Idempotent; cấu trúc hoãn sang after_migrate nếu site
	# chưa có Company (cài app trước setup wizard).
	"hrms.vn_payroll.setup_mvl.ensure_mvl_defaults",
]
after_migrate = [
	"hrms.setup.update_select_perm_after_install",
	# Fork defaults: self-heal Công Tác workflow + COO role and verify fixture master data every migrate.
	"hrms.setup_vn_defaults.ensure_defaults",
	# MVL payroll: đóng gói cấu hình lương (component + structure + custom fields + tham số) vào app,
	# self-heal mỗi migrate, không ghi đè giá trị HR đã sửa.
	"hrms.vn_payroll.setup_mvl.ensure_mvl_defaults",
]

# Gỡ cài đặt
before_uninstall = "hrms.uninstall.before_uninstall"

# Tích hợp: chạy khi một app khác được cài / gỡ (tên app truyền vào làm tham số)
after_app_install = "hrms.setup.after_app_install"
before_app_uninstall = "hrms.setup.before_app_uninstall"

# Phân quyền
has_upload_permission = {"Employee": "erpnext.setup.doctype.employee.employee.has_upload_permission"}

# Ghi đè lớp doctype chuẩn
override_doctype_class = {
	"Employee": "hrms.overrides.employee_master.EmployeeMaster",
	"Timesheet": "hrms.overrides.employee_timesheet.EmployeeTimesheet",
	"Payment Entry": "hrms.overrides.employee_payment_entry.EmployeePaymentEntry",
	"Project": "hrms.overrides.employee_project.EmployeeProject",
}

# Tác dụng phụ liên doctype: bám vào phương thức/sự kiện của tài liệu

doc_events = {
	"Expense Claim": {
		"after_insert": "hrms.hr.doctype.business_trip.business_trip.link_claim_to_trip",
	},
	# Miyano: Yêu cầu chấm công (khác Đơn xin nghỉ) — ngày vẫn làm việc/tính có mặt (WFH, quên chấm
	# công, on-duty, đi muộn/về sớm). Có DUYỆT bởi quản lý trực tiếp + ghi mã công riêng (payroll-
	# neutral). Xem attendance_request_miyano.py. (Đi công tác có chi phí vẫn qua Công Tác/Business Trip.)
	# Khoá kỳ: Bảng Công Tháng đã chốt thì ngày công trong kỳ không được thêm/sửa/huỷ nữa,
	# nếu không thì bảng đã ký và phiếu lương lệch nhau trong im lặng (spec §6).
	"Attendance": {
		"before_insert": "hrms.hr.period_lock.guard_period_not_locked",
		"on_update_after_submit": "hrms.hr.period_lock.guard_period_not_locked",
		"before_cancel": "hrms.hr.period_lock.guard_period_not_locked",
	},
	"Attendance Request": {
		"before_insert": "hrms.hr.doctype.attendance_request.attendance_request_miyano.set_default_approver",
		"validate": "hrms.hr.doctype.attendance_request.attendance_request_miyano.set_default_approver",
		"after_insert": "hrms.hr.doctype.attendance_request.attendance_request_miyano.assign_to_approver",
		"before_submit": "hrms.hr.doctype.attendance_request.attendance_request_miyano.guard_submit",
		"on_submit": "hrms.hr.doctype.attendance_request.attendance_request_miyano.set_attendance_request_code",
	},
	"User": {
		"validate": [
			"erpnext.setup.doctype.employee.employee.validate_employee_role",
			"hrms.overrides.employee_master.update_approver_user_roles",
		],
		"on_update": "erpnext.setup.doctype.employee.employee.update_user_permissions",
	},
	"Company": {
		"validate": "hrms.overrides.company.validate_default_accounts",
		"on_update": [
			"hrms.overrides.company.make_company_fixtures",
			"hrms.overrides.company.set_default_hr_accounts",
		],
		"on_trash": "hrms.overrides.company.handle_linked_docs",
	},
	"Holiday List": {
		"on_update": "hrms.utils.holiday_list.invalidate_cache",
		"on_trash": "hrms.utils.holiday_list.invalidate_cache",
	},
	"Timesheet": {"validate": "hrms.hr.utils.validate_active_employee"},
	# Miyano: lương NET gross-up theo công thức MVL — chạy sau calculate_net_pay của controller.
	# THỨ TỰ BA BƯỚC NÀY LÀ BẮT BUỘC, đừng đổi:
	# 1. `add_paid_holidays` — cộng ngày nghỉ lễ vào `total_working_days`/`payment_days`. Phải chạy
	#    TRƯỚC cổng, vì cổng so `payment_days` với "Tổng công" của bảng đã chốt mà bảng đã đếm lễ;
	#    chạy sau thì cổng so số chưa cộng với số đã cộng và chặn sạch phiếu tháng có lễ.
	# 2. `sheet_gate.gate` — chặn phiếu khi kỳ chưa chốt công và đối soát với bảng đã chốt. Mặc định
	#    TẮT — bật bằng site config `hrms_enforce_sheet_gate` (spec §7).
	# 3. `apply_mvl` — engine lương, đọc số ngày đã chuẩn hoá ở bước 1.
	"Salary Slip": {
		"validate": [
			"hrms.vn_payroll.salary_slip_hook.add_paid_holidays",
			"hrms.vn_payroll.sheet_gate.gate",
			"hrms.vn_payroll.salary_slip_hook.apply_mvl",
		]
	},
	# Miyano: gắn mã công cho Loại nghỉ ngay tại form Loại nghỉ. Nguồn sự thật vẫn là
	# Attendance Code.leave_type (một loại nghỉ ứng nhiều mã: P và 1/2P) — ô trên Leave Type chỉ là
	# mặt bàn để nhập, lưu thì ghi ngược. Chỉ chạm master data, không đụng ngày công đã ghi.
	"Leave Type": {
		"on_update": [
			"hrms.hr.leave_type_code.sync_code_to_leave_type",
			"hrms.hr.leave_type_code.warn_if_unmapped",
		],
	},
	# Miyano: gộp một quỹ phép năm — validate mã lý do; sau duyệt ghi mã lên Attendance (thuần hiển thị).
	"Leave Application": {
		"validate": "hrms.hr.doctype.leave_application.leave_single_pool.validate_pool_code",
		"on_submit": "hrms.hr.doctype.leave_application.leave_single_pool.set_leave_attendance_code",
	},
	"Payment Entry": {
		"on_submit": "hrms.hr.doctype.expense_claim.expense_claim.update_payment_for_expense_claim",
		"on_cancel": "hrms.hr.doctype.expense_claim.expense_claim.update_payment_for_expense_claim",
		"on_update_after_submit": "hrms.hr.doctype.expense_claim.expense_claim.update_payment_for_expense_claim",
	},
	"Journal Entry": {
		"validate": "hrms.hr.doctype.expense_claim.expense_claim.validate_expense_claim_in_jv",
		"on_submit": [
			"hrms.hr.doctype.expense_claim.expense_claim.update_payment_for_expense_claim",
			"hrms.hr.doctype.full_and_final_statement.full_and_final_statement.update_full_and_final_statement_status",
			"hrms.payroll.doctype.salary_withholding.salary_withholding.update_salary_withholding_payment_status",
		],
		"on_update_after_submit": "hrms.hr.doctype.expense_claim.expense_claim.update_payment_for_expense_claim",
		"on_cancel": [
			"hrms.hr.doctype.expense_claim.expense_claim.update_payment_for_expense_claim",
			"hrms.payroll.doctype.salary_slip.salary_slip.unlink_ref_doc_from_salary_slip",
			"hrms.hr.doctype.full_and_final_statement.full_and_final_statement.update_full_and_final_statement_status",
			"hrms.payroll.doctype.salary_withholding.salary_withholding.update_salary_withholding_payment_status",
		],
	},
	"Loan": {"validate": "hrms.hr.utils.validate_loan_repay_from_salary"},
	"Employee": {
		"validate": "hrms.overrides.employee_master.validate_onboarding_process",
		"on_update": [
			"hrms.overrides.employee_master.update_approver_role",
			"hrms.overrides.employee_master.publish_update",
		],
		"after_insert": "hrms.overrides.employee_master.update_job_applicant_and_offer",
		"on_trash": "hrms.overrides.employee_master.update_employee_transfer",
		"after_delete": "hrms.overrides.employee_master.publish_update",
	},
	"Project": {"validate": "hrms.controllers.employee_boarding_controller.update_employee_boarding_status"},
	"Task": {"on_update": "hrms.controllers.employee_boarding_controller.update_task"},
}

# Tác vụ nền theo lịch
scheduler_events = {
	"all": [
		"hrms.hr.doctype.interview.interview.send_interview_reminder",
	],
	"hourly": [
		"hrms.hr.doctype.daily_work_summary_group.daily_work_summary_group.trigger_emails",
	],
	"hourly_long": [
		"hrms.hr.doctype.shift_type.shift_type.update_last_sync_of_checkin",
		"hrms.hr.doctype.shift_type.shift_type.process_auto_attendance_for_all_shifts",
		"hrms.hr.doctype.shift_schedule_assignment.shift_schedule_assignment.process_auto_shift_creation",
	],
	"daily": [
		"hrms.controllers.employee_reminders.send_birthday_reminders",
		"hrms.controllers.employee_reminders.send_work_anniversary_reminders",
		"hrms.hr.doctype.daily_work_summary_group.daily_work_summary_group.send_summary",
		"hrms.hr.doctype.interview.interview.send_daily_feedback_reminder",
		"hrms.hr.doctype.job_opening.job_opening.close_expired_job_openings",
	],
	"daily_long": [
		"hrms.hr.doctype.leave_ledger_entry.leave_ledger_entry.process_expired_allocation",
		"hrms.hr.utils.generate_leave_encashment",
		"hrms.hr.utils.allocate_earned_leaves",
	],
	"weekly": ["hrms.controllers.employee_reminders.send_reminders_in_advance_weekly"],
	"monthly": ["hrms.controllers.employee_reminders.send_reminders_in_advance_monthly"],
}

advance_payment_doctypes = ["Leave Encashment", "Gratuity", "Employee Advance"]

invoice_doctypes = ["Expense Claim"]

period_closing_doctypes = ["Payroll Entry"]

accounting_dimension_doctypes = [
	"Expense Claim",
	"Expense Claim Detail",
	"Expense Taxes and Charges",
	"Payroll Entry",
	"Leave Encashment",
]

bank_reconciliation_doctypes = ["Expense Claim"]

# Kiểm thử
before_tests = "hrms.tests.test_utils.before_tests"

# Truy vấn khớp lệnh cho Đối soát ngân hàng
get_matching_queries = "hrms.hr.utils.get_matching_queries"

# Doctype của ERPNext đưa vào Tìm kiếm toàn cục
global_search_doctypes = {
	"Default": [
		{"doctype": "Salary Slip", "index": 19},
		{"doctype": "Leave Application", "index": 20},
		{"doctype": "Expense Claim", "index": 21},
		{"doctype": "Employee Grade", "index": 37},
		{"doctype": "Job Opening", "index": 39},
		{"doctype": "Job Applicant", "index": 40},
		{"doctype": "Job Offer", "index": 41},
		{"doctype": "Salary Structure Assignment", "index": 42},
		{"doctype": "Appraisal", "index": 43},
	],
}

# Mỗi hàm ghi đè nhận tham số `data` — sinh từ bản dựng gốc của dashboard doctype,
# kèm mọi sửa đổi mà các app khác đã áp lên nó.
override_doctype_dashboards = {
	"Employee": "hrms.overrides.dashboard_overrides.get_dashboard_for_employee",
	"Holiday List": "hrms.overrides.dashboard_overrides.get_dashboard_for_holiday_list",
	"Task": "hrms.overrides.dashboard_overrides.get_dashboard_for_project",
	"Project": "hrms.overrides.dashboard_overrides.get_dashboard_for_project",
	"Timesheet": "hrms.overrides.dashboard_overrides.get_dashboard_for_timesheet",
	"Bank Account": "hrms.overrides.dashboard_overrides.get_dashboard_for_bank_account",
}

ignore_links_on_delete = ["PWA Notification"]

company_data_to_be_ignored = [
	"Salary Component Account",
	"Salary Structure",
	"Salary Structure Assignment",
	"Payroll Period",
	"Income Tax Slab",
	"Leave Period",
	"Leave Policy Assignment",
	"Employee Onboarding Template",
	"Employee Separation Template",
]

# VN timekeeping (mã công) master data — deployed to all sites via `bench migrate`.
# Leave Type is filtered to only the VN anchors so existing/standard Leave Types are not exported.
fixtures = [
	{
		"dt": "Leave Type",
		"filters": {
			"name": [
				"in",
				[
					"Nghỉ phép năm",
					"Nghỉ ốm",
					"Nghỉ chăm con ốm",
					"Nghỉ thai sản",
					"Nghỉ tai nạn lao động",
					"Nghỉ bù",
					"Nghỉ không lương",
					"Nghỉ kết hôn",
					"Nghỉ con kết hôn",
					"Nghỉ tang",
				],
			]
		},
	},
	"Attendance Code",
	{
		"dt": "Custom Field",
		"filters": {
			"name": [
				"in",
				[
					"Attendance-custom_attendance_code",
					"Attendance-custom_morning_code",
					"Attendance-custom_afternoon_code",
					"Attendance-custom_work_credit",
					"Attendance-custom_lunch",
					"Leave Type-custom_attendance_code",
					"Leave Application-custom_attendance_code",
					"Leave Application-custom_leave_reason",
					"Leave Application-custom_half_day_period",
					"Attendance Request-custom_approver",
					"Attendance Request-custom_half_day_session",
					"Expense Claim-custom_business_trip",
					"Shift Type-custom_split_half_day",
					"Shift Type-custom_lunch_start",
					"Shift Type-custom_lunch_end",
					"Shift Type-custom_flexible_shift",
					"Shift Type-custom_flex_band_minutes",
					"Shift Type-custom_min_work_hours",
					"Employee-custom_citizen_id",
					"Employee-custom_social_insurance_no",
					"Employee-custom_exempt_from_checkin",
					"Employee-custom_exempt_from_checkin_from",
					"Attendance-custom_auto_filled",
				],
			]
		},
	},
	# Miyano: mở rộng options field `reason` của Attendance Request (thêm Quên chấm công / Đi muộn-về
	# sớm bên cạnh Work From Home / On Duty). Lọc theo doc_type+field_name (không dùng `name in` nên
	# test đồng bộ bỏ qua) → export đúng 1 property setter này.
	{
		"dt": "Property Setter",
		"filters": {"doc_type": "Attendance Request", "field_name": "reason"},
	},
]
