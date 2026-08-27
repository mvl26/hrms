# Copyright (c) 2026, Miyano Việt Nam.
"""Luật vị trí & đặt tên file của repo Miyano HR — nguồn sự thật DUY NHẤT.

Được gọi từ hai chỗ, cố ý dùng chung một bộ luật để không lệch nhau:

    python3 scripts/check_file_placement.py            # quét toàn bộ cây (pre-commit, CI)
    python3 scripts/check_file_placement.py <path>...  # quét vài đường dẫn
    python3 scripts/check_file_placement.py --hook     # PreToolUse của Claude Code, đọc JSON ở stdin

Cố ý gộp cả chế độ hook vào đây thay vì để một shim trong `.claude/hooks/`: shim đó
là file .py nằm ngoài `hrms/`|`scripts/`|`.github/` nên sẽ vi phạm đúng cái luật nó
đang thi hành.

Nguyên tắc chọn luật: CHỈ ép những quy ước repo đang tuân 100%. Một luật báo nhầm
hàng loạt là một luật sẽ bị tắt, và tắt rồi thì nó không bảo vệ được gì nữa. Các quy
ước repo vốn không nhất quán (tên .js/.ts ở frontend, tên file trong thư mục doctype)
thì để skill khuyến nghị, không chặn.
"""

import json
import pathlib
import re
import subprocess
import sys

# Thư mục ở gốc repo đã bị dọn 2026-08-14, không được lập lại (nay là docs/spec, docs/tasks).
RETIRED_ROOT_DIRS = {"spec", "tasks"}

# Thư mục con của một module có thể chứa test nằm cạnh thứ nó kiểm.
# Frappe ràng `test_records.json` theo đúng đường dẫn doctype nên KHÔNG chuyển đi được.
TEST_MAY_SIT_BESIDE = {"doctype", "report", "page"}

# Nơi hợp lệ của mã nguồn Python.
PYTHON_ROOTS = ("hrms/", "scripts/", ".github/")

# Thư mục patch theo phiên bản. `post_install/` là patch upstream cũ đã bị tỉa entry
# khỏi patches.txt (16 file) — miễn trừ, không phải việc của repo này.
VERSIONED_PATCH_DIR = re.compile(r"^v\d")

SNAKE_CASE = re.compile(r"^[a-z_][a-z0-9_]*$")
PASCAL_CASE = re.compile(r"^[A-Z][A-Za-z0-9]*$")
KEBAB_CASE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
PLAN_DOC = re.compile(r"^plan(-[a-z0-9-]+)?$")


def segments(path: str) -> list[str]:
	return [s for s in path.split("/") if s]


def stem(name: str) -> str:
	return name.rsplit(".", 1)[0] if "." in name else name


def is_test_file(name: str) -> bool:
	return name.startswith("test_") and name.endswith(".py")


def sits_beside_what_it_tests(parts: list[str]) -> bool:
	"""hrms/<module>/(doctype|report|page)/<tên>/test_*.py — vị trí Frappe bắt buộc."""
	return len(parts) >= 4 and parts[-3] in TEST_MAY_SIT_BESIDE


def check_path(path: str) -> list[str]:
	"""Trả về danh sách vi phạm của MỘT đường dẫn (tương đối gốc repo). Rỗng = hợp lệ."""
	# removeprefix chứ KHÔNG lstrip("./"): lstrip nhận tập ký tự nên nó ăn luôn dấu chấm
	# của `.github/`, biến thành `github/` rồi báo nhầm là mã nguồn đặt sai chỗ.
	path = path.strip().removeprefix("./")
	parts = segments(path)
	if not parts:
		return []

	if parts[0] in RETIRED_ROOT_DIRS:
		return [f"`{parts[0]}/` ở gốc repo đã bị dọn — tài liệu nay nằm ở `docs/{parts[0]}/`."]

	return check_naming(path, parts) + check_placement(path, parts)


