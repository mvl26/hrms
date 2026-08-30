// Copyright (c) 2026, Miyano Việt Nam.
frappe.ui.form.on("Work Calendar Settings", {
	refresh(frm) {
		if (!frm.doc.generate_for_year) {
			frm.set_value("generate_for_year", new Date().getFullYear());
		}
		render_preview(frm);
	},

	generate_for_year(frm) {
		render_preview(frm);
	},

	// Sinh lịch phải đi qua server để chính sách và Holiday List không bao giờ lệch nhau.
	generate_button(frm) {
		frm.save().then(() => {
			frappe.call({
				method: "hrms.hr.doctype.work_calendar_settings.work_calendar_settings.generate_holiday_list",
				args: { year: frm.doc.generate_for_year, company: frm.doc.company },
				freeze: true,
				freeze_message: __("Đang sinh Holiday List..."),
				callback(r) {
					if (!r.message) return;
					frappe.msgprint({
						title: __("Xong"),
						indicator: "green",
						message: __("Đã sinh {0}. Mở để kiểm tra ngày nghỉ lễ.", [
							`<a href="/app/holiday-list/${encodeURIComponent(
								r.message,
							)}">${frappe.utils.escape_html(r.message)}</a>`,
						]),
					});
				},
			});
		});
	},
});

// Số ngày công từng tháng, trước và sau khi lưu. Khai một ngày làm bù mà quên khai ngày nghỉ ghép
// đi kèm là im lặng đổi lương cả tháng — bảng này bắt đúng lỗi đó, trước khi HR bấm lưu.
function render_preview(frm) {
	const wrapper = frm.get_field("preview_html");
	if (!wrapper || frm.is_new()) return;

	frm.call("working_days_preview", { year: frm.doc.generate_for_year }).then((r) => {
		const data = r.message;
		if (!data) return;
		const months = Object.keys(data).sort((a, b) => a - b);
		const changed = months.filter((m) => data[m].before !== data[m].after);

		const cells = months
			.map((m) => {
				const { before, after } = data[m];
				const diff = after - before;
				const style = diff ? ' style="background:#fdf1d7;font-weight:600"' : "";
				const note = diff ? ` (${diff > 0 ? "+" : ""}${diff})` : "";
				return `<td${style}>T${m}<br>${after}${note}</td>`;
			})
			.join("");

		const warning = changed.length
			? `<p style="color:#b32626"><b>${__(
					"Số ngày công đổi ở {0} tháng — đây là MẪU SỐ của phiếu lương.",
					[changed.length],
			  )}</b></p>`
			: "";

		wrapper.$wrapper.html(`
			${warning}
			<table class="table table-bordered" style="text-align:center;font-size:12px">
				<tbody><tr>${cells}</tr></tbody>
			</table>
			<p class="text-muted">${__(
				"Ngày làm bù nên nằm cùng tháng với ngày nghỉ ghép nó bù cho, nếu không số ngày công của cả hai tháng đều đổi.",
			)}</p>
		`);
	});
}
