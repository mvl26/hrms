import click

from hrms.setup import before_uninstall as remove_custom_fields


def before_uninstall():
	try:
		print("Đang gỡ tuỳ biến của Miyano HR...")
		remove_custom_fields()

	except Exception as e:
		click.secho(
			"Gỡ tuỳ biến Miyano HR thất bại do lỗi."
			" Vui lòng thử lại hoặc"
			" báo cho bộ phận CNTT (info@miyano.com.vn) nếu chưa khắc phục được.",
			fg="bright_red",
		)
		raise e

	click.secho("Đã gỡ tuỳ biến Miyano HR thành công.", fg="green")