def check_naming(path: str, parts: list[str]) -> list[str]:
	problems = []
	name = parts[-1]

	if " " in path:
		problems.append("tên file/thư mục không được chứa dấu cách.")

	if name.endswith("_test.py"):
		problems.append(
			"test phải đặt tiền tố `test_`, không phải hậu tố `_test.py` — "
			"Frappe chỉ gom file bắt đầu bằng `test_`."
		)
	elif path.endswith(".py") and path.startswith(PYTHON_ROOTS) and not SNAKE_CASE.match(stem(name)):
		problems.append(f"module Python phải là snake_case, không phải `{name}`.")

	if path.endswith(".vue") and not PASCAL_CASE.match(stem(name)):
		problems.append(f"component Vue phải là PascalCase, không phải `{name}`.")

	problems += check_container_dir_naming(parts)
	problems += check_doc_naming(parts)
	return problems


def check_container_dir_naming(parts: list[str]) -> list[str]:
	"""Thư mục đặt tên một doctype/report/page phải là snake_case của tên đó."""
	problems = []
	for i, seg in enumerate(parts[:-1]):
		if seg in TEST_MAY_SIT_BESIDE and i + 1 < len(parts) - 1:
			owner = parts[i + 1]
			if not SNAKE_CASE.match(owner):
				problems.append(f"thư mục `{seg}/{owner}` phải là snake_case.")
	return problems


def check_doc_naming(parts: list[str]) -> list[str]:
	if len(parts) < 3 or parts[0] != "docs" or not parts[-1].endswith(".md"):
		return []
	name = stem(parts[-1])
	if parts[1] == "spec" and not KEBAB_CASE.match(name):
		return [f"spec phải đặt tên kebab-case, không phải `{parts[-1]}`."]
	if parts[1] == "tasks" and not PLAN_DOC.match(name):
		return [f"kế hoạch phải đặt tên `plan-<kebab-case>.md`, không phải `{parts[-1]}`."]
	return []


def suggested_tests_dir(parts: list[str]) -> str:
	"""Thư mục tests/ nên dùng cho một test đang đặt sai chỗ."""
	# Patch không phải là "module có test riêng" — test của patch thuộc về hrms/tests/.
	# Gợi ý `hrms/patches/v15_0/tests/` sẽ đẻ ra một thư mục vô nghĩa.
	if parts[:2] == ["hrms", "patches"]:
		return "hrms/tests/"
	return "/".join(parts[:-1]) + "/tests/"


def check_placement(path: str, parts: list[str]) -> list[str]:
	problems = []
	name = parts[-1]

	if is_test_file(name) and "tests" not in parts[:-1] and not sits_beside_what_it_tests(parts):
		suggested = suggested_tests_dir(parts)
		problems.append(
			f"test không được nằm cạnh mã nguồn — chuyển vào `{suggested}` "
			f"(hoặc để cạnh doctype/report nếu là test của chính nó)."
		)

	if path.endswith(".md") and not is_allowed_markdown(path, parts):
		problems.append("tài liệu phải nằm trong `docs/`.")

	if path.endswith(".py") and not path.startswith(PYTHON_ROOTS):
		problems.append("mã nguồn Python phải nằm trong `hrms/` (hoặc `scripts/`, `.github/`).")

	return problems


def is_allowed_markdown(path: str, parts: list[str]) -> bool:
	if parts[0] == "docs":
		return True
	if parts[-1] == "README.md" or path == "CLAUDE.md":
		return True
	# Skill/agent của Claude Code buộc phải nằm trong .claude/ — công cụ đọc từ đúng đó,
	# dời sang docs/ là hỏng. Luật này tự phát hiện khi hook chặn chính file SKILL.md.
	if parts[0] == ".claude":
		return True
	# Frappe đọc template thông báo từ chính thư mục notification/<tên>/
	return "notification" in parts


