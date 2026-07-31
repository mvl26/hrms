# Miyano HR — bóc lớp vỏ Frappe HR: Kế hoạch thực thi

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chuyển repo từ bản tuỳ biến của Frappe HR thành **Miyano HR** — sản phẩm nội bộ mang thương hiệu Miyano, không còn dấu vết GPL, `© Frappe Technologies`, hay thương hiệu "Frappe HR" nào trong code, hình ảnh và tài liệu.

**Architecture:** Phân loại từng file theo commit nhập thượng nguồn `3078af3` — file Miyano tự viết được ghi công lại cho đúng, file thượng nguồn bị xoá header. Đổi thương hiệu tập trung ở `hooks.py` rồi lan ra các SPA. Hình ảnh sinh lại toàn bộ từ logo Miyano bằng PIL. Mọi thay đổi là comment / chuỗi hiển thị / tài nguyên tĩnh, trừ Task 4 (gỡ regional) là phần duy nhất động vào hành vi.

**Tech Stack:** Python 3.12 + PIL 10.2.0, git, ruff (qua pre-commit), Frappe v15 bench.

**Spec:** [`docs/superpowers/specs/2026-07-31-miyano-rebrand-delicense-design.md`](../specs/2026-07-31-miyano-rebrand-delicense-design.md)

## Global Constraints

- **Thư mục làm việc:** chạy mọi lệnh `bench` từ `/home/miyano/frappe-bench`; lệnh `git`/`pre-commit` từ `/home/miyano/frappe-bench/apps/hrms`.
- **Nhánh:** `feat/skip-attendance-diag`. Mỗi task một commit, `git revert`-được.
- **Stage có chọn lọc:** `git add <đường dẫn cụ thể>`, **không bao giờ** `git add -A` — working tree hay có việc dở dang.
- **Conventional Commits**, scope `(hr)`. Thông điệp commit viết **không dấu** (tránh lỗi encoding hook).
- **Định dạng:** ruff — **tab**, nháy kép, dài dòng 110, py310.
- **TUYỆT ĐỐI KHÔNG** chạy `bench --site miyano run-tests` — nó ghi thẳng vào dữ liệu HR/lương thật. Chỉ dùng harness rollback.
- **Không đổi:** `app_name = "hrms"`, thư mục `hrms/`, mọi `import frappe`, mọi tên doctype.
- **Không đụng:** `frappe-ui/` (git submodule), `node_modules/`, `hrms/public/frontend/`, `hrms/public/roster/` (thư mục build sinh tự động).
- **Tên mới:** `Miyano HR`. Đơn vị: `Miyano Việt Nam`. Email: `info@miyano.com.vn`.
- **Ranh giới phân loại file:** commit `3078af3` (bản nhập thượng nguồn).
- **Mốc test đối chiếu:** 190 test / 0 fail / 9 error (không gồm `business_trip`) — 9 error là nhiễu `_Test Company`/WFC có sẵn từ trước, không phải do các thay đổi này.

---

### Task 1: Bóc header bản quyền khỏi 521 file

**Files:**
- Create: `/tmp/claude-1000/-home-miyano-frappe-bench-apps-hrms/a0147703-b768-441c-941c-e48eacc32705/scratchpad/strip_headers.py` (script một lần, **không** commit vào repo)
- Create: `/tmp/claude-1000/-home-miyano-frappe-bench-apps-hrms/a0147703-b768-441c-941c-e48eacc32705/scratchpad/verify_clean.sh` (script kiểm chứng, **không** commit)
- Modify: 516 file `.py`/`.js`/`.ts`/`.vue` + `package.json`

**Interfaces:**
- Consumes: không có (task đầu tiên)
- Produces: repo không còn chuỗi `Frappe Technologies` / `GNU General Public` trong file code. Task 6 xử lý nốt 4 file `.md` còn sót.

**Bối cảnh đã kiểm chứng — dùng làm dữ kiện, không cần đo lại:**
- Mọi dòng Copyright/license đều nằm trong **5 dòng đầu** file, không ngoại lệ.
- **Không tồn tại file `license.txt`** nào trong repo → mọi dòng "See license.txt" đã là con trỏ chết.
- Biến thể dòng Copyright (đã liệt kê đủ): `Frappe Technologies Pvt. Ltd. and Contributors` (213), `... and contributors` (151), bản `//` (121 + 26), `... and Contributors and Contributors` (9), `Frappe and Contributors` (8), `... and Contributors and contributors` (3), một dòng bị nhân đôi dấu `# #` (1).
- Biến thể dòng license: `For license information, please see license.txt` (174 `#` + 125 `//`), `See license.txt` (130), `License: GNU General Public License v3. See license.txt` (80 `#` + 21 `//`), `MIT License. See license.txt` (2 + 2), một dòng `# #` nhân đôi.

- [ ] **Step 1: Viết script kiểm chứng (đây là "test" của task này)**

Tạo `/tmp/claude-1000/-home-miyano-frappe-bench-apps-hrms/a0147703-b768-441c-941c-e48eacc32705/scratchpad/verify_clean.sh`:

```bash
#!/usr/bin/env bash
# Kiem chung: repo khong con dau vet ban quyen Frappe trong file code.
cd /home/miyano/frappe-bench/apps/hrms || exit 1

fail=0
check() {  # $1 = nhan, $2 = so ket qua mong doi, $3... = lenh
	local label="$1" want="$2"; shift 2
	local got; got=$("$@" | wc -l)
	if [ "$got" -eq "$want" ]; then
		echo "PASS  $label (=$got)"
	else
		echo "FAIL  $label: mong doi $want, thuc te $got"; fail=1
	fi
}

check "khong con 'Frappe Technologies' trong code" 0 \
	git grep -l "Frappe Technologies" -- '*.py' '*.js' '*.ts' '*.vue'
check "khong con 'GNU General Public' trong code" 0 \
	git grep -li "GNU General Public" -- '*.py' '*.js' '*.ts' '*.vue'
check "khong con 'license.txt' trong code" 0 \
	git grep -l "license\.txt" -- '*.py' '*.js' '*.ts' '*.vue'
check "83 file Miyano co ghi cong dung" 83 \
	git grep -l "Copyright (c) 2026, Miyano" -- '*.py' '*.js' '*.ts' '*.vue'

exit $fail
```

