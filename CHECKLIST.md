# CHECKLIST THỰC HIỆN DỰ ÁN K4 L3B — MULTI-AGENT MCP + A2A

> **Mục tiêu:** Xây dựng hệ thống Multi-Agent điều tra khiếu nại thương mại điện tử (tập dữ liệu Olist Brazilian E-commerce), tích hợp MCP Gateway, phân giải thực thể (Entity Resolution), xử lý xung đột dữ liệu (Source Conflict), tối ưu chi phí gọi tool (Efficiency) và ghi trace chuẩn xác.

---

## 📌 BẢNG TỔNG QUAN TIÊU CHÍ CHẤM ĐIỂM & ĐIỀU KIỆN TIÊN QUYẾT

### 1. Trọng số điểm (L3B Variant)

- [ ] **Semantic (40%):** Độ đúng nghiệp vụ, phân tích đúng vấn đề chính (`primary_issue`), nguyên nhân gốc rễ (`root_cause`) và quyết định tài chính.
- [ ] **Evidence (15%):** Thu thập đầy đủ bằng chứng bắt buộc theo từng nhóm nghiệp vụ, độ chính xác của bằng chứng liên quan.
- [ ] **Provenance (15%):** Mọi `evidence_ref` phải xuất phát từ MCP audit thực tế, khớp chính xác `team_id`, `run_id` và `case_id`.
- [ ] **Consistency (10%):** Tính nhất quán logic giữa các trường (trạng thái khiếu nại, hoàn tiền, trách nhiệm các bên, không trùng lặp hành động).
- [ ] **Schema (5%):** Khớp 100% JSON Schema chuẩn (`day09-l3b-output-v2`).
- [ ] **Calibration (5%):** Mức độ tin cậy (`confidence`) đánh giá hợp lý, bám sát độ chính xác thực tế.
- [ ] **Workflow (5%):** Đầy đủ các lifecycle events trong trace theo đúng thứ tự, thể hiện sự phối hợp đa tác nhân.
- [ ] **Efficiency (5%):** Gọi MCP tools hiệu quả, không gọi dư thừa, nằm trong budget cho phép của từng case.

### 2. ⚠️ Các Hard Gates (Vi phạm = 0 ĐIỂM toàn bộ Case)

- [ ] Không khớp `case_id` giữa input, trace và output.
- [ ] Output sai định dạng JSON hoặc không thỏa mãn JSON Schema.
- [ ] Thiếu bằng chứng bắt buộc (`missing_required_evidence`).
- [ ] Tự tạo hoặc sửa đổi `evidence_ref` giả mạo (`invalid_evidence_refs`).
- [ ] `evidence_ref` không tồn tại trong hệ thống MCP Server Audit (`unknown_evidence_ref`).
- [ ] Sử dụng bằng chứng chéo giữa các case hoặc sai scope (`cross_scope_evidence_ref`).

---

## 🚀 CHECKLIST CHI TIẾT THEO TỪNG GIAI ĐOẠN

### GIAI ĐOẠN 1: THIẾT LẬP MÔI TRƯỜNG & ĐĂNG KÝ TEAM

- [x] **1.1. Chuẩn bị môi trường Python:**
  - [x] Cài đặt Python `>= 3.11`.
  - [x] Tạo môi trường ảo: `python -m venv .venv`.
  - [x] Kích hoạt môi trường ảo:
    - Windows (PowerShell): `.venv\Scripts\Activate.ps1`
    - Linux/macOS: `source .venv/bin/activate`
  - [x] Cài đặt package và dev dependencies: `pip install -e ".[dev]"`.
  - [x] Kiểm tra môi trường: chạy `pytest -q` và `day09 --help`.
- [x] **1.2. Đăng ký Team trên Competition Workspace:**
  - [x] Truy cập đường dẫn `/register` trên Competition Workspace.
  - [x] Điền thông tin: Tên team, mã học viên, danh sách thành viên.
  - [x] Nhập `registration code` của lớp học.
  - [x] Lưu lại **Team API Key** (dạng `sk-team-...`).
- [x] **1.3. Cấu hình biến môi trường:**
  - [x] Copy file mẫu: `cp .env.example .env`.
  - [x] Cập nhật giá trị thật vào `.env`:
    - `COMPETITION_API_URL`
    - `COMPETITION_TEAM_API_KEY=sk-team-...`
    - `MCP_ENDPOINT`
  - [x] Thử nghiệm kết nối MCP Gateway: chạy `day09 mcp-tools` để khám phá danh sách công cụ được cấp.

