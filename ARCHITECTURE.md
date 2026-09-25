# L3B Architecture Record — Multi-Agent MCP + A2A System

Tài liệu đặc tả kiến trúc kỹ thuật hệ thống Multi-Agent điều tra khiếu nại thương mại điện tử (K4 L3B). Hệ thống tuân thủ mô hình A2A (Agent-to-Agent), tích hợp MCP Gateway, phân giải thực thể (Entity Resolution), xử lý xung đột dữ liệu đa nguồn và đảm bảo khả năng kiểm chứng 100% qua trace observable.

---

## 1. System overview

Hệ thống được thiết kế theo luồng điều phối hướng đơn (Directed Acyclic Graph - DAG), kết hợp giữa kiến trúc **Orchestrator/Coordinator** và các **Specialist Agents** hoạt động độc lập theo nguyên tắc đặc quyền tối thiểu (Least Privilege).

### Sơ đồ luồng xử lý tổng thể

```text
       [ Case Input JSON ]
                │
                ▼
      ┌──────────────────┐
      │  Entity Resolver │ ◄── MCP: get_order, get_customer_history
      └─────────┬────────┘
                │ (Resolved Order + Customer Context)
                ▼
      ┌──────────────────┐
      │   Coordinator    │ ── Emits: task_assigned, handoff
      └─────────┬────────┘
                │
   ┌────────────┼────────────────────────┐
   ▼            ▼                        ▼
┌──────────┐ ┌──────────────┐ ┌────────────────────┐
│  Order   │ │   Shipment   │ │   Payment/Refund   │
│  Agent   │ │    Agent     │ │       Agent        │
└────┬─────┘ └──────┬───────┘ └──────────┬─────────┘
     │              │                    │
     │ MCP:         │ MCP:               │ MCP:
     │ get_order_   │ get_shipment_      │ get_order_payments,
     │ items,       │ summary,           │ get_payment_timeline,
     │ get_product_ │ get_sellers        │ get_refund_timeline
     │ context      │                    │
     └──────────────┼────────────────────┘
                    │ (Specialist Findings + Evidence Refs)
                    ▼
          ┌──────────────────┐
          │   Policy Agent   │ ◄── MCP: get_policy
          └─────────┬────────┘
                    │ (Rules & SLA Thresholds)
                    ▼
          ┌──────────────────┐
          │ Conflict Resolver│ ── Emits: policy_decided (Source Precedence)
          └─────────┬────────┘
                    │ (Draft Output + Claims Assessment)
                    ▼
          ┌──────────────────┐
          │     Verifier     │ ── Emits: verification_completed (10 Invariants)
          └─────────┬────────┘
                    │ (Validated Payload)
                    ▼
      [ Output JSON (day09-l3b-output-v2) ] + [ Observable Trace JSONL ]
```

### Các giai đoạn thực thi (Execution Phases)
1. **Case Ingestion & Envelope Init:** Coordinator nhận `case_id`, khởi tạo context điều tra, emit sự kiện `case_received`.
2. **Entity & Context Disambiguation:** `Entity/Customer Agent` nhận diện chính xác `order_id` từ danh sách `candidate_order_ids`, phân tách `rejected_candidates` và truy xuất `customer_unique_id`.
3. **Targeted Investigation Dispatch:** `Coordinator` phân tích `investigation_scope` và `customer_request.claims`, giao nhiệm vụ (`task_assigned`) cho các domain specialist tương ứng.
4. **Evidence Collection & Consumption:** Các Specialist Agents gọi các MCP tools được ủy quyền, lưu trữ `evidence_ref` và phát sự kiện `tool_result_consumed`.
5. **Policy Matching & Conflict Resolution:** `Policy Agent` đối soát quy định bồi hoàn; `Conflict Resolver` đối chiếu log vận chuyển/thanh toán với khiếu nại của khách để phân giải mâu thuẫn nguồn tin và xếp hạng nguyên nhân gốc (`root_cause_analysis`).
6. **Deterministic Verification:** `Verifier` kiểm tra tính toàn vẹn của 10 bất biến (schema, toán học tài chính, provenance của bằng chứng, tính nhất quán trạng thái).
7. **Finalization:** `Coordinator` sinh file `outputs/<case_id>.json` và emit sự kiện `case_finalized`.