- [ ] **Step 2: Chạy để xác nhận nó FAIL**

```bash
bash /tmp/claude-1000/-home-miyano-frappe-bench-apps-hrms/a0147703-b768-441c-941c-e48eacc32705/scratchpad/verify_clean.sh
```

Kỳ vọng: 4 dòng `FAIL` — lần lượt 516, 98, ~500, 0.

- [ ] **Step 3: Viết script bóc header**

Tạo `/tmp/claude-1000/-home-miyano-frappe-bench-apps-hrms/a0147703-b768-441c-941c-e48eacc32705/scratchpad/strip_headers.py`:

```python
"""Boc header ban quyen: file Miyano viet -> ghi cong Miyano; file thuong nguon -> xoa han."""

import pathlib
import re
import subprocess

ROOT = pathlib.Path("/home/miyano/frappe-bench/apps/hrms")
FORK = "3078af3"
CODE_EXT = {".py", ".js", ".ts", ".vue"}
SCAN_DEPTH = 5  # moi header deu nam trong 5 dong dau - da kiem chung

COPYRIGHT = re.compile(r"^\s*(#|//)\s*#?\s*Copyright \(c\).*Frappe.*$", re.I)
LICENSE = re.compile(
	r"^\s*(#|//)\s*#?\s*(License:.*|For license information.*|See license\.txt.*|MIT License\..*)$",
	re.I,
)
MIYANO = {"#": "# Copyright (c) 2026, Miyano Việt Nam.\n", "//": "// Copyright (c) 2026, Miyano Việt Nam.\n"}


def git(*args: str) -> list[str]:
	out = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True)
	return out.stdout.splitlines()


upstream = set(git("ls-tree", "-r", "--name-only", FORK))
tracked = git("ls-files")

touched: list[str] = []  # de stage chinh xac, khong dung `git add -u`
stripped = tagged = 0
for rel in tracked:
	path = ROOT / rel
	if path.suffix not in CODE_EXT or not path.is_file():
		continue
	lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

	start = 1 if lines and lines[0].startswith("#!") else 0
	kept, removed = lines[:start], False
	for i, line in enumerate(lines[start:], start=start):
		if i < start + SCAN_DEPTH and (COPYRIGHT.match(line) or LICENSE.match(line)):
			removed = True
			continue
		kept.append(line)
	if not removed:
		continue

	# Bo dong trong thua o dau khoi con lai, tranh de lai khoang ho.
	while len(kept) > start and not kept[start].strip():
		del kept[start]

	if rel not in upstream:  # Miyano tu viet -> ghi cong dung
		comment = "//" if path.suffix in {".js", ".ts"} else "#"
		kept.insert(start, MIYANO[comment])
		tagged += 1
	else:
		stripped += 1

	path.write_text("".join(kept), encoding="utf-8")
	touched.append(rel)

SCRATCH = pathlib.Path(
	"/tmp/claude-1000/-home-miyano-frappe-bench-apps-hrms/a0147703-b768-441c-941c-e48eacc32705/scratchpad"
)
(SCRATCH / "touched.txt").write_text("\n".join(touched) + "\n", encoding="utf-8")

print(f"xoa header thuong nguon: {stripped} file")
print(f"ghi cong Miyano:         {tagged} file")
print(f"tong cong ghi ra touched.txt: {len(touched)} file")
```

**Lưu ý về `.vue`:** file `.vue` dùng comment `//` bên trong `<script>`; regex đã phủ. Nếu con số cuối lệch so với kỳ vọng, kiểm tra `git diff` của riêng nhóm `.vue` trước khi đi tiếp.

- [ ] **Step 4: Chạy thử ở chế độ xem trước**

```bash
cd /home/miyano/frappe-bench/apps/hrms
git stash list   # ghi nho trang thai truoc
python3 /tmp/claude-1000/-home-miyano-frappe-bench-apps-hrms/a0147703-b768-441c-941c-e48eacc32705/scratchpad/strip_headers.py
git diff --stat | tail -5
```

Kỳ vọng: `xoa header thuong nguon: 433 file`, `ghi cong Miyano: 83 file`, tổng 516 file đổi.

Nếu số lệch: **dừng lại**, `git checkout -- .` và điều tra. Không đi tiếp với con số sai.

- [ ] **Step 5: Kiểm tra bằng mắt vài file đại diện**

```bash
head -4 hrms/hr/doctype/attendance/attendance.py           # thuong nguon -> bat dau bang code/docstring
head -4 hrms/hr/doctype/attendance/vn_day_classifier.py    # Miyano -> "# Copyright (c) 2026, Miyano Việt Nam."
head -4 hrms/hr/doctype/attendance/attendance.js           # thuong nguon, file JS
head -6 hrms/setup_vn_defaults.py                          # Miyano, file von khong co header
```

Xác nhận: không file nào bị cụt code, không docstring nào bị hỏng.

- [ ] **Step 6: Sửa `package.json` thủ công**

```json
"description": "Phần mềm Nhân sự & Tiền lương Miyano",
"author": "Miyano Việt Nam",
"license": "UNLICENSED",
```

Xoá luôn khối `"repository"`, `"homepage"`, `"bugs"` (đều trỏ về `github.com/frappe/hrms`).

- [ ] **Step 7: Chạy script kiểm chứng — phải PASS**

```bash
bash /tmp/claude-1000/-home-miyano-frappe-bench-apps-hrms/a0147703-b768-441c-941c-e48eacc32705/scratchpad/verify_clean.sh
```

Kỳ vọng: cả 4 dòng `PASS`.

- [ ] **Step 8: Chạy lint để chắc không hỏng cú pháp**

```bash
cd /home/miyano/frappe-bench/apps/hrms
pre-commit run --all-files
```

Kỳ vọng: pass (ruff có thể tự sửa định dạng — nếu có, `git add` phần nó sửa rồi chạy lại).