---

### GIAI ĐOẠN 2: CHUẨN BỊ VÀ THẨM ĐỊNH DỮ LIỆU ĐẦU VÀO

- [x] **2.1. Tải và giải nén dữ liệu:**
  - [x] Tải file `l3b-inputs-<version>.zip` từ GitHub Release của cuộc thi.
  - [x] Giải nén trực tiếp vào thư mục gốc của repository.
  - [x] Kiểm tra cấu trúc thư mục đảm bảo đúng chuẩn:
    ```text
    case-set.json
    inputs/
    ├── L3B_CASE_001.json
    ├── ...
    └── L3B_CASE_100.json
    ```
- [x] **2.2. Thẩm định dữ liệu đầu vào:**
  - [x] Chạy lệnh: .venv\Scripts\Activate.ps1.
  - [ ] Xác nhận output hiển thị đủ 100 cases hợp lệ.
  - [ ] Phân tích mẫu các case: xác định các trường hợp thiếu exact order ID cần phân giải thực thể (Entity Resolution).

---

### GIAI ĐOẠN 3: HOÀN THIỆN THIẾT KẾ KIẾN TRÚC (`ARCHITECTURE.md`)

- [x] **3.1. System Overview:**
  - [x] Mô tả sơ đồ luồng tổng thể:
    `Input → Entity Resolver → Coordinator → Specialists → Conflict Resolver → Verifier → Output / Trace`
- [x] **3.2. Phân quyền và Trách nhiệm Agent (Agent Ownership):**
  - [x] Điền bảng phân nhiệm chi tiết cho từng tác nhân theo nguyên tắc Least Privilege (chỉ cấp quyền gọi MCP tool cần thiết):
    - `Entity/Customer Agent`: Phân giải candidate, truy xuất lịch sử khách hàng.
    - `Coordinator Agent`: Nhận case, điều phối, giao việc và tổng hợp.
    - `Order/Product Agent`: Kiểm tra trạng thái đơn, danh sách mặt hàng, giá trị tiền.
    - `Shipment Agent`: Đánh giá tiến độ giao hàng, bên chịu trách nhiệm chậm trễ (seller vs logistics).
    - `Payment/Refund Agent`: Đối soát cổng thanh toán, hoàn tiền, số tiền được hoàn.
    - `Policy Agent`: Kiểm tra chính sách bồi thường/khiếu nại.
    - `Conflict Resolver Agent`: Xử lý xung đột giữa các nguồn dữ liệu (seller, buyer, system logs).
    - `Verifier Agent`: Kiểm tra tính hợp lệ của output trước khi finalize.
- [x] **3.3. Entity Resolution & Giao thức A2A:**
  - [x] Cơ chế xếp hạng và loại trừ candidate (`rejected_candidates`).
  - [x] Ngưỡng tin cậy (Confidence threshold) để chấp nhận kết quả resolve.
  - [x] Quy tắc đóng gói envelope, timeout và cơ chế chống vòng lặp (loop avoidance).
- [x] **3.4. Vòng đời Evidence & Xử lý xung đột:**
  - [x] Quy trình kiểm tra schema response từ MCP.
  - [x] Thu thập và gắn `evidence_ref` vào từng claim/assessment.
  - [x] Quy tắc ưu tiên nguồn dữ liệu (Source precedence: log hệ thống > xác nhận vận chuyển > tự khai).
  - [x] Bắt buộc ghi nhận sự kiện `tool_result_consumed` vào trace.
- [x] **3.5. Chính sách lỗi & Tối ưu hiệu quả (Failure & Efficiency):**
  - [x] Chiến lược Cache MCP trong phạm vi từng case để tránh gọi trùng.
  - [x] Ngân sách retry (Retry budget) hữu hạn khi gặp MCP Timeout hoặc dữ liệu không rõ ràng.
  - [x] Chiến lược Fallback an toàn, không tự suy đoán thông tin khi thiếu bằng chứng.
- [x] **3.6. Verification Invariants (Bất biến kiểm định):**
  - [x] Danh sách kiểm tra trước khi hoàn tất output (Schema, liên kết bằng chứng, tổng tiền hoàn, tính nhất quán).
