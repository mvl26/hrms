import click

from hrms.setup import after_install as setup


def after_install():
	try:
		print("Đang cài đặt Miyano HR...")
		setup()

		# Mặc định nội bộ: Công Tác workflow + COO role + fixture master-data integrity check.
		from hrms.setup_vn_defaults import ensure_defaults

		ensure_defaults()

		click.secho("Đã cài đặt Miyano HR thành công!", fg="green")

	except Exception as e:
		click.secho(
			"Cài đặt Miyano HR thất bại do lỗi."
			" Vui lòng thử cài lại hoặc"
			" báo cho bộ phận CNTT (info@miyano.com.vn) nếu chưa khắc phục được.",
			fg="bright_red",
		)
		raise e