- [ ] **Step 9: Commit**

Stage **đúng** danh sách file script đã đụng — không dùng `git add -u`/`-A` vì working tree có thể mang việc dở dang không liên quan:

```bash
cd /home/miyano/frappe-bench/apps/hrms
git add --pathspec-from-file=/tmp/claude-1000/-home-miyano-frappe-bench-apps-hrms/a0147703-b768-441c-941c-e48eacc32705/scratchpad/touched.txt
git add package.json
git status --short | grep -c "^M" # doi chieu: phai la 517 (516 + package.json)
git commit -m "chore(hr): boc header ban quyen Frappe khoi 516 file code

File Miyano tu viet (83) duoc ghi cong dung ten Miyano Viet Nam.
File thuong nguon (433) xoa han header thay vi dan nham ten Miyano.
Repo khong con chuoi GNU General Public hay Frappe Technologies."
```

---

### Task 2: Đổi thương hiệu sang "Miyano HR"

**Files:**
- Modify: `hrms/hooks.py:1-18`, `hrms/install.py`, `hrms/uninstall.py`, `hrms/overrides/company.py:35,48`,
  `hrms/patches/v15_0/check_version_compatibility_with_frappe.py:14-15`, `pyproject.toml`,
  `frontend/index.html:9,12`, `frontend/vite.config.js:27-28`, `frontend/src/views/Login.vue:8`,
  `frontend/src/components/BaseLayout.vue:9`, `frontend/src/components/InstallPrompt.vue:5,28`,
  `roster/src/components/NavBar.vue:6`, `hrms/translations/{bs,de,fa,sv,tr}.csv`

**Interfaces:**
- Consumes: Task 1 đã xong (không xung đột — Task 1 chỉ đụng comment đầu file)
- Produces: `app_title = "Miyano HR"`. Task 3 sẽ đổi đường dẫn logo trong cùng khối `add_to_apps_screen`.

- [ ] **Step 1: Sửa khối metadata trong `hooks.py`**

Thay 8 dòng đầu:

```python
app_name = "hrms"
app_title = "Miyano HR"
app_publisher = "Miyano Việt Nam"
app_description = "Phần mềm Nhân sự & Tiền lương Miyano"
app_email = "info@miyano.com.vn"
app_license = "Proprietary"
required_apps = ["frappe/erpnext"]
```

(`source_link` bị xoá hẳn — nó trỏ `github.com/frappe/hrms`.)

Và trong `add_to_apps_screen`, đổi `"title": "Frappe HR"` → `"title": "Miyano HR"`. **Giữ nguyên** `"logo"` ở bước này — Task 3 lo.

- [ ] **Step 2: Sửa thông báo CLI và log**

| File | Cũ | Mới |
|---|---|---|
| `install.py:8` | `Setting up Frappe HR...` | `Đang cài đặt Miyano HR...` |
| `install.py:16` | `Thank you for installing Frappe HR!` | `Đã cài đặt Miyano HR thành công!` |
| `install.py:21` | `Installation for Frappe HR app failed due to an error.` | `Cài đặt Miyano HR thất bại do lỗi.` |
| `uninstall.py:8` | `Removing customizations created by the Frappe HR app...` | `Đang gỡ tuỳ biến của Miyano HR...` |
| `uninstall.py:14` | `Removing Customizations for Frappe HR failed due to an error.` | `Gỡ tuỳ biến Miyano HR thất bại do lỗi.` |
| `uninstall.py:21` | `Frappe HR app customizations have been removed successfully...` | `Đã gỡ tuỳ biến Miyano HR thành công.` |
| `overrides/company.py:35` | `Unable to delete country fixtures for Frappe HR` | `Unable to delete country fixtures for Miyano HR` |
| `overrides/company.py:48` | `Unable to setup country fixtures for Frappe HR` | `Unable to setup country fixtures for Miyano HR` |

`overrides/company.py` giữ tiếng Anh vì đó là chuỗi `frappe.log_error` cho lập trình viên, không phải người dùng cuối.

- [ ] **Step 3: Sửa thông báo patch tương thích phiên bản**

`hrms/patches/v15_0/check_version_compatibility_with_frappe.py:14-15` — thay `Frappe HR` → `Miyano HR` trong hai câu. Patch này đã chạy xong trên miyano nên chỉ ảnh hưởng cài mới; sửa để chuỗi thống nhất.

- [ ] **Step 4: Sửa `pyproject.toml`**

```toml
description = "Phần mềm Nhân sự & Tiền lương Miyano"
```

Xoá hẳn khối `[project.urls]` (cả 3 URL đều trỏ về Frappe).

- [ ] **Step 5: Sửa hai SPA**

| File | Đổi |
|---|---|
| `frontend/index.html:9` | `<title>Miyano HR</title>` |
| `frontend/index.html:12` | `apple-mobile-web-app-title` content → `Miyano HR` |
| `frontend/vite.config.js:27-28` | `name` + `short_name` → `Miyano HR` |
| `frontend/vite.config.js:29` | `description` → `Nhân sự & chấm công Miyano trong tầm tay` |
| `frontend/src/views/Login.vue:8` | `__("Login to Frappe HR")` → `__("Đăng nhập Miyano HR")` |
| `frontend/src/components/BaseLayout.vue:9` | `__("Frappe HR")` → `__("Miyano HR")` |
| `frontend/src/components/InstallPrompt.vue:5,28` | `__("Install Frappe HR")` → `__("Cài đặt Miyano HR")` |
| `roster/src/components/NavBar.vue:6` | `Frappe HR` → `Miyano HR` |

- [ ] **Step 6: Dọn 5 file dịch**

```bash
cd /home/miyano/frappe-bench/apps/hrms
grep -n "Frappe HR" hrms/translations/{bs,de,fa,sv,tr}.csv
```

Đây là bản dịch cộng đồng của chuỗi `"Frappe HR"` sang tiếng Bosnia/Đức/Ba Tư/Thuỵ Điển/Thổ. Chuỗi nguồn không còn tồn tại nữa → **xoá cả dòng** (8 dòng tổng cộng), không dịch lại.