---

## 2. Agent ownership

Áp dụng nguyên tắc **Least Privilege (Đặc quyền tối thiểu)**: Mỗi tác nhân chỉ được cấp quyền truy cập các MCP tools phục vụ trực tiếp cho phạm vi nghiệp vụ của mình. Coordinator, Conflict Resolver và Verifier không được trực tiếp gọi MCP tools để tránh lãng phí call budget và phá vỡ cấu trúc trách nhiệm.

| Actor | Input | Trách nhiệm chính | Tool permission (MCP) | Output / Handoff |
| :--- | :--- | :--- | :--- | :--- |
| **Entity/Customer** (`entity-agent`) | `claimed_order_id`, `candidate_order_ids`, `customer_unique_id_hint`, `customer_request` | Phân giải order chính xác, loại trừ candidate sai, liên kết `customer_unique_id` và các `related_order_ids`. | `get_customer_history`, `get_order` | `entity_resolution` dict, `customer_context` dict $\rightarrow$ Handoff về `coordinator`. |
| **Coordinator** (`coordinator`) | Case payload từ runner, kết quả điều tra từ các Specialist | Quản lý vòng đời case, phân rã điều tra, điều phối luồng A2A, quản lý cache và ngân sách gọi tool. | *None* (Không gọi tool) | Giao nhiệm vụ (`task_assigned`), chuyển giao context (`handoff`), tổng hợp output cuối. |
| **Order/Product** (`order-agent`) | `resolved_order_ids`, `investigation_scope` | Trích xuất danh sách mặt hàng (`item_ids`), người bán (`seller_ids`), trọng lượng, kích thước và phân loại hàng hóa. | `get_order`, `get_order_items`, `get_product_context` | `affected_entities` (items, sellers), đặc tính sản phẩm $\rightarrow$ Handoff về `coordinator`. |
| **Shipment** (`shipment-agent`) | `resolved_order_ids`, claims về giao hàng | Phân tích mốc thời gian giao nhận, SLA cam kết, xác định chậm trễ do người bán hay bên vận chuyển, phát hiện đơn thất lạc/hoàn trả. | `get_shipment_summary`, `get_sellers` | `shipment_analysis` (`verdict`, `late_seller_ids`, `timeline_complete`, `shipment_ids`) $\rightarrow$ Handoff về `coordinator`. |
| **Payment/Refund** (`payment-agent`) | `resolved_order_ids`, claims về tài chính | Đối soát dòng tiền thanh toán (thẻ, boleto, voucher), tính toán `captured_total_brl`, `refunded_total_brl`, `refundable_total_brl`, lịch sử hoàn tiền. | `get_order_payments`, `get_payment_timeline`, `get_refund_timeline` | `payment_analysis` (`verdict`, số dư BRL, `payment_references`) $\rightarrow$ Handoff về `coordinator`. |
| **Policy** (`policy-agent`) | `policy_version`, các claim cần kiểm tra | Tra cứu điều khoản bảo vệ khách hàng, thời hạn khiếu nại tối đa, mức bồi hoàn theo chính sách. | `get_policy` | Điều kiện bồi hoàn, căn cứ pháp lý chính sách $\rightarrow$ Handoff về `conflict-resolver`. |
| **Conflict Resolver** (`conflict-resolver`) | Dữ liệu tổng hợp từ các Specialist và Policy | Phát hiện xung đột dữ liệu đa nguồn, áp dụng quy tắc thứ bậc ưu tiên nguồn tin, xếp hạng nguyên nhân gốc (`ranked_causes`), đề xuất giải pháp tài chính. | *None* (Không gọi tool) | `root_cause_analysis`, `data_conflicts`, `financial_resolution`, `resolution_actions` $\rightarrow$ Handoff về `verifier`. |
| **Verifier** (`verifier`) | Toàn bộ payload output dự thảo, trace log hiện tại | Kiểm tra 10 bất biến nghiệp vụ, kiểm tra schema compliance, đối soát provenance của bằng chứng, hiệu chuẩn `confidence`. | *None* (Không gọi tool) | Báo cáo kiểm định hợp lệ, emit `verification_completed` $\rightarrow$ Chuyển quyền cho `coordinator` để finalize. |

