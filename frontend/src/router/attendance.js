const routes = [
	// Miyano: bỏ 3 route Attendance Request (list / new / detail) — xin đi công tác đi qua
	// Công Tác (Business Trip) để có duyệt COO. Attendance Request bị khoá server-side ở
	// business_trip.block_attendance_request, nên các màn hình này chỉ dẫn tới ngõ cụt.
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