- [ ] **Step 7: Kiểm chứng**

```bash
cd /home/miyano/frappe-bench/apps/hrms
git grep -i "frappe hr" -- ':!docs' ':!spec' ':!tasks' ':!CLAUDE.md' ':!.github'
```

Kỳ vọng: rỗng. (Tài liệu để Task 6, issue template để Task 5.)

- [ ] **Step 8: Xác nhận app vẫn nạp được**

```bash
cd /home/miyano/frappe-bench
bench --site miyano execute frappe.get_hooks --kwargs '{"hook":"app_title"}'
```

Kỳ vọng: in ra `['Miyano HR']`.

- [ ] **Step 9: Commit**

```bash
cd /home/miyano/frappe-bench/apps/hrms
git add hrms/hooks.py hrms/install.py hrms/uninstall.py hrms/overrides/company.py \
  hrms/patches/v15_0/check_version_compatibility_with_frappe.py pyproject.toml \
  frontend/index.html frontend/vite.config.js frontend/src/views/Login.vue \
  frontend/src/components/BaseLayout.vue frontend/src/components/InstallPrompt.vue \
  roster/src/components/NavBar.vue hrms/translations/
git commit -m "feat(hr): doi thuong hieu app tu Frappe HR sang Miyano HR

Metadata trong hooks.py, thong bao CLI, tieu de PWA, man dang nhap,
thanh dieu huong hai SPA, va pyproject/package. Xoa 8 dong dich cong
dong cua chuoi 'Frappe HR' vi chuoi nguon khong con ton tai.

Giu nguyen app_name=hrms va moi ten doctype - doi la mat du lieu."
```

---

### Task 3: Sinh lại toàn bộ hình ảnh từ logo Miyano

**Files:**
- Create: `hrms/public/images/miyano-hr-logo.png`
- Create: `/tmp/claude-1000/-home-miyano-frappe-bench-apps-hrms/a0147703-b768-441c-941c-e48eacc32705/scratchpad/gen_icons.py` (**không** commit)
- Modify: `hrms/hooks.py:13`, `hrms/subscription_utils.py:124`
- Overwrite: `hrms/public/manifest/{manifest-icon-192.maskable,manifest-icon-512.maskable,favicon-196,apple-icon-180}.png`, 30 file `hrms/public/manifest/apple-splash-*.jpg`, `roster/public/favicon.png`, `frontend/public/favicon.png`
- Delete: `hrms/public/images/frappe-hr-logo.{png,svg}`, `hrms/public/manifest/frappe-hr-logo.svg`
- Track: `frontend/public/logo-miyano.png` (đang untracked)

**Interfaces:**
- Consumes: `app_title` từ Task 2; nguồn ảnh `frontend/public/logo-miyano.png` (768×768 RGBA, chủ sở hữu cung cấp)
- Produces: đường dẫn tài nguyên `/assets/hrms/images/miyano-hr-logo.png`

- [ ] **Step 1: Viết script sinh ảnh**

Tạo `/tmp/claude-1000/-home-miyano-frappe-bench-apps-hrms/a0147703-b768-441c-941c-e48eacc32705/scratchpad/gen_icons.py`:

```python
"""Sinh lai toan bo icon/splash tu logo Miyano."""

import pathlib

from PIL import Image

ROOT = pathlib.Path("/home/miyano/frappe-bench/apps/hrms")
SRC = ROOT / "frontend/public/logo-miyano.png"
MANIFEST = ROOT / "hrms/public/manifest"
WHITE = (255, 255, 255)

logo = Image.open(SRC).convert("RGBA")


def centered(w: int, h: int, ratio: float) -> Image.Image:
	"""Logo can giua tren nen trang, chiem `ratio` canh ngan."""
	canvas = Image.new("RGB", (w, h), WHITE)
	side = max(1, int(min(w, h) * ratio))
	small = logo.resize((side, side), Image.LANCZOS)
	canvas.paste(small, ((w - side) // 2, (h - side) // 2), small)
	return canvas


# 1. Logo desk (app switcher + Navbar Settings) - giu nen trong suot
logo.resize((512, 512), Image.LANCZOS).save(ROOT / "hrms/public/images/miyano-hr-logo.png")

# 2. Icon PWA. Maskable can vung an toan ~80% -> logo chiem 72%.
centered(192, 192, 0.72).save(MANIFEST / "manifest-icon-192.maskable.png")
centered(512, 512, 0.72).save(MANIFEST / "manifest-icon-512.maskable.png")
centered(196, 196, 0.85).save(MANIFEST / "favicon-196.png")
centered(180, 180, 0.85).save(MANIFEST / "apple-icon-180.png")

# 3. Favicon hai SPA
centered(196, 196, 0.85).save(ROOT / "roster/public/favicon.png")
centered(196, 196, 0.85).save(ROOT / "frontend/public/favicon.png")

# 4. 30 splash screen iOS - kich thuoc lay tu chinh ten file
count = 0
for path in sorted(MANIFEST.glob("apple-splash-*.jpg")):
	w, h = (int(x) for x in path.stem.split("-")[2:4])
	centered(w, h, 0.35).save(path, quality=90, optimize=True)
	count += 1

print(f"da sinh lai {count} splash screen + 6 icon + 1 logo desk")
```

- [ ] **Step 2: Chạy script**

```bash
python3 /tmp/claude-1000/-home-miyano-frappe-bench-apps-hrms/a0147703-b768-441c-941c-e48eacc32705/scratchpad/gen_icons.py
```

Kỳ vọng: `da sinh lai 30 splash screen + 6 icon + 1 logo desk`.

- [ ] **Step 3: Kiểm tra bằng mắt**

Mở xem 3 file, xác nhận logo Miyano căn giữa, không méo, không tràn viền:
- `hrms/public/images/miyano-hr-logo.png`
- `hrms/public/manifest/manifest-icon-512.maskable.png`
- `hrms/public/manifest/apple-splash-1170-2532.jpg`

- [ ] **Step 4: Đổi 2 chỗ tham chiếu đường dẫn logo**

