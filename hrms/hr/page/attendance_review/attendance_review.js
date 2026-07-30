// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt
//
// Trang SOÁT CÔNG THÁNG — mắt xích HR thiếu bấy lâu.
//
// Lưới nhân viên x ngày, ô nào đáng ngờ thì tô màu; bấm vào ô để đổi mã công kèm lý do; sửa bao
// nhiêu ô cũng được rồi "Lưu tất cả" một lượt. Mọi thay đổi đi qua đúng một API
// (`apply_corrections_bulk` → `apply_correction`) nên luôn có vết trong Nhật ký điều chỉnh công.

frappe.pages["attendance-review"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Soát công tháng"),
		single_column: true,
	});
	new AttendanceReview(page);
};

class AttendanceReview {
	constructor(page) {
		this.page = page;
		this.pending = new Map(); // attendance -> {attendance, code, reason}
		this.make_filters();
		this.make_actions();
		this.body = $('<div class="attendance-review-body">').appendTo(this.page.main);
		this.inject_styles();
		this.refresh();
	}

	make_filters() {
		const today = frappe.datetime.now_date(true);
		this.month = this.page.add_select(
			__("Tháng"),
			Array.from({ length: 12 }, (_, i) => ({ label: String(i + 1), value: String(i + 1) })),
		);
		this.month.val(String(today.getMonth() + 1));

		this.year = this.page.add_field({
			fieldtype: "Int",
			fieldname: "year",
			label: __("Năm"),
			default: today.getFullYear(),
		});
		this.company = this.page.add_field({
			fieldtype: "Link",
			fieldname: "company",
			label: __("Công ty"),
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		});
		this.department = this.page.add_field({
			fieldtype: "Link",
			fieldname: "department",
			label: __("Phòng ban"),
			options: "Department",
		});

		// nhận bộ lọc khi được mở từ báo cáo bảng công (giữ nguyên kỳ đang xem, không phải chọn lại)
		const ro = frappe.route_options || {};
		if (ro.month) this.month.val(String(ro.month));
		if (ro.year) this.year.set_value(ro.year);
		if (ro.company) this.company.set_value(ro.company);
		if (ro.department) this.department.set_value(ro.department);
		frappe.route_options = null;

		for (const f of [this.year, this.company, this.department]) {
			f.$input.on("change", () => this.refresh());
		}
		this.month.on("change", () => this.refresh());
	}

	make_actions() {
		this.page.set_primary_action(__("Lưu tất cả"), () => this.save_all());
		this.page.set_secondary_action(__("Tải lại"), () => this.refresh());
		// chặng nối của luồng: soát xong thì về báo cáo xem lại, rồi chốt công
		this.page.add_inner_button(__("Về bảng công tháng"), () => this.go_to_report());
		this.page.add_inner_button(__("Chốt công tháng"), () => this.go_to_sheet());
	}

	go_to_report() {
		frappe.route_options = this.filters();
		frappe.set_route("query-report", "Monthly Attendance Report");
	}

	go_to_sheet() {
		const f = this.filters();
		frappe.call({
			method: "hrms.hr.doctype.monthly_attendance_sheet.monthly_attendance_sheet.get_or_create_sheet",
			args: f,
			freeze: true,
			freeze_message: __("Đang mở bảng chốt công..."),
			callback: (r) => {
				if (r.message) frappe.set_route("Form", "Monthly Attendance Sheet", r.message);
			},
		});
	}

	filters() {
		return {
			month: this.month.val(),
			year: this.year.get_value(),
			company: this.company.get_value(),
			department: this.department.get_value() || undefined,
		};
	}

	refresh() {
		this.pending.clear();
		this.update_pending_label();
		frappe
			.call({
				method: "hrms.hr.attendance_review.get_review_grid",
				args: { filters: this.filters() },
			})
			.then((r) => this.render(r.message || { rows: [], flags: {} }));
	}

