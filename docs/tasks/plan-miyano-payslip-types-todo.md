# Todo: Phiếu lương Miyano theo loại (mẫu 09/2026)

> Chi tiết, tiêu chí nghiệm thu và cách kiểm: `docs/tasks/plan-miyano-payslip-types.md`.

## Trước khi bắt đầu
- [x] D1: dòng 6 = Bán thời gian, thuế part time theo cờ đăng ký giảm trừ (chốt 2026-10-30)
- [ ] HR/kế toán chốt D2–D5 (code đã làm theo phương án đề xuất 2026-10-30; chờ xác nhận trước khi deploy)
- [x] Ghi mốc test đỏ `hrms.vn_payroll.tests.test_salary_slip_mvl` (danh sách tên test)

## Phase 1: Sửa công thức sai
- [x] Task 1: Phiếu Thử việc không bao giờ có bảo hiểm (S)
- [x] Task 2: Thuế part time theo cờ đăng ký giảm trừ; Khoán / Chuyên gia không trừ gia cảnh (S)
- [x] **Checkpoint A:** không đỏ mới · 6 phiếu T7/2026 giữ nguyên net + thuế

## Phase 2: Khoản thu nhập HR nhập
- [x] Task 3: Mọi loại phiếu nhận Thưởng (Lễ/Tết) và báo cáo hiện cột này (M) — sau Task 2
- [x] Task 4: Thưởng KPI, Hỗ trợ điện thoại, Hỗ trợ xăng xe + TK 6421 (M) — sau Task 3
- [x] **Checkpoint B:** toàn bộ test lương xanh · duyệt D2, D5 + TK 6421

## Phase 3: KPCĐ
- [x] Task 5: KPCĐ trên phiếu Chính thức (M) — sau Task 1
- [x] Task 6: KPCĐ vào báo cáo và bút toán 3382 (S) — sau Task 5
- [x] **Checkpoint C:** bất biến lặp lại (chỉ gương chi phí Chính thức +2% × G) · duyệt D3

## Phase 4: Đầu ra theo mẫu + nghiệm thu
- [x] Task 7: Báo cáo và file Excel theo bố cục mẫu A–Z (M) — sau Task 4, 6
- [x] Task 8: Phiếu in "Phiếu lương MVL" hiện đủ khoản (S) — sau Task 4, 5
- [x] Task 9: Nghiệm thu E2E 6 dòng mẫu qua Payroll Entry + bút toán cân + cập nhật spec (M) — sau Task 1–8
- [x] **Checkpoint hoàn tất:** mọi tiêu chí đạt · ruff sạch · người duyệt xem lại

## Triển khai (ask-first)
- [ ] Ký duyệt D1–D5 + TK GL
- [ ] `bench --site miyano migrate`
- [ ] User restart app
- [ ] HR tạo Additional Salary định kỳ (điện thoại / xăng xe), KPI + Lễ/Tết mỗi kỳ