---

## 3. Entity resolution và A2A protocol

### 3.1. Cơ chế xếp hạng và loại trừ Candidate (Ranking & Rejection)
1. **Kiểm tra Exact Match:** Nếu `claimed_order_id` có mặt trong `candidate_order_ids`, gọi `get_order` để xác thực sự tồn tại. Nếu đơn hàng hợp lệ và khớp với ngữ cảnh khiếu nại, candidate này được chọn.
2. **Đối chiếu chéo (Cross-referencing Candidate Disambiguation):**
   - **Customer Linkage:** Gọi `get_customer_history` bằng `customer_unique_id_hint` để lấy danh sách lịch sử đơn hàng của khách hàng.
   - **Timestamp Proximity:** So khớp ngày tạo đơn trong dữ liệu MCP với `opened_at` của case.
   - **Item & Seller Match:** So sánh các từ khóa mặt hàng hoặc người bán trong `customer_request.message` với `get_order_items`.
3. **Phân loại kết quả:**
   - **Resolved (`status = "resolved"`):** Tìm được đúng 1 order ID thỏa mãn toàn bộ tiêu chí liên kết. Order này đưa vào `resolved_order_ids`. Tất cả các candidate còn lại lập tức bị đưa vào `rejected_candidates`.
   - **Ambiguous (`status = "ambiguous"`):** Tồn tại từ 2 candidate trở lên đều có bằng chứng hỗ trợ ngang nhau hoặc không đủ căn cứ loại trừ. Cả 2 được giữ lại hoặc ghi nhận phân vân, `confidence` bị giới hạn $\le 0.50$.
   - **Not Found (`status = "not_found"`):** Không có candidate nào khớp với customer history hoặc hệ thống database. `resolved_order_ids = []`, toàn bộ candidate ban đầu chuyển vào `rejected_candidates`.

### 3.2. Ngưỡng tin cậy (Confidence Threshold)
- $\ge 0.85$: Tìm thấy đơn hàng chính xác, có bằng chứng log hệ thống xác nhận đầy đủ customer ID và timeline.
- $0.60 - 0.84$: Khớp gián tiếp qua lịch sử khách hàng nhưng một số mốc thông tin chi tiết mặt hàng bị thiếu.
- $< 0.60$: Dữ liệu mập mờ, thiếu bằng chứng xác thực (`needs_investigation`).

### 3.3. Giao thức A2A (Agent-to-Agent Protocol)
- **Message Envelope:** Các Agent trao đổi thông tin nội bộ thông qua cấu trúc envelope chuẩn:
  ```json
  {
    "case_id": "L3B_CASE_001",
    "sender": "shipment-agent",
    "receiver": "coordinator",
    "event_type": "handoff",
    "payload": { ... },
    "evidence_refs": ["ev_abc123..."],
    "occurred_at": "2026-09-25T08:00:00.000Z"
  }
  ```
- **Correlation qua `case_id`:** Mọi thông điệp và event trace bắt buộc chứa `case_id` tương ứng. Không cho phép rò rỉ dữ liệu hoặc chia sẻ context giữa các case.
- **Cơ chế chống vòng lặp (Loop Avoidance) & Timeout:**
  - Luồng điều phối là **DAG đơn hướng**: Coordinator $\rightarrow$ Specialists $\rightarrow$ Conflict Resolver $\rightarrow$ Verifier.
  - Không cho phép bất kỳ chu trình phản hồi lặp nào (No cyclic loops).
  - Giới hạn thời gian (Timeout): Mỗi lệnh gọi MCP timeout tối đa 10s (tổng per-case tối đa 30s). Nếu quá thời gian, kích hoạt fallback mà không retry lặp vô hạn.

---

## 4. Evidence và conflict lifecycle

