# Miyano HR — bóc lớp vỏ Frappe HR

**Ngày:** 2026-07-31
**Nhánh:** `feat/skip-attendance-diag`
**Trạng thái:** thiết kế đã duyệt, chờ lập kế hoạch thực thi

## 1. Mục tiêu

Chuyển repo từ "bản tuỳ biến nội bộ của Frappe HR" thành **Miyano HR** — sản phẩm nội bộ mang thương hiệu Miyano, không công khai. Sau khi xong:

- `git grep -i "GNU General Public"` → 0 kết quả
- `git grep "Frappe Technologies"` → 0 kết quả
- `git grep -i "Frappe HR"` → 0 kết quả
- Không còn hình ảnh, logo, hay hạ tầng dự án mã nguồn mở nào của Frappe

## 2. Bối cảnh & quyết định đã chốt

Repo có 1.631 file: **1.453 file đến từ bản nhập thượng nguồn** (commit `3078af3`), **194 file do Miyano thêm**. 521 file mang `© Frappe Technologies`, 103 file mang header GPL v3.

Ba điểm đã được nêu với chủ sở hữu trước khi thiết kế:

1. **App không phân phối thì GPL không ràng buộc gì.** GPL chỉ phát sinh nghĩa vụ khi conveying. Miyano dùng nội bộ ⇒ không phải công bố mã nguồn. Mục tiêu "không public" đã đạt sẵn, không cần phẫu thuật giấy phép.
2. **Xoá header không đổi giấy phép thực tế** của 1.453 file thượng nguồn. Vô hại khi nằm trong hạ tầng Miyano, nhưng thành rủi ro thật nếu app được chia sẻ, kiểm toán hay bán lại.
3. **Không thể gỡ Frappe khỏi *kỹ thuật*** — app chạy trên Frappe Framework + ERPNext, mọi file đều `import frappe`. Gỡ được là gỡ **thương hiệu Frappe HR**, không phải nền tảng.

Chủ sở hữu đã cân nhắc và chọn gỡ sạch. Quyết định được ghi nhận; thiết kế này thực thi theo.

**Điều chỉnh duy nhất áp dụng:** với 433 file thượng nguồn, header bị **xoá hẳn** thay vì thay bằng `© Miyano`. Kết quả với mục tiêu là giống hệt (repo sạch chữ GPL/Frappe), nhưng không tự dán tên Miyano lên code Miyano không viết — nếu sau này có kiểm toán thì đó là "không ghi gì" chứ không phải "ghi sai".

## 3. Phân loại file — quy tắc khách quan

Ranh giới là commit nhập thượng nguồn `3078af3`, không phán đoán chủ quan:

```bash
comm -13 <(git ls-tree -r --name-only 3078af3 | sort) <(git ls-files | sort)
```

| Nhóm | Số file | Xử lý header |
|---|---|---|
| Miyano tự viết | **83** | `# Copyright (c) 2026, Miyano Việt Nam.` |
| Thượng nguồn | **433** | Xoá hẳn 2 dòng header, không thay gì |
| Không phải code | **5** | Sửa thủ công (`package.json` + 4 `.md`) |

Ví dụ cụ thể — [`vn_day_classifier.py`](../../../hrms/hr/doctype/attendance/vn_day_classifier.py) hiện ghi `© 2026 Frappe Technologies` dù đó là luật chấm công Miyano: đây là ghi công sai theo chiều ngược lại, sửa là đúng bản chất.

## 4. Hạng mục thực thi

### 4.1 Header bản quyền (516 file code + 5 file khác)

Script Python một lần, phân loại theo mục 3, xử lý cả `.py` / `.js` / `.ts` / `.vue`. Không đụng vào bất kỳ dòng code thực thi nào.

### 4.2 Thương hiệu → "Miyano HR"

Gốc là [`hooks.py`](../../../hrms/hooks.py):

| Khoá | Cũ | Mới |
|---|---|---|
| `app_title` | `Frappe HR` | `Miyano HR` |
| `app_publisher` | `Frappe Technologies Pvt. Ltd.` | `Miyano Việt Nam` |
| `app_description` | `Modern HR and Payroll Software` | `Phần mềm Nhân sự & Tiền lương Miyano` |
| `app_email` | `contact@frappe.io` | `info@miyano.com.vn` |
| `app_license` | `GNU General Public License (v3)` | `Proprietary` |
| `source_link` | `github.com/frappe/hrms` | gỡ bỏ |

Kéo theo: `add_to_apps_screen`, tiêu đề PWA (`frontend/index.html`, `frontend/vite.config.js`), `Login.vue`, `BaseLayout.vue`, `InstallPrompt.vue`, `roster/.../NavBar.vue`, thông báo CLI (`install.py`, `uninstall.py`, `overrides/company.py`), thông báo patch tương thích phiên bản, `pyproject.toml`, `package.json`, và 5 file `hrms/translations/*.csv`.

**Giữ nguyên tuyệt đối:** `app_name = "hrms"`, thư mục `hrms/`, `import frappe`, mọi tên doctype. Đổi những cái đó nghĩa là cài lại app và mất dữ liệu.

### 4.3 Hình ảnh

