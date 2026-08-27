# Spec: Trường định danh VN trên Employee (Đợt E — thu hẹp)

> Status: **APPROVED scope 2026-07-16** (Q&A roadmap: "chỉ trường định danh", không doctype HĐLĐ).
> Xem `docs/audit-roadmap-2026-07-16.md` mục 2.5 + Đợt E.

## Objective

Hồ sơ Employee hiện thiếu định danh pháp lý VN: không có **số CCCD**, **số sổ BHXH**. Riêng
**MST cá nhân** đã có chỗ chứa: field `tax_id` (Data, "Tax ID") đã tồn tại trên Employee trong fork
erpnext (`erpnext/setup/doctype/employee/employee.json:840`) — **không thêm field trùng**, chỉ
chuẩn hóa cách dùng + nhãn VN.

**Success:** HR nhập được CCCD + số sổ BHXH trên form Employee (Desk); fixtures re-sync mỗi migrate;
additive 100% (không đụng logic nào).

## Thiết kế

2 Custom Field mới trên **Employee**, qua `hrms/fixtures/custom_field.json` (cùng cơ chế với các
custom field hiện có):

| Fieldname | Label | Type | Vị trí |
|---|---|---|---|
| `custom_citizen_id` | Số CCCD | Data | Personal tab — sau `marital_status` (cạnh Passport Details) |
| `custom_social_insurance_no` | Số sổ BHXH | Data | ngay sau `custom_citizen_id` |

- Fieldname English, label VN (đúng convention naming đã chốt).
- Không `unique`/`reqd` (dữ liệu cũ trống; ràng buộc thêm sau nếu HR cần).
- MST cá nhân: dùng `tax_id` sẵn có; thêm dòng dịch "Tax ID" → "MST cá nhân" vào `hrms/translations/vi.csv`.
- Cập nhật **fixtures filter** trong `hooks.py` (thêm 2 tên `Employee-custom_*`) — test sync
  fixtures↔filter hiện có phải được mở rộng/giữ xanh.

## Điều KHÔNG làm

- Không doctype hợp đồng lao động (đã quyết định loại).
- Không thêm ngày cấp/nơi cấp CCCD, loại HĐ, v.v. — chờ HR yêu cầu cụ thể.
- Không validate định dạng (12 số CCCD…) đợt này — additive thuần.

## Files

```
hrms/fixtures/custom_field.json   (sửa — +2 field Employee)
hrms/hooks.py                     (sửa — filter +2 tên)
hrms/translations/vi.csv          (sửa — Tax ID → MST cá nhân)
hrms/tests/test_setup_vn_defaults.py hoặc test fixture hiện có (mở rộng đếm/sync)
```

## Testing (rollback harness)

1. Sau `bench migrate`: 2 Custom Field tồn tại trên Employee, đúng label/insert_after.
2. Test sync fixtures↔hooks filter xanh với danh sách mới (12 custom field).
3. Set/đọc giá trị 2 field trên một Employee test — không side effect.

## Boundaries

- **Always:** additive, revert được; label VN/fieldname English.
- **Ask first:** deploy lên prod (gộp gate Đợt A/T2); thêm ràng buộc unique/reqd sau này.
- **Never:** đụng field `tax_id` structure; thêm doctype mới.