- [x] **3.7. Reproducibility:**
  - [x] Ghi lại model, cấu hình, giới hạn tài nguyên và concurrency.
  - [x] Cam kết không ghi lộ bí mật / API Key vào tài liệu.

---

### GIAI ĐOẠN 4: HIỆN THỰC HÓA MULTI-AGENT WORKFLOW (`src/student_agent/workflow.py`)

- [x] **4.1. Cấu trúc hàm điều phối** **`solve_case`:**
  - [x] Nhận tham số: `case: dict`, `gateway: EvidenceGateway`, `trace: TraceWriter`.
  - [x] Khởi tạo context điều tra riêng biệt cho từng `case_id`.
- [x] **4.2. Ghi Trace Observable chuẩn:**
  - [x] Đảm bảo phát sinh đầy đủ các sự kiện bắt buộc theo thứ tự:
    - [x] `case_received` (Actor: Coordinator) - *Đã có sẵn tại CLI*
    - [x] `task_assigned` (Actor: Coordinator -> Target: Specialist)
    - [x] `tool_result_consumed` (Mỗi khi Specialist dùng kết quả từ MCP Gateway)
    - [x] `handoff` (Chuyển giao kết quả giữa các tác nhân)
    - [x] `policy_decided` (Khi áp dụng quy tắc nghiệp vụ/giải quyết xung đột)
    - [x] `verification_completed` (Actor: Verifier)
    - [x] `case_finalized` (Actor: Coordinator) - *Đã có sẵn tại CLI*
  - [x] Không ghi prompt nội bộ hoặc chuỗi suy luận (chain-of-thought) vào trace.
- [x] **4.3. Module Phân giải Thực thể (Entity Resolution):**
  - [x] Kiểm tra nếu case có sẵn `order_id` -> xác thực qua MCP.
  - [x] Nếu case chỉ có `candidate_order_ids` -> gọi MCP tra cứu thông tin (customer, items, timestamps) để chọn đúng `resolved_order_ids` và liệt kê `rejected_candidates`.
  - [x] Trích xuất `customer_unique_id` và danh sách `related_order_ids`.
  - [x] Thiết lập trạng thái: `"resolved"`, `"ambiguous"`, hoặc `"not_found"`.
- [x] **4.4. Module Phân tích Vận chuyển (Shipment Analysis):**
  - [x] Gọi MCP tra cứu tracking / shipment data của đơn hàng.
  - [x] So sánh `shipping_limit_date`, `delivered_carrier_date`, `estimated_delivery_date`, `delivered_customer_date`.
  - [x] Đưa ra verdict: `on_time`, `seller_delay`, `logistics_delay`, `lost`, `returned`, `conflicting`, hoặc `insufficient_evidence`.
  - [x] Xác định danh sách `late_seller_ids` và cờ `timeline_complete`.
- [x] **4.5. Module Phân tích Thanh toán (Payment Analysis):**
  - [x] Tra cứu thông tin thanh toán và giao dịch hoàn tiền.
  - [x] Tính toán chính xác số liệu tiền tệ (BRL):
    - `captured_total_brl`: Tổng tiền đã trừ của khách.
    - `refunded_total_brl`: Tổng tiền đã hoàn trả.
    - `refundable_total_brl`: Số tiền còn có thể hoàn trả hợp lệ.
  - [x] Đưa ra verdict: `reconciled`, `capture_mismatch`, `duplicate_capture`, `refund_pending`, `refund_failed`, `refunded`, hoặc `insufficient_evidence`.
- [x] **4.6. Module Phân tích Nguyên nhân gốc & Xử lý Xung đột:**
  - [x] Xếp hạng các nguyên nhân gốc (`ranked_causes`) kèm mã lỗi chuẩn.
  - [x] Xác định bên chịu trách nhiệm (`responsible_parties`: seller, platform, logistics\_provider, payment\_provider, customer, unknown).
  - [x] Phát hiện và lập danh sách xung đột dữ liệu (`data_conflicts`): trường xung đột, các nguồn tin, nguồn được chọn và mã giải quyết.