### 4.1. Quy trình thẩm định và lưu trữ Evidence (Validation & Storage)
1. **Schema Validation:** Mọi dữ liệu trả về từ MCP Gateway được kiểm định qua `Contracts.validate_evidence(evidence)` theo schema `mcp-evidence-response-v1.schema.json`.
2. **Trích xuất `evidence_ref`:** Lấy định danh duy nhất của bằng chứng (`ev_[A-Za-z0-9_-]{20,96}`). Tuyệt đối không tự sinh hay sửa đổi chuỗi này.
3. **Ghi nhận Trace Event:** Khi bất kỳ Specialist nào sử dụng dữ liệu từ bằng chứng để đưa ra kết luận, phải lập tức phát sinh sự kiện trace:
   - `event_type`: `"tool_result_consumed"`
   - `actor`: Tên agent tiêu thụ (ví dụ: `"shipment-agent"`)
   - `tool_name`: Tên công cụ MCP (ví dụ: `"get_shipment_summary"`)
   - `evidence_refs`: Danh sách các mã bằng chứng liên quan.
4. **Mapping vào Output:** Mọi `evidence_ref` trong output (`evidence_refs` tổng và `claim_assessments[].evidence_refs`) phải là tập con của các evidence đã được ghi nhận trong trace của chính case đó.

### 4.2. Quy tắc thứ bậc ưu tiên nguồn tin (Source Precedence Hierarchy)
Khi có sự mâu thuẫn giữa các lời khai hoặc luồng thông tin, hệ thống giải quyết theo thứ bậc tin cậy:
1. **Tier 1 (Độ tin cậy cao nhất — Immutable System Logs):**
   - Nhật ký bưu cục và trạng thái vận chuyển từ đối tác logistics (`get_shipment_summary`).
   - Lịch sử đối soát cổng thanh toán và giao dịch ngân hàng (`get_payment_timeline`, `get_refund_timeline`).
2. **Tier 2 (Platform Database Records):**
   - Bản ghi trạng thái đơn hàng và các mặt hàng trong cơ sở dữ liệu sàn (`get_order`, `get_order_items`, `get_order_payments`).
3. **Tier 3 (Master Registry & Metadata):**
   - Hồ sơ người bán (`get_sellers`) và danh mục sản phẩm (`get_product_context`).
4. **Tier 4 (Độ tin cậy thấp nhất — Unverified Declarations):**
   - Lời khiếu nại của khách hàng (`customer_request.message`).
   - Phản hồi giải trình từ người bán.

### 4.3. Biểu diễn xung đột dữ liệu (`data_conflicts`)
Khi phát hiện mâu thuẫn giữa 2 nguồn tin trở lên, Conflict Resolver ghi nhận vào mảng `data_conflicts`:
```json
{
  "field": "delivery_status",
  "sources": ["customer_claim", "carrier_tracking_log"],
  "selected_source": "carrier_tracking_log",
  "resolution_code": "SYSTEM_LOGS_SUPERSEDE_SELF_REPORT"
}
```
Nếu cả hai nguồn cùng độ tin cậy nhưng trái ngược nhau mà không có log chứng minh: `selected_source = null`, `resolution_code = "UNRESOLVABLE_EVIDENCE_GAP"`.

---

## 5. Failure and efficiency policy

### 5.1. Bảng chính sách xử lý sự cố (Failure Handling Matrix)

| Tình huống sự cố | Ngân sách Retry | Chiến lược Fallback an toàn | Mã Trace / Sự kiện phát sinh |
| :--- | :---: | :--- | :--- |
| **MCP Timeout / Network 5xx** | Tối đa 1 lần (backoff 500ms) | Đánh dấu thiếu bằng chứng cho phân hệ đó; tiếp tục với các phân hệ khác; hạ confidence. | `task_assigned` kèm fallback note / `RETRY_EXHAUSTED` |
| **Entity Not Found / Ambiguous** | 0 lần (Không quét mò) | Thiết lập `status = "not_found"` hoặc `"ambiguous"`; kết luận `primary_issue = "insufficient_evidence"`. | `policy_decided` với mã `ENTITY_UNRESOLVED` |
| **Source Conflict không giải quyết được** | 0 lần | Chọn `selected_source = null`; đưa `case_status = "needs_investigation"`; giữ nguyên trạng thái tài chính an toàn. | `policy_decided` với mã `CONFLICT_UNRESOLVED` |
| **Specialist trả dữ liệu bất hợp lệ** | 0 lần | Coordinator áp dụng giá trị mặc định chuẩn schema (default safe verdict); ghi nhận cảnh báo. | `verification_completed` với mã `FALLBACK_APPLIED` |

