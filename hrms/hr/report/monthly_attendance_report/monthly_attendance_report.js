// Copyright (c) 2026, Miyano Việt Nam.
// Tên báo cáo viết thẳng chứ không đặt hằng số ở top-level: `frappe.dom.eval` chèn file này
// thành <script> chạy ở phạm vi TOÀN CỤC, và Custom Report dẫn xuất sẽ nạp lại — `const` gặp
// lần eval thứ hai là vỡ `SyntaxError: already been declared`, kéo sập cả script báo cáo.
frappe.query_reports["Monthly Attendance Report"] = {
	filters: [
		{
			fieldname: "month",
			label: __("Tháng"),
			fieldtype: "Select",
			options: [
				{ value: 1, label: __("Jan") },
				{ value: 2, label: __("Feb") },
				{ value: 3, label: __("Mar") },
				{ value: 4, label: __("Apr") },
				{ value: 5, label: __("May") },
				{ value: 6, label: __("Jun") },
				{ value: 7, label: __("Jul") },
				{ value: 8, label: __("Aug") },
				{ value: 9, label: __("Sep") },
				{ value: 10, label: __("Oct") },
				{ value: 11, label: __("Nov") },
				{ value: 12, label: __("Dec") },
			],
			default: frappe.datetime.str_to_obj(frappe.datetime.get_today()).getMonth() + 1,
			reqd: 1,
		},
		{
			fieldname: "year",
			label: __("Năm"),
			fieldtype: "Select",
			reqd: 1,
		},
		{
			fieldname: "company",
			label: __("Công ty"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "include_company_descendants",
			label: __("Gồm công ty con"),
			fieldtype: "Check",
			default: 1,
		},
	],

	onload: function (report) {
		// Luồng chấm công: BẢNG CÔNG (đang ở đây) -> soát công -> chốt công -> lương.
		// Hai nút này là chặng nối; đứng ở báo cáo là đi tiếp được, không phải nhớ đường.
		report.page.add_inner_button(__("Soát công"), () => {
			const f = report.get_values();
			frappe.route_options = {
				month: String(f.month),
				year: f.year,
				company: f.company,
				department: f.department,
			};
			frappe.set_route("attendance-review");
		});

		report.page.add_inner_button(__("Chốt công tháng"), () => {
			const f = report.get_values();
			frappe.call({
				method: "hrms.hr.doctype.monthly_attendance_sheet.monthly_attendance_sheet.get_or_create_sheet",
				args: {
					month: String(f.month),
					year: f.year,
					company: f.company,
					department: f.department,
				},
				freeze: true,
				freeze_message: __("Đang mở bảng chốt công..."),
				callback: (r) => {
					if (r.message) frappe.set_route("Form", "Monthly Attendance Sheet", r.message);
				},
			});
		});

		// Dọn các ngày mà mã công lệch với status/leave_type (thường là V kẹt lại sau khi đơn nghỉ
		// duyệt đè lên bản ghi Vắng). XEM TRƯỚC rồi mới áp — đây là dữ liệu lương thật.
		report.page.add_inner_button(__("Đồng bộ mã công"), () => {
			const f = report.get_values();
			frappe.call({
				method: "hrms.hr.attendance_code_sync.preview_sync",
				args: { filters: { month: String(f.month), year: f.year, company: f.company } },
				freeze: true,
				freeze_message: __("Đang rà mã công..."),
				callback: (r) => {
					const changes = (r.message && r.message.changes) || [];
					if (!changes.length) {
						frappe.msgprint({
							title: __("Không có gì để đồng bộ"),
							message: __("Mọi ngày công trong kỳ đã khớp mã."),
							indicator: "green",
						});
						return;
					}
					const rows = changes
						.map(
							(c) =>
								`<tr><td>${frappe.utils.escape_html(
									c.employee_name || c.employee,
								)}</td>
								 <td>${c.attendance_date}</td>
								 <td>${frappe.utils.escape_html(c.leave_type || c.status || "")}</td>
								 <td>${
										c.old_code === c.new_code
											? frappe.utils.escape_html(c.new_code)
											: `<b>${frappe.utils.escape_html(
													c.old_code || "—",
											  )}</b> → <b>${frappe.utils.escape_html(
													c.new_code,
											  )}</b>`
									}</td>
								 <td>${
										c.old_credit === c.new_credit
											? c.new_credit
											: `<b>${c.old_credit}</b> → <b>${c.new_credit}</b>`
									}</td></tr>`,
						)
						.join("");
					const d = new frappe.ui.Dialog({
						title: __("Đồng bộ mã công — {0} ngày", [changes.length]),
						size: "large",
						fields: [
							{
								fieldtype: "HTML",
								options: `<p>${__(
									"Chỉ sửa mã công hiển thị. Trạng thái, loại nghỉ và nửa ngày giữ nguyên nên lương không đổi.",
								)}</p>
								<div style="max-height:50vh;overflow:auto">
								<table class="table table-bordered"><thead><tr>
								<th>${__("Nhân viên")}</th><th>${__("Ngày")}</th><th>${__("Loại nghỉ")}</th><th>${__(
									"Mã công",
								)}</th><th>${__("Công")}</th>
								</tr></thead><tbody>${rows}</tbody></table></div>`,
							},
							{
								fieldtype: "Small Text",
								fieldname: "reason",
								label: __("Lý do"),
								reqd: 1,
								default: __("Đồng bộ mã công theo loại nghỉ"),
							},
						],
						primary_action_label: __("Áp dụng"),
						primary_action: (v) => {
							frappe.call({
								method: "hrms.hr.attendance_code_sync.apply_sync",
								args: { rows: changes, reason: v.reason },
								freeze: true,
								freeze_message: __("Đang đồng bộ..."),
								callback: (res) => {
									d.hide();
									const m = res.message || {};
									let msg = __("Đã đồng bộ {0} ngày.", [m.applied || 0]);
									if ((m.skipped || []).length)
										msg +=
											"<br>" +
											__("Bỏ qua {0} ngày (kỳ đã chốt).", [
												m.skipped.length,
											]);
									frappe.msgprint({
										title: __("Xong"),
										message: msg,
										indicator: "green",
									});
									report.refresh();
								},
							});
						},
					});
					d.show();
				},
			});
		});

		// Export mặc định của Frappe dựng file qua `make_xlsx()` — đường đó không có chỗ móc để tô
		// màu nên file ra trắng trơn, mất sạch 10 màu trạng thái của bảng.
		//
		// CẨN THẬN: `frappe.query_report` là MỘT instance dùng chung cho MỌI query report —
		// `load_report()` chỉ đổi `report_name` chứ không dựng lại object. Ghi đè thẳng
		// `export_report` vì thế rò sang mọi báo cáo khác trong cùng phiên: mở bảng chấm công rồi
		// sang Salary Register bấm Export là gọi nhầm vào đây (lỗi "Please select month and year",
		// 2026-08-03). Nên phải bọc MỘT LẦN và luôn kiểm tên báo cáo lúc bấm.
		if (!report._vn_export_patched) {
			report._vn_export_patched = true;
			const fallback = report.export_report.bind(report); // bản gốc trên prototype
			report.export_report = function () {
				if (this.report_name === "Monthly Attendance Report")
					return vn_export_dialog(this);
				return fallback();
			};
		}

		// bảng màu do server định nghĩa (một nguồn duy nhất) — formatter chỉ tra, không tự phân loại
		frappe.call({
			method: "hrms.hr.report.monthly_attendance_report.monthly_attendance_report.get_color_map",
			callback: function (r) {
				frappe.query_reports["Monthly Attendance Report"]._state_styles = r.message || {};
			},
		});
		return frappe.call({
			method: "hrms.hr.report.monthly_attendance_sheet.monthly_attendance_sheet.get_attendance_years",
			callback: function (r) {
				const year_filter = report.get_filter("year");
				year_filter.df.options = r.message;
				year_filter.df.default = r.message.split("\n")[0];
				year_filter.refresh();
				year_filter.set_input(year_filter.df.default);
			},
		});
	},

	// Tô nền mỗi ô mã công theo state màu server đã tính sẵn (`_state_<day>`). Thuần hiển thị.
	formatter: function (value, row, column, data, default_formatter) {
		const html = default_formatter(value, row, column, data);
		const fieldname = (column && column.fieldname) || "";
		// Cột chủ đạo "Tổng công" — in đậm cho dễ nhìn (thuần hiển thị)
		if (fieldname === "tong_cong") {
			return `<b>${html}</b>`;
		}
		if (!fieldname.startsWith("day_")) return html;

		const day = fieldname.slice(4);
		const state = data && data["_state_" + day];
		const styles = frappe.query_reports["Monthly Attendance Report"]._state_styles;
		if (!state || !styles || !styles[state]) return html;

		const s = styles[state];
		const dark = is_dark_theme();
		const bg = dark ? s.bg_dark : s.bg;
		const fg = dark ? s.fg_dark : s.fg;
		const text = value == null ? "" : frappe.utils.escape_html(String(value));
		// negative margin để nền phủ kín ô (bù padding mặc định của datatable)
		return `<div style="background:${bg};color:${fg};font-weight:600;margin:-5px -8px;padding:5px 8px;text-align:center;">${text}</div>`;
	},
};

// Hộp thoại xuất báo cáo. Excel đi đường riêng của Miyano (có màu + khối chú thích dạng lưới);
// CSV giữ nguyên đường `export_query` của Frappe để không mất năng lực nào.
function vn_export_dialog(report) {
	const d = new frappe.ui.Dialog({
		title: __("Xuất báo cáo"),
		fields: [
			{
				fieldname: "file_format",
				label: __("Định dạng"),
				fieldtype: "Select",
				options: [
					{ value: "Excel", label: __("Excel — có màu, kèm chú thích") },
					{ value: "CSV", label: __("CSV — dữ liệu thô") },
				],
				default: "Excel",
				reqd: 1,
			},
			{
				fieldtype: "Section Break",
				label: __("Khối trình ký"),
				depends_on: "eval:doc.file_format=='Excel'",
			},
			{
				fieldname: "prepared_by",
				label: __("Người lập"),
				fieldtype: "Data",
				description: __("Để trống = tên người đang đăng nhập"),
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "approved_by",
				label: __("Người duyệt"),
				fieldtype: "Data",
				description: __("Để trống = chỉ in chức danh, ký tên tay"),
			},
		],
		primary_action_label: __("Tải về"),
		primary_action: ({ file_format, prepared_by, approved_by }) => {
			d.hide();
			report.make_access_log("Export", file_format);

			const filters = report.get_filter_values(true);
			const visible_idx = report.datatable?.bodyRenderer.visibleRowIndices || [];
			// dòng chú thích cuối bảng nằm ngoài vùng datatable đếm — bù lại như Frappe vẫn làm
			if (visible_idx.length + 1 === report.data?.length)
				visible_idx.push(visible_idx.length);

			if (file_format === "Excel") {
				open_url_post(frappe.request.url, {
					cmd: "hrms.hr.attendance_xlsx.download",
					filters,
					visible_idx,
					prepared_by: prepared_by || "",
					approved_by: approved_by || "",
				});
			} else {
				open_url_post(frappe.request.url, {
					cmd: "frappe.desk.query_report.export_query",
					report_name: report.report_name,
					file_format_type: "CSV",
					filters,
					visible_idx,
				});
			}
		},
	});
	d.show();
}

function is_dark_theme() {
	const t = document.documentElement.getAttribute("data-theme");
	if (t === "dark") return true;
	if (t === "light") return false;
	// "automatic" hoặc không đặt → theo thiết lập hệ điều hành
	return !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
}