```bash
cd /home/miyano/frappe-bench/apps/hrms
grep -n "frappe-hr-logo" hrms/hooks.py hrms/subscription_utils.py
```

Cả hai đổi `/assets/hrms/images/frappe-hr-logo.svg` → `/assets/hrms/images/miyano-hr-logo.png`.
(Nguồn là PNG nên **chỉ dùng PNG** — không dựng SVG giả.)

- [ ] **Step 5: Xoá ảnh Frappe cũ**

```bash
cd /home/miyano/frappe-bench/apps/hrms
git rm hrms/public/images/frappe-hr-logo.png hrms/public/images/frappe-hr-logo.svg \
       hrms/public/manifest/frappe-hr-logo.svg
```

- [ ] **Step 6: Xác nhận không còn tham chiếu chết**

```bash
cd /home/miyano/frappe-bench/apps/hrms
git grep -rn "frappe-hr-logo" -- ':!docs'
```

Kỳ vọng: rỗng.

- [ ] **Step 7: Build lại bundle desk**

```bash
cd /home/miyano/frappe-bench
bench build --app hrms
```

Kỳ vọng: build xong không lỗi.

- [ ] **Step 8: Commit**

```bash
cd /home/miyano/frappe-bench/apps/hrms
git add frontend/public/logo-miyano.png hrms/public/images/ hrms/public/manifest/ \
        roster/public/favicon.png frontend/public/favicon.png \
        hrms/hooks.py hrms/subscription_utils.py
git commit -m "feat(hr): thay toan bo hinh anh Frappe bang logo Miyano

Sinh lai tu frontend/public/logo-miyano.png: logo desk, 4 icon PWA,
2 favicon SPA va 30 splash screen iOS (truoc do mang logo Frappe tren
nen xanh mint). Xoa frappe-hr-logo.{png,svg} va doi 2 cho tham chieu."
```

---

### Task 4: Gỡ regional India + UAE

**Files:**
- Delete: `hrms/regional/india/{setup.py,utils.py,data/salary_components.json}`, `hrms/regional/united_arab_emirates/setup.py`, `hrms/regional/` (cả cây)
- Delete: `hrms/patches/v14_0/create_marginal_relief_field_for_india_localisation.py`, `hrms/patches/v15_0/create_marginal_relief_field_for_india_localisation.py`
- Modify: `hrms/hooks.py:324-330`, `hrms/patches.txt:33,35`, `hrms/payroll/doctype/salary_slip/test_salary_slip.py:1945`, `hrms/payroll/doctype/gratuity/test_gratuity.py:247`

**Interfaces:**
- Consumes: `hooks.py` đã sửa ở Task 2 (khối metadata, khác khối `regional_overrides`)
- Produces: không còn `hrms.regional` — 3 decorator `@erpnext.allow_regional` trong `hr/utils.py` chạy nhánh mặc định

**Đã kiểm chứng an toàn (dữ kiện, không cần đo lại):**
- Cả hai patch `create_marginal_relief_field_for_india_localisation` (v14 + v15) **đã có trong Patch Log của site miyano** → không bao giờ chạy lại.
- `run_regional_setup` tại `hrms/overrides/company.py:29-32` bọc try/except cho module thiếu.
- Công ty của Miyano ở Việt Nam → `run_regional_setup("Vietnam")` chưa từng chạm tới nhánh India/UAE.

- [ ] **Step 1: Xác nhận lại patch đã nằm trong Patch Log**

```bash
cd /home/miyano/frappe-bench
bench --site miyano execute frappe.client.get_list --kwargs '{"doctype":"Patch Log","filters":{"patch":["like","%marginal_relief%"]},"fields":["patch"],"limit_page_length":0}'
```

Kỳ vọng: có cả `v14_0` lẫn `v15_0`. **Nếu thiếu → dừng, không gỡ patch.**

- [ ] **Step 2: Xoá module regional và 2 patch**

```bash
cd /home/miyano/frappe-bench/apps/hrms
git rm -r hrms/regional
git rm hrms/patches/v14_0/create_marginal_relief_field_for_india_localisation.py \
       hrms/patches/v15_0/create_marginal_relief_field_for_india_localisation.py
```

- [ ] **Step 3: Gỡ khối `regional_overrides` khỏi `hooks.py`**

Xoá trọn 7 dòng `hooks.py:324-330`:

```python
regional_overrides = {
	"India": {
		"hrms.hr.utils.calculate_annual_eligible_hra_exemption": "hrms.regional.india.utils.calculate_annual_eligible_hra_exemption",
		"hrms.hr.utils.calculate_hra_exemption_for_period": "hrms.regional.india.utils.calculate_hra_exemption_for_period",
		"hrms.hr.utils.calculate_tax_with_marginal_relief": "hrms.regional.india.utils.calculate_tax_with_marginal_relief",
	},
}
```

**Giữ nguyên** 3 decorator `@erpnext.allow_regional` trong `hrms/hr/utils.py:642,649,656` — không có override thì chúng chạy nhánh mặc định, đúng như VN cần.

- [ ] **Step 4: Gỡ 2 dòng khỏi `patches.txt`**

Xoá dòng 33 và 35:
```
hrms.patches.v15_0.create_marginal_relief_field_for_india_localisation
hrms.patches.v14_0.create_marginal_relief_field_for_india_localisation
```

- [ ] **Step 5: Gỡ 2 test thượng nguồn phụ thuộc regional**

```bash
cd /home/miyano/frappe-bench/apps/hrms
sed -n '1940,1960p' hrms/payroll/doctype/salary_slip/test_salary_slip.py
sed -n '240,260p' hrms/payroll/doctype/gratuity/test_gratuity.py
```

Xoá trọn hàm test chứa `from hrms.regional.india.setup import setup` (trong `test_salary_slip.py`) và hàm chứa `from hrms.regional.united_arab_emirates.setup import setup` (trong `test_gratuity.py`) — đó là test cho localisation Ấn Độ / UAE, không còn đối tượng để kiểm.

- [ ] **Step 6: Xác nhận không còn tham chiếu chết**