### 5.2. Chiến lược Tối ưu hóa Hiệu quả Gọi Tool (Efficiency Strategy)
- **Per-Case In-Memory Cache:** Lưu đệm toàn bộ kết quả gọi MCP theo khóa `(case_id, tool_name, hash(arguments))`. Trong cùng 1 case, không bao giờ gọi 2 lần cùng một tool với tham số giống hệt nhau.
- **Gọi theo nhu cầu thực tế (Need-based Tool Discovery):**
  - Chỉ gọi `get_customer_history` khi case yêu cầu phân giải thực thể hoặc có cờ `include_customer_history: true`.
  - Chỉ gọi `get_product_context` khi khiếu nại liên quan trực tiếp đến sai mô tả hàng hoặc có cờ `include_product_context: true`.
  - Chỉ gọi `get_refund_timeline` khi `get_order_payments` cho thấy có dấu hiệu giao dịch hoàn tiền.
- **Kiểm soát ngân sách gọi (Call Budget):** Đảm bảo số lượt gọi MCP per case duy trì trong khoảng **4 đến 7 calls**, tuyệt đối không vượt quá ngưỡng tối đa để đạt trọn vẹn **5% điểm Efficiency**.
- **Không suy đoán dữ liệu (Zero Hallucination Guarantee):** Khi MCP không trả về dữ liệu, hệ thống ghi nhận giá trị rỗng/null hoặc `"insufficient_evidence"`, tuyệt đối không tự bịa đặt ID, mã hash hay số tiền.

---

## 6. Verification invariants

Trước khi chấp thuận kết quả từ Coordinator để xuất ra file `outputs/<case_id>.json`, Verifier bắt buộc kiểm định **10 điều kiện bất biến**:

1. **Schema Compliance:** Output khớp 100% với JSON Schema `day09-l3b-output-v2` (`contracts/schemas/l3b-output-v2.schema.json`), không thừa không thiếu trường bắt buộc.
2. **Case ID Integrity:** Giá trị `case_id` trong output phải trùng khớp tuyệt đối với `case_id` của input và các dòng trace liên quan.
3. **Entity Scope & Origin:** Mọi ID xuất hiện trong `affected_entities` (`order_ids`, `item_ids`, `seller_ids`, `payment_references`, `shipment_ids`) phải là dữ liệu thực trích xuất từ MCP response, không dùng ID giả định.
4. **Candidate Disjointness:** Tập hợp `resolved_order_ids` và `rejected_candidates` phải rời nhau hoàn toàn:
   $$\text{resolved\_order\_ids} \cap \text{rejected\_candidates} = \emptyset$$
5. **Evidence Ownership & Trace Parity:**
   - Mọi mã bằng chứng trong `evidence_refs` phải khớp regex `^ev_[A-Za-z0-9_-]{20,96}$`.
   - Tất cả các mã trong `output.evidence_refs` phải nằm trong tập hợp các `evidence_refs` đã được phát sinh qua sự kiện `tool_result_consumed` trong trace của chính case đó.
6. **Timeline & Responsibility Consistency:**
   - Nếu `shipment_analysis.verdict == "seller_delay"`, danh sách `late_seller_ids` không được rỗng.
   - Nếu `shipment_analysis.verdict == "on_time"`, danh sách `late_seller_ids` bắt buộc phải là `[]`.
7. **Financial Mathematics Coherence:**
   - Số tiền đề xuất hoàn không được vượt quá số tiền còn có thể hoàn:
     $$0 \le \text{recommended\_refund\_brl} \le \text{refundable\_total\_brl}$$
   - Tổng các dòng chi tiết hoàn tiền phải khớp với tổng tiền hoàn đề xuất:
     $$\left| \sum \text{refund\_lines[].amount\_brl} - \text{recommended\_refund\_brl} \right| < 0.01\text{ BRL}$$