def parse_patch_modules(patches_txt: str) -> set[str]:
	"""Các module patch đã khai trong patches.txt (bỏ chú thích, tiêu đề mục, dòng execute:)."""
	modules = set()
	for line in patches_txt.splitlines():
		line = line.split("#", 1)[0].strip()
		if not line or line.startswith("[") or line.startswith("execute:"):
			continue
		modules.add(line)
	return modules


def check_patch_registration(path: str, patch_modules: set[str]) -> list[str]:
	"""Patch không có entry trong patches.txt sẽ không bao giờ chạy — im lặng và vô dụng."""
	parts = segments(path)
	if len(parts) < 4 or parts[:2] != ["hrms", "patches"] or not path.endswith(".py"):
		return []
	if parts[-1] == "__init__.py" or not VERSIONED_PATCH_DIR.match(parts[2]):
		return []
	module = path[: -len(".py")].replace("/", ".")
	if module not in patch_modules:
		return [f"patch thiếu entry trong `hrms/patches.txt` — thêm dòng `{module}`."]
	return []


def check_all(paths, patches_txt: str = "") -> dict[str, list[str]]:
	"""Soi một loạt đường dẫn. Trả về {đường dẫn: [vi phạm]} — rỗng nghĩa là sạch."""
	patch_modules = parse_patch_modules(patches_txt)
	found = {}
	for path in paths:
		problems = check_path(path) + check_patch_registration(path, patch_modules)
		if problems:
			found[path] = problems
	return found


def repo_root() -> pathlib.Path:
	return pathlib.Path(__file__).resolve().parents[1]


def hook_decision(payload: dict, *, root, exists=None) -> str | None:
	"""Thông điệp chặn cho PreToolUse hook, hoặc None nếu cho qua.

	Chỉ chặn lúc TẠO file mới. Sửa file đang sai vị trí thì để yên — rất có thể
	đó chính là lúc đang dọn nó, chặn thì thành ra tự khoá tay mình.
	"""
	if payload.get("tool_name") != "Write":
		return None
	file_path = (payload.get("tool_input") or {}).get("file_path")
	if not file_path:
		return None

	exists = exists or (lambda p: pathlib.Path(p).exists())
	if exists(file_path):
		return None

	try:
		relative = str(pathlib.PurePath(file_path).relative_to(root))
	except ValueError:
		return None  # ngoài repo, không phải việc của luật này

	problems = check_path(relative)
	if not problems:
		return None
	return f"`{relative}` sai cấu trúc repo:\n" + "\n".join(f"  → {p}" for p in problems)


def run_as_hook() -> int:
	"""PreToolUse: mã thoát 2 = chặn, stderr được trả lại cho model để nó tự sửa."""
	try:
		payload = json.load(sys.stdin)
	except (json.JSONDecodeError, ValueError):
		return 0  # hook không bao giờ được làm hỏng phiên làm việc vì input lạ
	message = hook_decision(payload, root=str(repo_root()))
	if not message:
		return 0
	print(
		f"{message}\n\nĐặt lại cho đúng rồi ghi lại. "
		f"Quy ước đầy đủ: .claude/skills/code_structure/SKILL.md",
		file=sys.stderr,
	)
	return 2


def main(argv: list[str]) -> int:
	if argv and argv[0] == "--hook":
		return run_as_hook()

	root = repo_root()
	if argv:
		paths = argv
	else:
		# Không tham số = soi toàn bộ cây đang tracked. Làm được vì cây đã sạch sau đợt
		# dọn 2026-08-14, và như vậy bắt luôn cả regression trên file cũ.
		out = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True, check=True)
		paths = out.stdout.splitlines()

	patches_txt = (root / "hrms" / "patches.txt").read_text(encoding="utf-8")
	found = check_all(paths, patches_txt)
	if not found:
		return 0

	print(f"Sai cấu trúc: {len(found)} file. Xem `.claude/skills/code_structure/SKILL.md`.\n")
	for path in sorted(found):
		print(f"  {path}")
		for problem in found[path]:
			print(f"      → {problem}")
	return 1


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