```bash
cd /home/miyano/frappe-bench/apps/hrms
git grep -rn "hrms.regional\|hrms\.regional\|marginal_relief" -- ':!docs' ':!spec' ':!tasks'
```

Kỳ vọng: rỗng. Nếu còn `create_marginal_relief_field` trong doctype JSON (custom field), để nguyên — trường đã tồn tại trên site, gỡ trường là data migration cần ký duyệt riêng.

- [ ] **Step 7: Xác nhận app vẫn nạp và migrate khô vẫn chạy**

```bash
cd /home/miyano/frappe-bench
bench --site miyano execute frappe.get_hooks --kwargs '{"hook":"regional_overrides"}'
```

Kỳ vọng: `{}` hoặc rỗng, không traceback.

- [ ] **Step 8: Chạy lint**

```bash
cd /home/miyano/frappe-bench/apps/hrms && pre-commit run --all-files
```

- [ ] **Step 9: Commit**

```bash
cd /home/miyano/frappe-bench/apps/hrms
git add -u hrms/regional hrms/patches hrms/patches.txt hrms/hooks.py \
  hrms/payroll/doctype/salary_slip/test_salary_slip.py \
  hrms/payroll/doctype/gratuity/test_gratuity.py
git commit -m "refactor(hr): go regional India va UAE khoi app

Mien tru HRA va thue An Do khong ap dung cho Miyano (cong ty Viet Nam).
Go hrms/regional/, khoi regional_overrides, 2 patch marginal_relief
(da nam trong Patch Log nen khong chay lai) va 2 test thuong nguon
phu thuoc chung.

Giu 3 decorator @erpnext.allow_regional - khong co override thi chung
chay nhanh mac dinh, dung nhu VN can."
```

---

### Task 5: Dọn chú thích thừa và hạ tầng dự án công khai

**Files:**
- Modify: `hrms/hooks.py` (24 dòng code bị comment + tiêu đề mục rỗng)
- Delete: `.github/ISSUE_TEMPLATE/{bug_report.yaml,feature_request.yaml,config.yml}`

**Interfaces:**
- Consumes: `hooks.py` sau Task 2 + Task 4
- Produces: `hooks.py` chỉ còn cấu hình đang thật sự dùng

- [ ] **Step 1: Liệt kê chính xác các dòng sẽ xoá**

```bash
cd /home/miyano/frappe-bench/apps/hrms
grep -nE "^\s*#\s*[a-z_]+\s*=" hrms/hooks.py
```

Đây là 24 dòng code bị comment, kế thừa nguyên si từ template scaffold `bench new-app` của Frappe — chưa từng được bật. Ví dụ: `# app_include_css = ...`, `# webform_include_js = ...`, `# doctype_tree_js = ...`, `# before_install = ...`, `# notification_config = ...`, `# permission_query_conditions = {...}`.

- [ ] **Step 2: Xoá chúng cùng tiêu đề mục đã rỗng**

Xoá 24 dòng trên. Sau đó xoá luôn các tiêu đề mục không còn nội dung — ví dụ khối:

```python
# Generators
# ----------
```

**Giữ lại** tiêu đề của những mục vẫn còn cấu hình thật (`# Installation`, `# Permissions` nếu bên dưới còn khai báo đang dùng). Nguyên tắc: một tiêu đề chỉ bị xoá khi mọi thứ dưới nó cho tới tiêu đề kế tiếp đều đã biến mất.

- [ ] **Step 3: Xác nhận `hooks.py` vẫn hợp lệ về cú pháp**

```bash
cd /home/miyano/frappe-bench/apps/hrms
python3 -c "import ast; ast.parse(open('hrms/hooks.py').read()); print('cu phap OK')"
```

- [ ] **Step 4: So sánh danh sách hook trước/sau — phải giống hệt**

**Không dùng `git stash`** — working tree có thể mang việc dở dang. Đọc thẳng bản cũ từ git và so hai không gian tên:

```python
# chay: python3 - <<'EOF'   (tu /home/miyano/frappe-bench/apps/hrms)
import subprocess

old_src = subprocess.run(
	["git", "show", "HEAD:hrms/hooks.py"], capture_output=True, text=True, check=True
).stdout
new_src = open("hrms/hooks.py", encoding="utf-8").read()

old_ns, new_ns = {}, {}
exec(compile(old_src, "hooks_old", "exec"), old_ns)
exec(compile(new_src, "hooks_new", "exec"), new_ns)

clean = lambda ns: {k: v for k, v in ns.items() if not k.startswith("__")}
old, new = clean(old_ns), clean(new_ns)

# Task 2 doi metadata thuong hieu; Task 4 go regional_overrides. Ngoai ra phai giong het.
expected = {"app_title", "app_publisher", "app_description", "app_email", "app_license", "source_link", "regional_overrides", "add_to_apps_screen"}
diff = {k for k in set(old) | set(new) if old.get(k) != new.get(k)}
extra = diff - expected

print("khac biet:", sorted(diff))
print("NGOAI DU KIEN:", sorted(extra) if extra else "khong co - DAT")
assert not extra, f"comment bi xoa da lam doi hook: {extra}"
EOF
```

Kỳ vọng: `NGOAI DU KIEN: khong co - DAT`. Xoá comment không được phép làm đổi bất kỳ hook nào ngoài các khoá đã cố ý sửa ở Task 2 và 4.

- [ ] **Step 5: Xoá thư mục issue template**

```bash
cd /home/miyano/frappe-bench/apps/hrms
git rm -r .github/ISSUE_TEMPLATE
```

Ba file này trỏ về issue tracker công khai và nhóm Telegram của Frappe HR — vô nghĩa với app nội bộ.

- [ ] **Step 6: Commit**

```bash
cd /home/miyano/frappe-bench/apps/hrms
git add hrms/hooks.py && git add -u .github
git commit -m "chore(hr): don comment chet va ha tang du an cong khai

Xoa 24 dong code bi comment ke thua tu template scaffold Frappe
(chua tung duoc bat) cung cac tieu de muc da rong. Xoa
.github/ISSUE_TEMPLATE tro ve issue tracker + Telegram cua Frappe HR.

Da doi chieu doc_events truoc/sau: khong doi."
```

