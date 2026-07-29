const routes = [
	// Miyano: Yêu cầu chấm công (mở lại) — WFH / quên chấm công / on-duty / đi muộn-về sớm, duyệt
	// bởi quản lý trực tiếp (attendance_request_miyano.py). Khác Đơn xin nghỉ (nghỉ) và Công Tác (đi
	// công tác có chi phí, duyệt COO).
	{
		name: "AttendanceRequestListView",
		path: "/attendance-requests",
		component: () => import("@/views/attendance/AttendanceRequestList.vue"),
	},
	{
		name: "AttendanceRequestFormView",
		path: "/attendance-requests/new",
		component: () => import("@/views/attendance/AttendanceRequestForm.vue"),
	},
	{
		name: "AttendanceRequestDetailView",
		path: "/attendance-requests/:id",
		props: true,
		component: () => import("@/views/attendance/AttendanceRequestForm.vue"),
	},
	{
		name: "ShiftRequestListView",
		path: "/shift-requests",
		component: () => import("@/views/attendance/ShiftRequestList.vue"),
	},
	{
		name: "ShiftRequestFormView",
		path: "/shift-requests/new",
		component: () => import("@/views/attendance/ShiftRequestForm.vue"),
	},
	{
		name: "ShiftRequestDetailView",
		path: "/shift-requests/:id",
		props: true,
		component: () => import("@/views/attendance/ShiftRequestForm.vue"),
	},
	{
		name: "ShiftAssignmentListView",
		path: "/shift-assignments",
		component: () => import("@/views/attendance/ShiftAssignmentList.vue"),
	},
	{
		name: "ShiftAssignmentFormView",
		path: "/shift-assignments/new",
		component: () => import("@/views/attendance/ShiftAssignmentForm.vue"),
	},
	{
		name: "ShiftAssignmentDetailView",
		path: "/shift-assignments/:id",
		props: true,
		component: () => import("@/views/attendance/ShiftAssignmentForm.vue"),
	},
	{
		name: "EmployeeCheckinListView",
		path: "/employee-checkins",
		component: () => import("@/views/attendance/EmployeeCheckinList.vue"),
	},
]

export default routes