Nguồn: `frontend/public/logo-miyano.png` (768×768 RGBA, chủ sở hữu cung cấp). Sinh lại bằng PIL 10.2.0:

- `hrms/public/images/miyano-hr-logo.png` (desk app switcher, Navbar Settings). Nguồn là PNG nên **chỉ sinh PNG** — hai chỗ tham chiếu hiện trỏ `.svg` sẽ được đổi sang `.png`, không dựng SVG giả.
- 4 icon PWA: `manifest-icon-192.maskable.png`, `manifest-icon-512.maskable.png`, `favicon-196.png`, `apple-icon-180.png`
- **30 file `apple-splash-*.jpg`** — hiện mang logo Frappe trên nền xanh mint; sinh lại: logo Miyano căn giữa trên nền trắng (khớp `theme_color: "#ffffff"` của manifest)
- `frontend/public/favicon.png`, `roster/public/favicon.png`
- Xoá `frappe-hr-logo.{png,svg}` ở cả `public/images/` lẫn `public/manifest/`; cập nhật 2 chỗ tham chiếu (`hooks.py:13`, `subscription_utils.py:124`)

### 4.4 Gỡ regional India + UAE

Đã kiểm chứng an toàn: hai patch `create_marginal_relief_field_for_india_localisation` (v14 + v15) **đã có trong Patch Log của site miyano** nên không bao giờ chạy lại; `run_regional_setup` tại [`company.py:29-32`](../../../hrms/overrides/company.py) bọc try/except cho module thiếu.

Xoá `hrms/regional/` (5 file) ⇒ kéo theo: khối `regional_overrides` (`hooks.py:324-330`), 2 file patch + 2 dòng trong `patches.txt`, và 2 test thượng nguồn import chúng (`test_salary_slip.py:1945`, `test_gratuity.py:247`).

**Giữ nguyên** 3 decorator `@erpnext.allow_regional` trong `hr/utils.py` — không có override thì chúng chạy nhánh mặc định, đúng như VN cần.

### 4.5 Dọn chú thích dư thừa

- `hooks.py`: 24 dòng code bị comment từ template scaffold Frappe (`# app_include_css = ...`, `# webform_include_js = ...`) — chưa từng dùng, xoá cùng các tiêu đề mục rỗng đi kèm.
- Xoá `.github/ISSUE_TEMPLATE/` (3 file) — issue tracker công khai + nhóm Telegram của Frappe HR, vô nghĩa với app nội bộ.

### 4.6 Tài liệu

- `CLAUDE.md`: viết lại phần "What this project is" — hiện định nghĩa repo là "in-house customization of Frappe HR".
- `docs/`, `spec/`, `tasks/`: chỉ sửa chỗ nói về **Frappe HR như sản phẩm/thượng nguồn**. **Giữ nguyên** chỗ nói về **Frappe Framework** (`frappe.db`, doctype, hooks, `bench`) — đó là mô tả kỹ thuật đúng, xoá đi thành sai.

## 5. Ngoài phạm vi

- Đổi `app_name`, tên module, tên doctype — cần cài lại app.
- Gỡ Gratuity và các doctype thượng nguồn khác — chủ sở hữu chọn giữ.
- Viết lại lịch sử git.
- Đụng vào `frappe-ui/` (submodule).

## 6. Kiểm chứng

| Cổng | Lệnh |
|---|---|
| Không còn dấu vết | `git grep -i "GNU General Public\|Frappe Technologies\|Frappe HR"` → rỗng |
| Lint | `pre-commit run --all-files` |
| App nạp được | `bench --site miyano console` → `import hrms` |
| Test | Harness rollback (**không** `run-tests` trên miyano) — so với mốc 190t/0fail/9err |
| Build SPA | `bench build --app hrms` |
| **Bất biến payroll** | `payment_days` / `absent_days` / LWP trước-sau không đổi |

## 7. Rủi ro

| Rủi ro | Mức | Giảm thiểu |
|---|---|---|
| Ghi công sai trên 433 file thượng nguồn | Đã nêu, chủ sở hữu chấp nhận | Xoá header thay vì dán `© Miyano` |
| Regex header ăn nhầm code | Trung bình | Neo vào đầu file, đối chiếu `git diff --stat`, kiểm tra `pre-commit` |
| Gỡ regional làm hỏng migrate | Thấp | Patch đã trong Patch Log; xoá đồng thời khỏi `patches.txt` |
| Đổi `app_title` ảnh hưởng desk | Thấp | Chỉ là nhãn hiển thị, không phải khoá tra cứu |
| Đổi đường dẫn logo làm vỡ ảnh | Thấp | Cập nhật đủ 2 chỗ tham chiếu; kiểm tra trực quan sau `bench build` |
| Splash iOS sai tỉ lệ | Thấp | Sinh đúng 30 kích thước gốc, đối chiếu tên file |

## 8. Thứ tự thực thi

Từng bước một commit, `git revert`-được:

1. Header bản quyền (516 + 5 file)
2. Thương hiệu → Miyano HR
3. Hình ảnh + logo
4. Gỡ regional India/UAE
5. Dọn chú thích thừa + xoá issue template
6. Tài liệu
7. Kiểm chứng toàn bộ + cổng bất biến payroll