- [x] **4.7. Module Quyết định Tài chính & Hành động (Financial Resolution & Actions):**
  - [x] Xác định số tiền đề xuất hoàn: `recommended_refund_brl` (loại tiền tệ `"BRL"`).
  - [x] Liệt kê chi tiết từng dòng hoàn tiền (`refund_lines`): `reason_code`, `amount_brl`, `entity_id`.
  - [x] Đưa ra danh sách hành động đề xuất (`resolution_actions`): tối đa 8 hành động cụ thể, không trùng lặp.
- [x] **4.8. Module Kiểm định (Verifier Agent):**
  - [x] Kiểm tra ràng buộc Schema trước khi trả về kết quả.
  - [x] Kiểm tra tính nhất quán logic (Consistency invariants):
    - Nếu `case_status == "no_action"` thì `recommended_refund_brl == 0` và không có action yêu cầu can thiệp.
    - `recommended_refund_brl` không được vượt quá `refundable_total_brl`.
    - Mọi `evidence_refs` trong output phải là tập con của các evidence đã tiêu thụ trong trace.
  - [x] Hiệu chuẩn điểm tin cậy (`confidence`): đặt giá trị phản ánh đúng mức độ chắc chắn của bằng chứng, tránh gán cố định 1.0.

---

### GIAI ĐOẠN 5: CHẠY KIỂM THỬ, ĐÁNH GIÁ & TỐI ƯU

- [ ] **5.1. Thực thi toàn bộ pipeline:**
  - [x] Chạy lệnh: `day09 run`.
  - [x] Theo dõi log, đảm bảo không có case nào bị crash hoặc unhandled exception.
  - [x] Kiểm tra thư mục `outputs/` sinh đủ 100 file JSON (`L3B_CASE_001.json` ... `L3B_CASE_100.json`).
  - [x] Kiểm tra file `traces/trace.jsonl` được ghi nhận đầy đủ các sự kiện.
- [ ] **5.2. Thẩm định kết quả (Validation):**
  - [x] Chạy lệnh: `day09 validate`.
  - [x] Đảm bảo pass 100% schema và trace events.
  - [ ] Chạy test tự động: `pytest -q`.
  - [x] Chạy linter kiểm tra chất lượng code: `ruff check .`.
- [ ] **5.3. Tối ưu hóa điểm số:**
  - [ ] Đánh giá số lần gọi MCP tool: loại bỏ các cuộc gọi trùng lặp (tận dụng caching) để nâng điểm **Efficiency (5%)**.
  - [ ] Kiểm tra kỹ bằng chứng liên kết để tối đa điểm **Evidence (15%)** và **Provenance (15%)**.
  - [ ] Rà soát tính chặt chẽ giữa các trường dữ liệu để lấy trọn **Consistency (10%)**.

---

### GIAI ĐOẠN 6: ĐÓNG GÓI VÀ NỘP BÀI THI

- [ ] **6.1. Đóng gói bài thi (Packaging):**
  - [ ] Chạy lệnh: `day09 package --output dist/submission.zip`.
  - [ ] Xác nhận gói `dist/submission.zip` được tạo thành công.
- [ ] **6.2. Kiểm tra an toàn bảo mật (Safety Checks):**
  - [ ] Kiểm tra nội dung bên trong file ZIP, **CHỈ ĐƯỢC CHỨA DUY NHẤT 3 THÀNH PHẦN**:
    ```text
    manifest.json
    trace.jsonl
    outputs/
    ├── L3B_CASE_001.json
    ├── ...
    └── L3B_CASE_100.json
    ```
  - [ ] Tuyệt đối **KHÔNG** đưa mã nguồn (`src/`), dữ liệu đầu vào (`inputs/`), file `.env`, API key hoặc debug log vào file ZIP.
  - [ ] Đảm bảo không chứa bất kỳ chuỗi bí mật nào (`sk-team-...`).
  - [ ] Đảm bảo từng file <= 1MB và tổng dung lượng giải nén <= 12MB.
- [ ] **6.3. Nộp bài lên hệ thống:**
  - [ ] Mở giao diện Competition Workspace tại endpoint `/l3b`.
  - [ ] Upload file `dist/submission.zip`.
  - [ ] Quan sát kết quả chấm sơ bộ trên Public Leaderboard (chiếm 20% trọng số).
  - [ ] Chọn bản submission ưng ý nhất để đánh dấu làm **Final Submission** (áp dụng cho 80% Private Leaderboard).