---

### Task 6: Cập nhật tài liệu

**Files:**
- Modify: `CLAUDE.md` (phần "What this project is" + mọi chỗ nói Frappe HR như thượng nguồn)
- Modify: `docs/superpowers/plans/2026-06-30-attendance-working-hours-dashboard.md`,
  `docs/superpowers/specs/2026-06-30-attendance-working-hours-dashboard-design.md`,
  `tasks/plan-auto-morning-afternoon.md`, `tasks/plan-vn-holiday-and-symbol.md`,
  `docs/SPEC.md`, `docs/audit-roadmap-2026-07-16.md`, `CODE_OF_CONDUCT.md`

**Interfaces:**
- Consumes: mọi task trước (tài liệu phải mô tả trạng thái cuối)
- Produces: không còn tham chiếu tài liệu tới Frappe HR như sản phẩm

**Nguyên tắc phân biệt — áp dụng cho từng lần khớp:**
- Nói về **Frappe HR** (sản phẩm / thượng nguồn / dự án mã nguồn mở) → sửa hoặc xoá.
- Nói về **Frappe Framework** (`frappe.db`, doctype, hooks, `bench`, `frappe-ui`, ERPNext) → **giữ nguyên**. Đó là mô tả kỹ thuật đúng; xoá đi thành sai và làm hỏng tài liệu cho người sau.

- [ ] **Step 1: Viết lại đoạn mở đầu `CLAUDE.md`**

Thay câu hiện tại:
> This repo is the **in-house customization and deployment of Frappe HR (HRMS) v15 for one company: Miyano.** ... it starts from upstream Frappe HR and layers Miyano's Vietnamese HR / timekeeping / payroll rules on top.

bằng:
> This repo is **Miyano HR — Miyano Việt Nam's in-house HR, timekeeping and payroll system.** It is private software for one deployment: not open source, not a product for resale. It runs on the Frappe Framework + ERPNext (v15).

**Gỡ hẳn** nguyên tắc "Stay upstream-mergeable" (chủ sở hữu đã quyết: Miyano tự bảo trì từ nay, không còn theo thượng nguồn). Thay bằng nguyên tắc thay thế:

> **Miyano tự bảo trì:** repo này không còn theo thượng nguồn. Thay đổi không cần giữ tương thích merge, nhưng vẫn phải `git revert`-được và đi kèm test. Đổi lại: mọi lỗ hổng bảo mật Frappe HR vá sau này, Miyano phải tự phát hiện và tự vá.

Giữ nguyên phần nói nhánh tích hợp là `version-15` và feature work trên `feat/*`.

- [ ] **Step 2: Sửa 4 file `.md` còn chứa `Frappe Technologies`**

```bash
cd /home/miyano/frappe-bench/apps/hrms
git grep -n "Frappe Technologies" -- '*.md'
```

Hai file trong `tasks/` chứa quy ước cũ: *"Mọi file Python/JS mới mở đầu bằng header bản quyền giống file lân cận: `# Copyright (c) YYYY, Frappe Technologies Pvt. Ltd. and Contributors` + `# License: GNU General Public License v3...`"*. Quy ước này **đã bị thay** — sửa thành:

> Mọi file Python/JS mới mở đầu bằng `# Copyright (c) 2026, Miyano Việt Nam.` (JS dùng `//`).

- [ ] **Step 3: Rà toàn bộ tài liệu còn nhắc Frappe HR**

```bash
cd /home/miyano/frappe-bench/apps/hrms
git grep -in "frappe hr" -- '*.md'
```

Xử lý từng chỗ theo nguyên tắc phân biệt ở trên.

- [ ] **Step 4: Xoá `CODE_OF_CONDUCT.md`**

```bash
cd /home/miyano/frappe-bench/apps/hrms
git rm CODE_OF_CONDUCT.md
```

Quy tắc ứng xử cộng đồng mã nguồn mở của Frappe, trỏ về kênh liên hệ của họ. App nội bộ không có cộng đồng đóng góp bên ngoài (chủ sở hữu đã quyết xoá, nhất quán với việc xoá issue template ở Task 5).

- [ ] **Step 5: Kiểm chứng toàn repo**

```bash
cd /home/miyano/frappe-bench/apps/hrms
git grep -i "GNU General Public"; git grep "Frappe Technologies"; git grep -i "Frappe HR"
```

Kỳ vọng: cả ba đều rỗng. Ngoại lệ được phép duy nhất: chính spec/plan này mô tả công việc bóc tách (chúng phải nhắc tên cũ để có nghĩa) — nếu vướng, dùng `':!docs/superpowers'` khi rà.

- [ ] **Step 6: Commit**

```bash
cd /home/miyano/frappe-bench/apps/hrms
git add CLAUDE.md docs/ tasks/ spec/
git commit -m "docs(hr): cap nhat tai lieu theo thuong hieu Miyano HR

Dinh nghia lai repo trong CLAUDE.md: san pham noi bo cua Miyano chay
tren Frappe Framework, khong con la ban tuy bien cua Frappe HR. Cap
nhat quy uoc header ban quyen trong tasks/.

Giu nguyen moi cho noi ve Frappe Framework (frappe.db, doctype, hooks,
bench) - do la mo ta ky thuat dung."
```

---

### Task 7: Kiểm chứng toàn bộ + cổng bất biến payroll

**Files:**
- Create: `/tmp/claude-1000/-home-miyano-frappe-bench-apps-hrms/a0147703-b768-441c-941c-e48eacc32705/scratchpad/payroll_invariance.py` (**không** commit)
- Modify: không có (task chỉ kiểm chứng)

**Interfaces:**
- Consumes: toàn bộ Task 1–6
- Produces: bằng chứng cho phép kết luận công việc hoàn tất

- [ ] **Step 1: Rà sạch dấu vết lần cuối**