8. **Case Status & Action Harmony:**
   - Nếu `case_status == "no_action"`, thì `recommended_refund_brl == 0` và `resolution_actions` không chứa hành động bồi hoàn hay xử lý kỷ luật đối tác.
   - Nếu `case_status == "action_required"`, bắt buộc phải có ít nhất 1 hành động trong `resolution_actions` hoặc `recommended_refund_brl > 0`.
9. **Primary Issue & Root Cause Alignment:** Vấn đề chính (`assessment.primary_issue`) phải đồng nhất về bản chất nghiệp vụ với nguyên nhân xếp hạng 1 trong `root_cause_analysis.ranked_causes[0]` và đối tượng liên quan trong `responsible_parties`.
10. **Calibrated Confidence Bounds:** Chỉ số `confidence` phải nằm trong đoạn $[0.0, 1.0]$. Nếu có xung đột dữ liệu chưa giải quyết (`unresolvable conflict`) hoặc `entity_resolution.status != "resolved"`, `confidence` bắt buộc phải $\le 0.60$.

---

## 7. Reproducibility

### 7.1. Cấu hình môi trường và Phiên bản công nghệ
- **Ngôn ngữ:** Python `>= 3.11`
- **Thư viện cốt lõi (Pinned Dependencies):**
  - `mcp>=2.0.0,<3.0.0`: Giao thức kết nối MCP Client.
  - `httpx2>=2.0.0,<3.0.0`: Client HTTP Async hỗ trợ streamable MCP.
  - `jsonschema[format]>=4.25.0,<5.0.0`: Kiểm định schema JSON theo chuẩn Draft 2020-12.
  - `python-dotenv>=1.1.0,<2.0.0`: Quản lý nạp biến môi trường từ `.env`.
- **Linter & Test:**
  - `pytest>=8.4.0`: Kiểm thử tự động.
  - `ruff>=0.12.0`: Phân tích tĩnh cú pháp code (quy tắc `E, F, I, UP, B, SIM`).

### 7.2. Tham số thực thi & Giới hạn tài nguyên
- **Mô hình thực thi:** Single-process Async Event Loop đảm bảo tính tất định (deterministic ordering) của các sự kiện ghi trong file trace.
- **Concurrency:** Tuần tự theo từng case (1 case tại một thời điểm; bên trong case có thể chạy đồng thời các specialist điều tra độc lập).
- **Randomness:** Không sử dụng các hàm sinh ngẫu nhiên thiếu kiểm soát. Các định danh sự kiện trace sinh bằng hàm băm URL-safe cố định độ dài (`evt_...`).
- **Mức tiêu thụ tài nguyên:** RAM $< 250\text{ MB}$, CPU $< 30\%$ trên môi trường máy trạm tiêu chuẩn.
- **Thời gian xử lý trung bình:** $\approx 0.8\text{s} - 1.5\text{s}$ trên mỗi case.

### 7.3. Quy trình các lệnh vận hành tiêu chuẩn
```bash
# 1. Kiểm tra tính toàn vẹn 100 cases đầu vào
day09 validate-inputs

# 2. Khám phá các công cụ MCP được cấp quyền
day09 mcp-tools

# 3. Chạy toàn bộ quy trình multi-agent giải quyết 100 cases
day09 run

# 4. Thẩm định output JSON và trace observable theo contracts
day09 validate

# 5. Đóng gói file nộp bài chuẩn quy cách
day09 package --output dist/submission.zip
```

### 7.4. Cam kết An toàn và Bảo mật (Security & Safety)
- **Không hardcode Secret:** File `.env` chứa `COMPETITION_TEAM_API_KEY` nằm trong danh mục `.gitignore`.
- **Rà soát tự động trước khi đóng gói:** Hàm `submission.validate_artifacts` tích hợp biểu thức chính quy quét toàn bộ output và trace, tự động chặn nếu phát hiện chuỗi khóa bí mật `sk-team-[A-Za-z0-9_-]{8,}`.
- **Giới hạn nộp bài:** File ZIP tạo ra chỉ chứa `manifest.json`, `trace.jsonl` và thư mục `outputs/*.json`, loại bỏ hoàn toàn source code, file `.env` và log thử nghiệm.