	render(data) {
		this.data = data;
		if (!data.rows.length) {
			this.body.html(
				`<div class="text-muted p-4">${__("Không có nhân viên nào trong kỳ này.")}</div>`,
			);
			return;
		}

		// vẽ trọn tháng: ngày thiếu bản ghi không có khoá trong `days` nhưng vẫn phải có ô để hiện cờ
		const last = data.days_in_month || 31;
		const days = Array.from({ length: last }, (_, i) => i + 1);

		let html =
			'<div class="table-responsive"><table class="table table-bordered ar-grid"><thead><tr>';
		html += `<th class="ar-emp">${__("Nhân viên")}</th>`;
		for (const d of days) html += `<th>${d}</th>`;
		html += `<th>${__("Tổng công")}</th></tr></thead><tbody>`;

		for (const row of data.rows) {
			const flags = (data.flags || {})[row.employee] || {};
			html += `<tr><td class="ar-emp">${frappe.utils.escape_html(
				row.employee_name || row.employee,
			)}</td>`;
			for (const d of days) {
				const symbol = row.days[d] ?? ""; // rỗng = ngày làm việc chưa có bản ghi công
				const cell_flags = flags[d] || [];
				const name = (row.attendance_names || {})[d];
				const title = cell_flags.map((f) => data.flag_labels[f] || f).join(", ");
				html += `<td class="ar-cell ${cell_flags.length ? "ar-flagged" : ""}"
					data-attendance="${name || ""}" data-day="${d}" data-employee="${row.employee}"
					title="${frappe.utils.escape_html(title)}">${frappe.utils.escape_html(symbol)}</td>`;
			}
			html += `<td class="ar-total">${row.totals["Tổng công"] ?? 0}</td></tr>`;
		}
		html += "</tbody></table></div>";
		this.body.html(html);
		this.body.find(".ar-cell").on("click", (e) => this.edit_cell($(e.currentTarget)));
	}

	edit_cell($cell) {
		const attendance = $cell.data("attendance");
		if (!attendance) {
			frappe.msgprint(__("Ngày này chưa có bản ghi công nên chưa sửa được ở đây."));
			return;
		}

		const d = new frappe.ui.Dialog({
			title: __("Sửa mã công ngày {0}", [$cell.data("day")]),
			fields: [
				{
					fieldtype: "Link",
					fieldname: "code",
					label: __("Mã công mới"),
					options: "Attendance Code",
					reqd: 1,
					default: $cell.text().trim(),
				},
				{
					fieldtype: "Small Text",
					fieldname: "reason",
					label: __("Lý do điều chỉnh"),
					reqd: 1,
					description: __("Bắt buộc — lý do được ghi vào Nhật ký điều chỉnh công."),
				},
			],
			primary_action_label: __("Ghi nhận"),
			primary_action: (values) => {
				this.pending.set(attendance, {
					attendance,
					code: values.code,
					reason: values.reason,
				});
				$cell.text(values.code).addClass("ar-pending");
				this.update_pending_label();
				d.hide();
			},
		});
		d.show();
	}

	update_pending_label() {
		this.page.set_indicator(
			this.pending.size ? __("{0} ô chờ lưu", [this.pending.size]) : __("Chưa có thay đổi"),
			this.pending.size ? "orange" : "gray",
		);
	}

	save_all() {
		if (!this.pending.size) {
			frappe.msgprint(__("Chưa có ô nào được sửa."));
			return;
		}
		frappe
			.call({
				method: "hrms.hr.attendance_review.apply_corrections_bulk",
				args: { corrections: Array.from(this.pending.values()) },
				freeze: true,
				freeze_message: __("Đang lưu điều chỉnh..."),
			})
			.then((r) => {
				const n = (r.message || {}).applied || 0;
				frappe.show_alert({
					message: __("Đã lưu {0} điều chỉnh", [n]),
					indicator: "green",
				});
				this.refresh();
				// soát xong thường là đi tiếp, nên hỏi luôn thay vì bắt tự nhớ đường
				frappe.confirm(
					__("Đã lưu {0} điều chỉnh. Xem lại bảng công tháng bây giờ?", [n]),
					() => this.go_to_report(),
				);
			});
	}

	inject_styles() {
		if (document.getElementById("ar-grid-style")) return;
		$(`<style id="ar-grid-style">
			.ar-grid { font-size: 12px; }
			.ar-grid th, .ar-grid td { text-align: center; padding: 4px; white-space: nowrap; }
			.ar-grid .ar-emp { text-align: left; position: sticky; left: 0; background: var(--fg-color); }
			.ar-cell { cursor: pointer; }
			.ar-cell:hover { outline: 2px solid var(--primary); }
			.ar-flagged { background: var(--bg-red); font-weight: 600; }
			.ar-pending { background: var(--bg-orange); }
			.ar-total { font-weight: 600; }
		</style>`).appendTo(document.head);
	}
}