```bash
cd /home/miyano/frappe-bench/apps/hrms
for pat in "GNU General Public" "Frappe Technologies" "Frappe HR" "frappe-hr-logo" "hrms.regional"; do
	n=$(git grep -i -l "$pat" -- ':!docs/superpowers' | wc -l)
	echo "$n  <- $pat"
done
```

Kỳ vọng: tất cả bằng 0.

- [ ] **Step 2: Lint toàn repo**

```bash
cd /home/miyano/frappe-bench/apps/hrms && pre-commit run --all-files
```

Kỳ vọng: pass.

- [ ] **Step 3: App nạp được, hook nguyên vẹn**

```bash
cd /home/miyano/frappe-bench
bench --site miyano execute frappe.get_hooks --kwargs '{"hook":"scheduler_events"}'
bench --site miyano execute frappe.get_hooks --kwargs '{"hook":"doc_events"}'
bench --site miyano execute frappe.get_hooks --kwargs '{"hook":"override_doctype_class"}'
```

Kỳ vọng: cả ba in ra đầy đủ, không traceback. So sánh bằng mắt với `hooks.py` — đặc biệt `hourly_long → process_auto_attendance_for_all_shifts`.

- [ ] **Step 4: Build lại hai SPA**

```bash
cd /home/miyano/frappe-bench && bench build --app hrms
```

- [ ] **Step 5: Chạy bộ test qua harness rollback**

Dùng harness rollback của dự án (`frappe.flags.in_test = True`, monkeypatch `frappe.db.commit` → no-op, savepoint mỗi test, `frappe.db.rollback()` trong `finally`). **KHÔNG** dùng `bench --site miyano run-tests`.

Kỳ vọng: khớp mốc **190 test / 0 fail / 9 error**, trừ đi các test đã xoá ở Task 4 (localisation Ấn Độ + gratuity UAE). 9 error là nhiễu `_Test Company`/WFC có sẵn từ trước.

Nếu số fail > 0: **dừng**, điều tra bằng superpowers:systematic-debugging trước khi đi tiếp.

- [ ] **Step 6: Cổng bất biến payroll**

Đây là cổng bắt buộc của dự án. Toàn bộ thay đổi ở Task 1–3, 5–6 là comment / chuỗi / ảnh nên **về nguyên tắc không thể** chạm payroll; Task 4 gỡ code Ấn Độ/UAE mà công ty VN chưa từng gọi. Bước này chứng minh điều đó bằng số:

```python
# /tmp/claude-1000/-home-miyano-frappe-bench-apps-hrms/a0147703-b768-441c-941c-e48eacc32705/scratchpad/payroll_invariance.py — chay qua: bench --site miyano console
import frappe

rows = frappe.get_all(
	"Salary Slip",
	filters={"docstatus": 1},
	fields=["name", "employee", "start_date", "payment_days", "absent_days", "leave_without_pay", "total_working_days"],
	order_by="name",
	limit_page_length=0,
)
print(f"{len(rows)} phieu luong da nop")
for r in rows:
	print(r.name, r.payment_days, r.absent_days, r.leave_without_pay, r.total_working_days, sep="\t")
```

Chạy **trước** khi bắt đầu Task 1 (lưu ra `/tmp/claude-1000/-home-miyano-frappe-bench-apps-hrms/a0147703-b768-441c-941c-e48eacc32705/scratchpad/payroll_before.txt`) và **lại sau** Task 6 (`payroll_after.txt`), rồi:

```bash
diff /tmp/claude-1000/-home-miyano-frappe-bench-apps-hrms/a0147703-b768-441c-941c-e48eacc32705/scratchpad/payroll_before.txt /tmp/claude-1000/-home-miyano-frappe-bench-apps-hrms/a0147703-b768-441c-941c-e48eacc32705/scratchpad/payroll_after.txt && echo "PAYROLL BAT BIEN"
```

Kỳ vọng: không khác biệt.

> **Nếu quên chụp mốc trước:** không suy đoán. Dùng `git stash` để về trạng thái trước, chụp, rồi `git stash pop`.

- [ ] **Step 7: Báo cáo trung thực**

Tổng hợp cho chủ sở hữu: số file đã đổi mỗi task, kết quả 5 lệnh rà ở Step 1, kết quả lint, số test pass/fail/error so mốc, và kết quả diff payroll. Nêu rõ **mọi** bước bị bỏ qua hoặc thất bại — không tuyên bố hoàn tất khi chưa chạy đủ.

- [ ] **Step 8: Xác nhận trực quan trên trình duyệt (cần con người)**

Nhờ chủ sở hữu kiểm tra `http://miyano:8080/hrms` (hoặc site thật sau khi khởi động lại app):
- App switcher hiện "Miyano HR" với logo Miyano
- Màn đăng nhập PWA hiện "Đăng nhập Miyano HR"
- Favicon là logo Miyano

> **Lưu ý triển khai:** `miyano` là PROD chạy supervisor + `gunicorn --preload`. Đổi `hooks.py` cần **khởi động lại app** mới có hiệu lực, và Claude không tự khởi động lại được — phải nhờ chủ sở hữu.

---

## Ghi chú cho người thực thi

**Thứ tự bắt buộc:** Task 1 → 7 theo đúng số. Task 2, 4, 5 đều sửa `hooks.py` nên chạy song song sẽ xung đột.

**Chụp mốc payroll TRƯỚC khi bắt đầu Task 1** (xem Task 7 Step 6) — quên là phải `git stash` mới lấy lại được.

**Hai quyết định đã chốt với chủ sở hữu (2026-07-31):**
1. **Gỡ** nguyên tắc "stay upstream-mergeable" — Miyano tự bảo trì, không còn theo thượng nguồn. Hệ quả đã được nêu và chấp nhận: mọi bản vá bảo mật Frappe HR sau này Miyano phải tự phát hiện và tự vá.
2. **Xoá** `CODE_OF_CONDUCT.md`.

**Nếu một task hỏng giữa chừng:** `git checkout -- .` để về mốc sạch của task đó (các task trước đã commit nên an toàn), rồi điều tra. Không chồng sửa chữa lên trạng thái nửa vời.
