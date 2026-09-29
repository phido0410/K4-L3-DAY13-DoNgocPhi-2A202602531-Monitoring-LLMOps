# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Đỗ Ngọc Phi
- **MSSV:** 2A202602531
- **Lớp:** K4-L3A
- **Repository URL:** https://github.com/phido0410/K4-L3-DAY13-DoNgocPhi-2A202602531-Monitoring-LLMOps
- **Commit SHA cuối:** `983d44b919b517e3079063ecf3b3747912bf7963` — commit chứa toàn bộ source, config và evidence. Commit ngay sau đó chỉ ghi SHA vào dòng này, không đổi nội dung nào khác.
- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1`
- **Tên project Langfuse cá nhân:** `day13-k4-l3a-2A202602531`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | [`evidence/01-pytest.txt`](evidence/01-pytest.txt) |
| Log validator | [`evidence/02-log-validator.txt`](evidence/02-log-validator.txt) |
| Dashboard validator | [`evidence/03-dashboard-validator.txt`](evidence/03-dashboard-validator.txt) |
| Structured log | [`evidence/04-structured-log.txt`](evidence/04-structured-log.txt) |
| PII redaction | [`evidence/05-pii-redaction.txt`](evidence/05-pii-redaction.txt) |
| Trace list | [`evidence/06-trace-list.png`](evidence/06-trace-list.png) |
| Trace waterfall | [`evidence/07-trace-waterfall.png`](evidence/07-trace-waterfall.png) |
| Trace metadata | [`08a-trace-metadata-root.png`](evidence/08a-trace-metadata-root.png) · [`08b-trace-metadata-generation.png`](evidence/08b-trace-metadata-generation.png) |
| Prompt versions | [`evidence/09-prompt-versions.png`](evidence/09-prompt-versions.png) |
| Prompt rollback | Trước: [`09-prompt-versions.png`](evidence/09-prompt-versions.png) · Sau promote: [`10b-promoted.png`](evidence/10b-promoted.png) · Sau rollback: [`10c-rolled-back.png`](evidence/10c-rolled-back.png) |
| Dashboard runtime | [`evidence/11-dashboard-overview.png`](evidence/11-dashboard-overview.png) |
| Incident metric | [`evidence/12-incident-metric.png`](evidence/12-incident-metric.png) |
| Incident log | [`evidence/13-incident-log.txt`](evidence/13-incident-log.txt) |
| Incident trace | [`evidence/14-incident-trace.png`](evidence/14-incident-trace.png) |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 (thiếu `correlation_id`, thiếu enrichment) | 100/100 | Baseline: [`00-baseline.txt`](evidence/00-baseline.txt); cuối: [`02-log-validator.txt`](evidence/02-log-validator.txt) |
| `validate_dashboard.py` | 6/6 panel | 6/6 panel | Contract có sẵn nên đạt từ đầu; dashboard runtime là [`scripts/dashboard.py`](../scripts/dashboard.py) |
| `pytest` | 22 passed | 31 passed | +9 test: PII (CCCD, thẻ), correlation ID/context leak/scrub pipeline, child observations |
| Số traces hợp lệ | 0 (chưa cấu hình Langfuse key) | 82 root traces | Các trace từ CP2 có đủ `retrieval` + `llm-generation` (trừ request `tool_fail`, dừng ở retrieval) |
| Số PII leak | 0 | 0 | Baseline 0 là nhờ `summarize_text`; `scrub_event` thêm lớp bảo vệ cho mọi `payload` |
| Latency P95 / TTFT P95 | 160 ms / 55 ms (10 requests) | 161 ms / 55 ms | Sau fix CP3, cùng 5 query challenge; lúc sự cố P95 = 2668 ms |
| Retrieval success rate | 100% (10/10) | 100% | Practice `tool_fail` làm giảm còn 83.9% trên dashboard CP2 |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** `CorrelationIdMiddleware` ([`app/middleware.py`](../app/middleware.py)) chạy đầu tiên với mọi request:
  1. Gọi `clear_contextvars()` để xóa context của request trước. Không có bước này, worker xử lý request mới vẫn giữ `correlation_id`/`session_id` cũ và log sẽ bị gán nhầm request.
  2. Đọc header `x-request-id`: nếu đúng format `req-<8 hex>` thì giữ nguyên để nối với hệ thống gọi tới; nếu thiếu hoặc sai format thì sinh mới `req-` + 8 ký tự đầu của `uuid4().hex`. Tôi chọn chỉ nhận đúng format để client không chèn được chuỗi tùy ý vào log; đánh đổi là ID của hệ thống ngoài có format khác sẽ bị thay bằng ID mới.
  3. `bind_contextvars(correlation_id=...)` nên mọi dòng log trong request tự có ID, đồng thời lưu vào `request.state` để `/chat` trả trong body và truyền vào `LabAgent.run` (ghi vào trace metadata ở CP2).
  4. Trả lại ID qua header `x-request-id` và thời gian xử lý qua `x-response-time-ms`.
- **Các metadata được ghi vào structured log:** ngoài `ts`, `level`, `service`, `event`, `correlation_id`, endpoint `/chat` ([`app/main.py`](../app/main.py)) bind trước log `request_received`: `user_id_hash` (SHA-256 cắt 12 ký tự, không ghi `user_id` gốc), `session_id`, `feature`, `model`, `env`. Vì bind vào context nên cả `request_received`, `response_sent` và `request_failed` đều có cùng bộ metadata mà không phải truyền tay từng dòng. `response_sent` thêm `latency_ms`, `ttft_ms`, `tokens_in`, `tokens_out`, `cost_usd`, `quality_score`, `tool_name`, `tool_success` — đây là các field dashboard dùng.
- **Cách bảo đảm PII được scrub trước khi ghi:** có hai lớp:
  1. Nội dung người dùng không được log nguyên văn mà qua `summarize_text()` — scrub rồi cắt còn 80 ký tự (`message_preview`, `answer_preview`).
  2. Processor `scrub_event` được đăng ký trong chuỗi structlog ([`app/logging_config.py`](../app/logging_config.py)) **sau** `merge_contextvars`/`TimeStamper` và **trước** `JsonlFileProcessor`/`JSONRenderer`, nên mọi chuỗi trong `payload` và `event` được che trước khi serialize và ghi file. Lớp này bắt cả các giá trị không đi qua `summarize_text`, ví dụ `payload.detail` chứa message của exception.

  Rule trong [`app/pii.py`](../app/pii.py): email, điện thoại Việt Nam (`0`/`+84` và 9 chữ số, cho phép khoảng trắng/`.`/`-`), CCCD 12 chữ số, thẻ thanh toán 16 chữ số (liền hoặc cách bằng khoảng trắng/`-`). Giá trị bị thay bằng `[REDACTED_<LOẠI>]`.
- **Cách kiểm chứng kết quả:**
  - Baseline: `validate_logs.py` đạt 30/100 — 20/21 dòng log có `correlation_id=MISSING` và thiếu enrichment ([`evidence/00-baseline.txt`](evidence/00-baseline.txt)).
  - Vì validator đọc toàn bộ `data/logs.jsonl`, tôi chuyển log baseline ra khỏi repo, restart API, chạy lại `load_test.py` và gửi thêm 2 request chứa PII giả (email, SĐT, CCCD, thẻ). Kết quả: 100/100, 0 PII leak, 12 correlation ID khác nhau trên 25 dòng log ([`evidence/02-log-validator.txt`](evidence/02-log-validator.txt)).
  - Log của cùng một request có chung `correlation_id` và đủ metadata ([`evidence/04-structured-log.txt`](evidence/04-structured-log.txt)); log đầu ra hiện `[REDACTED_EMAIL]`, `[REDACTED_PHONE_VN]`, `[REDACTED_CCCD]`, `[REDACTED_CREDIT_CARD]` ([`evidence/05-pii-redaction.txt`](evidence/05-pii-redaction.txt)).
  - Tests: [`tests/test_pii.py`](../tests/test_pii.py) kiểm tra từng loại PII; [`tests/test_correlation_logging.py`](../tests/test_correlation_logging.py) kiểm tra sinh/nhận ID, header, enrichment, không rò context giữa hai request liên tiếp và PII bị che trong file log (gọi logger trực tiếp với `payload.detail`, không qua `summarize_text`, nên chứng minh được `scrub_event` hoạt động — khi tạm bỏ `scrub_event` khỏi processor chain, đúng test này fail). Toàn bộ 29 tests pass.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** traces nằm trong project `day13-k4-l3a-2A202602531` (breadcrumb trong ảnh), được tạo bằng key của chính project này qua `load_test.py` và các request thủ công. `correlation_id` trong metadata của trace khớp với dòng log tương ứng trong `data/logs.jsonl` trên máy tôi.
- **Cấu trúc root/retrieval/generation observations:**
  - `lab-agent-run` (AGENT, root, `@observe` trên `LabAgent.run`) chứa metadata: `correlation_id`, `feature`, `model`, `prompt_name/label/version/source`, `doc_count`, `query_preview` (đã scrub).
  - `retrieval` (RETRIEVER, `@observe` trên `retrieve()` trong [`app/mock_rag.py`](../app/mock_rag.py)): không capture input vì là message người dùng có thể chứa PII, có capture output vì là tài liệu corpus.
  - `llm-generation` (GENERATION, `@observe` trên `FakeLLM.generate()` trong [`app/mock_llm.py`](../app/mock_llm.py)): `update_current_generation` ghi `model`, `usage_details` (input/output), `cost_details` (input/output/total, cùng bảng giá với `cost_usd` trong log), `completion_start_time` (để Langfuse tính TTFT). Prompt version được link tự động nhờ `propagate_attributes(prompt=...)`. Không capture prompt/output thô.
  - Ví dụ trace `37789723cac4772a4ba3b4937361e888` (đợt practice `rag_slow`): root 2.76s = `retrieval` 2.50s + `llm-generation` 202ms ([`07-trace-waterfall.png`](evidence/07-trace-waterfall.png)).
- **Cách nối trace với log:** middleware sinh `correlation_id`, bind vào structlog context và truyền vào `LabAgent.run`, rồi `propagate_attributes(metadata={"correlation_id": ...})` gắn nó vào mọi observation của trace. Kiểm chứng với `req-d49ee7e9`:

  | Trường | Log `response_sent` | Trace `37789723…` |
  |---|---|---|
  | latency | `latency_ms: 2762` | 2.76s |
  | cost | `cost_usd: 0.002076` | $0.002076 |
  | tokens | 32 in + 132 out | 164 tokens |
  | TTFT | `ttft_ms: 54` | metadata `ttft_ms: 54` |
  | session / user | `s02` / `95b6504a8bd6` | `s02` / `95b6504a8bd6` |

  Ảnh metadata: [`08a`](evidence/08a-trace-metadata-root.png) (root), [`08b`](evidence/08b-trace-metadata-generation.png) (generation). Dòng `scope.attributes.public_key` mà SDK tự thêm đã được che.
- **Prompt name:** `day13-chat` (text prompt, biến `{{feature}}`, `{{docs}}`, `{{message}}`)
- **Version/label baseline:** v1 — labels `production`, `baseline`
- **Version/label candidate:** v2 — label `candidate` (thêm dòng `Answer in at most 3 sentences and only use the Docs above.`)
- **Trace ID của mỗi version:** cùng input `What is your refund policy?`
  - `baseline` → v1: trace `3c3ad4e77ffc86957806baab5ef200e6`, correlation `req-ba5e0001`, tokens in/out 28/163, cost $0.002529
  - `candidate` → v2: trace `7dd07bebf61a8c3dc835e23b2102bacc`, correlation `req-cad10001`, tokens in/out 42/86, cost $0.001416 (input +14 tokens do dòng thêm vào prompt)
- **Cách promote và rollback `production`:** trên Langfuse UI, mở **Prompt labels** của version cần đưa lên và tick `production`. Langfuse tự gỡ label khỏi version cũ, vì mỗi label chỉ gắn với một version. Code không đổi gì: app luôn fetch theo `LANGFUSE_PROMPT_LABEL=production`. Cùng input `What is your refund policy?`:

  | Trạng thái | `production` trỏ tới | Correlation ID | Trace ID | tokens_in |
  |---|---|---|---|---:|
  | Trước | v1 | `req-ba5e0001` (label `baseline`, cùng v1) | `3c3ad4e77ffc86957806baab5ef200e6` | 28 |
  | Sau promote | v2 | `req-9f0d0002` | `3674bf3e82b595fef7ee9150f4f1800d` | 42 |
  | Sau rollback | v1 | `req-9f0d0003` | `97a1e24546b15e28d3abd84053cc2775` | 28 |

  Ở cả ba trace, `prompt_label`/`prompt_version` trong metadata của root và prompt link trên observation `llm-generation` đều khớp với version mà `production` đang trỏ tới. Lưu ý vận hành: SDK cache prompt 60 giây (`cache_ttl_seconds=60`), nên sau khi đổi label, process đang chạy có thể vẫn dùng version cũ tới 60 giây. Để kiểm chứng ngay, tôi restart API trước mỗi request.

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** [`scripts/dashboard.py`](../scripts/dashboard.py) (Streamlit, chạy bằng `streamlit run scripts/dashboard.py`) đọc `data/logs.jsonl` và lấy toàn bộ tên panel, unit, threshold, time range 60 phút và refresh 30 s từ [`config/dashboard.yaml`](../config/dashboard.yaml), nên dashboard không lệch khỏi contract.
  - Sáu panel: Latency P50/P95/P99 + TTFT P95 (ms), Traffic (request/phút), Error rate + retrieval success + breakdown theo `error_type` (%), Cost theo phút và lũy kế (USD), Input/output tokens lũy kế, Quality proxy (0–1).
  - Mỗi panel có đường threshold nét đứt và ô trạng thái "Đạt/Vi phạm" (icon + chữ, không chỉ dựa vào màu).
  - Percentile dùng chung hàm `app.metrics.percentile` với endpoint `/metrics`, nên số trên dashboard khớp với API.
  - Kiểm chứng runtime: khi bật 3 practice incident, error rate lên 16.1% (vi phạm), retrieval success giảm còn 83.9%, output tokens tăng ([`11-dashboard-overview.png`](evidence/11-dashboard-overview.png)). Ở CP3, P95 tăng vọt lên 2668 ms ([`12-incident-metric.png`](evidence/12-incident-metric.png)).
- **SLO và lý do chọn:** `fast_successful_requests` trong [`config/slo.yaml`](../config/slo.yaml): 99.5% request có `response_sent` với `latency_ms <= 1000` trong 28 ngày.
  - Tôi hạ ngưỡng từ 3000 ms xuống 1000 ms dựa trên số đo: baseline warm có P50/P95 khoảng 160 ms, còn practice `rag_slow` cho `latency_ms` khoảng 2666 ms. Với ngưỡng 3000 ms, sự cố gấp khoảng 16 lần bình thường vẫn được tính là "good", nên SLO không phát hiện được. 1000 ms cao hơn P95 warm khoảng 6 lần nên không báo động giả, nhưng bắt được `rag_slow` (và cả sự cố của challenge).
  - Request lỗi không có `response_sent` nên tự động là bad event, vì vậy SLO bao cả latency lẫn availability.
  - Tôi giữ nguyên threshold 3000 ms trong `dashboard.yaml` vì tài liệu yêu cầu không đổi contract. CP3 cho thấy đúng khoảng hở này: dashboard báo "Đạt" trong khi SLO bị vi phạm.
- **Cách tính error budget:** budget = 100% − 99.5% = **0.5%** số request trong cửa sổ 28 ngày.
  - Ở tải 1 request/phút: 28 × 24 × 60 = 40 320 request, nên được phép tối đa **201 bad request**.
  - Quy ra thời gian: 0.5% × 672 giờ = **3.36 giờ** nếu toàn bộ traffic hỏng. Vì vậy alert error rate có duration ngắn (2 phút): ở mức 100% lỗi, budget cạn sau khoảng 3.4 giờ.
  - Một đợt `rag_slow` 30 phút ở tải đó tiêu 30 bad request, tương đương khoảng 15% budget.
- **Ba alert và runbook tương ứng:** trong [`config/alert_rules.yaml`](../config/alert_rules.yaml), đều symptom-based, gửi Slack `#k4-l3a-day13-oncall`, owner là tôi (AI platform on-call). Runbook ở [`docs/alerts.md`](../docs/alerts.md), mỗi runbook có 3 bước Metrics → Logs → Traces kèm lệnh lọc log đã chạy thử.

  | Alert | Điều kiện | Duration | Severity | Ngưỡng dựa trên |
  |---|---|---|---|---|
  | `chat_latency_p95_high` | P95 `latency_ms` > 1000 ms (5m) | 5m | P2 | SLO; `rag_slow` khoảng 2666 ms |
  | `chat_error_rate_high` | `request_failed/request_received` > 2% (5m) | 2m | P1 | Guardrail 2%; `tool_fail` làm 10/10 request lỗi |
  | `chat_cost_per_request_spike` | cost trung bình/request > $0.0045 (15m) | 15m | P3 | Khoảng 2× baseline $0.00227; `cost_spike` đẩy lên $0.00782 |

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1` (cohort K4, seed 1311, 5 query feature `monitoring`, `latency_threshold_ms: 2000`). File `config/challenge.json` chỉ nằm trên máy, đã `.gitignore`, không commit.
- **Khoảng thời gian điều tra:** 29/09/2026, giờ địa phương UTC+7:
  - 16:42:45: chạy baseline, cùng 5 query challenge, chưa bật sự cố;
  - 16:43:02: `inject_incident.py` bật sự cố và chạy `load_test.py --challenge --concurrency 5`, 5 request chậm kết thúc lúc 16:43:15;
  - 16:44:19: tắt sự cố (fix), rồi chạy lại cùng bộ query để kiểm chứng.

  Trước khi chạy, tôi chuyển log practice sang chỗ khác và restart API, để dashboard và `/metrics` chỉ chứa dữ liệu của challenge.
- **Triệu chứng từ metrics:** panel Latency ([`12-incident-metric.png`](evidence/12-incident-metric.png)): P95 `response_sent.latency_ms` tăng từ **161 ms lên 2668 ms** (×16.6) ở bucket 16:43, rồi về 161 ms ở 16:44.
  - TTFT P95 giữ nguyên **55 ms**, error rate 0%, retrieval success 100%, cost và tokens không đổi đáng kể. Vậy LLM không chậm và không có lỗi; phần chậm nằm trước bước generation.
  - 2668 ms vượt ngưỡng challenge (2000 ms) và SLO `latency_ms <= 1000` của tôi. Threshold 3000 ms của contract dashboard vẫn báo "Đạt", nên threshold này không đủ nhạy (xem preventive measure).
  - Điểm khoảng 1460 ms ở bucket 16:42 là request warm-up `req-00000000` bị cold start khi fetch prompt, không thuộc sự cố.
- **Log line và correlation ID liên quan:** ([`13-incident-log.txt`](evidence/13-incident-log.txt))
  - Lọc `response_sent` có `latency_ms > 2000` được đúng 5/5 request challenge (2659–2668 ms), tất cả có `tool_success: true` và `ttft_ms` 50–55.
  - Ngay trước triệu chứng có log `incident_enabled` (`rag_slow`) lúc 09:43:02.221Z. Đây là manh mối "cái gì vừa thay đổi".
  - Request được chọn: **`req-25e63ea0`**, `response_sent` lúc `2026-09-29T09:43:05.002814Z` với `latency_ms: 2667`, `ttft_ms: 52`, `feature: monitoring`, `session_id: k4-l3a-challenge-s01`.
- **Trace ID và span gây ảnh hưởng:** trace **`3e52dd915bc140101bfd7fa65c6b9afa`**, cùng `correlation_id: req-25e63ea0` trong metadata ([`14-incident-trace.png`](evidence/14-incident-trace.png)):

  | Observation | Bắt đầu | Thời lượng |
  |---|---:|---:|
  | `lab-agent-run` (root) | +0 ms | 2668 ms |
  | **`retrieval`** | +1 ms | **2506 ms (94%)** |
  | `llm-generation` | +2509 ms | 159 ms |

  Span `retrieval` gây ảnh hưởng. Nó có level `DEFAULT` (không lỗi), nghĩa là dependency chậm chứ không hỏng. Prompt vẫn là `day13-chat` v1 `production`, nên có thể loại trừ nguyên nhân do đổi prompt.
- **Root cause:** bước retrieval (vector store) bị chậm khoảng 2.5 s mỗi request. Trong lab, incident `rag_slow` được bật qua control endpoint, và nó làm `retrieve()` ([`app/mock_rag.py`](../app/mock_rag.py)) sleep 2.5 s trước khi trả tài liệu. Cả ba lớp đều chỉ về cùng một nguyên nhân: metric (latency tăng, TTFT không đổi), log (`tool_success: true` nhưng `latency_ms` khoảng 2667, có `incident_enabled` ngay trước) và trace (`retrieval` chiếm 94%).

  Sự cố còn bị **khuếch đại** ở phía client, từ 2.67 s lên **13.35 s**: `/chat` là `async def` nhưng gọi code đồng bộ có `time.sleep`, nên event loop bị chặn. 5 request "đồng thời" bị xử lý tuần tự (các `response_sent` cách nhau đều khoảng 2.66 s). `latency_ms` trong log chỉ đo bên trong `agent.run`, nên không thấy thời gian xếp hàng này.
- **Fix action:** tắt nguồn gây chậm (`inject_incident.py --disable`), tương đương việc vector store đã phục hồi hoặc được chuyển sang replica. Kiểm chứng bằng cùng 5 query challenge ngay sau fix: P50 159 ms, P95 **161 ms**, client khoảng 813 ms, bằng baseline (mục 4 trong [`13-incident-log.txt`](evidence/13-incident-log.txt)).
- **Preventive measure:**
  1. **Alert theo SLO thay vì threshold dashboard:** `chat_latency_p95_high` (P95 > 1000 ms trong 5 phút, P2, [`config/alert_rules.yaml`](../config/alert_rules.yaml)) sẽ bắt được sự cố này. Threshold 3000 ms của contract thì không. Runbook Alert 1 trong [`docs/alerts.md`](../docs/alerts.md) chính là các bước điều tra ở trên. *Đã cấu hình.*
  2. **Timeout và fallback cho retrieval:** đặt timeout khoảng 500 ms (gấp nhiều lần mức bình thường dưới 5 ms) cho lời gọi vector store. Khi quá hạn, trả lời bằng tài liệu fallback và gắn cờ để quality proxy phản ánh. Thêm circuit breaker để tạm ngừng gọi khi vector store chậm liên tục. *Đề xuất, chưa triển khai.*
  3. **Đưa thời lượng retrieval vào log:** thêm field `retrieval_ms` vào `response_sent`, và đặt alert riêng cho latency của observation `retrieval`. Như vậy chỉ cần metric và log là đã khoanh vùng được, không phải chờ mở trace. *Đề xuất.*
  4. **Không chặn event loop:** chạy `agent.run` trong threadpool (đổi `/chat` thành `def` hoặc dùng `run_in_threadpool`), để một dependency chậm không làm các request khác phải xếp hàng. Đồng thời đo latency ở middleware (`x-response-time-ms`) để thấy đúng latency người dùng chịu. *Đề xuất.*

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:** chọn ngưỡng SLO bằng **số đo** thay vì giữ giá trị mặc định. Trước khi viết SLO và alert, tôi chạy cả 3 practice incident và đo `latency_ms`, error rate, cost. Kết quả cho thấy ngưỡng 3000 ms không phát hiện được `rag_slow` (khoảng 2666 ms), nên tôi hạ xuống 1000 ms. Các ngưỡng alert cũng lấy từ số đo: cost/request gấp 2 baseline, error rate khớp guardrail. CP3 xác nhận quyết định này đúng: sự cố challenge (P95 2668 ms) vi phạm SLO 1000 ms nhưng dashboard với threshold 3000 ms vẫn báo "Đạt".
- **Một lỗi/blocker đã gặp:** khi kiểm chứng trace bằng API, `GET /api/public/traces` của Langfuse trả **HTTP 410 `LEGACY_API_UNAVAILABLE_FOR_NEW_ORGANIZATION`**, vì organization tạo sau 16/09/2026 không còn được dùng legacy API. Ngoài ra còn một blocker nhỏ: sau khi sửa CP1, `validate_logs.py` vẫn báo lỗi vì nó đọc cả các dòng log từ trước khi sửa.
- **Cách tìm nguyên nhân và xử lý:** body lỗi 410 chỉ rõ endpoint thay thế. Tôi đọc SDK đã cài (`langfuse.api.observations.get_many`, có các nhóm field `core,basic,metadata,usage,prompt,...`), rồi chuyển sang `GET /api/public/v2/observations` và lọc theo `metadata.correlation_id`. Cách này dùng lại được ở CP2 (lấy trace ID của các prompt version) và CP3 (tìm trace của `req-25e63ea0`). Với validator, tôi lưu output baseline ([`00-baseline.txt`](evidence/00-baseline.txt)), chuyển log cũ ra khỏi repo, restart API rồi đo lại.
- **Cách hiểu luồng Metrics → Logs → Traces:**
  - **Metrics** trả lời "có vấn đề gì và từ khi nào": ở CP3, P95 tăng ×16.6 ở bucket 16:43 trong khi TTFT và error rate không đổi, tức là chậm chứ không lỗi, và chậm trước bước LLM.
  - **Logs** trả lời "request nào": lọc `latency_ms > 2000` ra 5 request, chọn `req-25e63ea0`, và thấy `incident_enabled` ngay trước đó.
  - **Traces** trả lời "bước nào": trace có cùng `correlation_id` cho thấy `retrieval` chiếm 94% thời gian.

  `correlation_id` là "khóa nối" giữa log và trace. Chỉ khi cả ba lớp cùng chỉ về một nguyên nhân thì mới kết luận root cause, và việc kiểm chứng fix cũng quay lại metric (P95 về 161 ms).
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:**
  - **Prompt version và label:** tách việc deploy prompt khỏi deploy code. Đổi `production` từ v1 sang v2 rồi rollback không cần sửa hay restart code (chỉ cần chờ cache 60 s). Mỗi generation ghi lại prompt version, nên khi cost hoặc chất lượng thay đổi có thể quy về đúng version.
  - **Token và cost:** v2 thêm 1 dòng làm `tokens_in` tăng từ 28 lên 42 cho cùng input, tức prompt dài hơn thì tốn tiền hơn ở mọi request. Theo dõi tokens và cost theo phút giúp phát hiện `cost_spike` (×3.4) trước khi vượt ngân sách ngày.
  - **SLO và error budget:** biến "hệ thống chạy ổn không" thành con số có thể quyết định: còn budget thì được phép release hoặc thử prompt mới, hết budget thì ưu tiên sửa độ ổn định.
- **Điều quan trọng nhất đã học:** số liệu phía server có thể "đẹp" trong khi người dùng đang chịu trận. Ở CP3, log ghi `latency_ms` khoảng 2.7 s nhưng client chờ **13.35 s**, vì `/chat` là `async def` gọi code đồng bộ nên chặn event loop và 5 request phải xếp hàng. Muốn đo đúng trải nghiệm người dùng thì phải đo ở biên (middleware hoặc client), không chỉ trong hàm xử lý. Threshold cũng phải được kiểm chứng bằng sự cố thật, chứ không chỉ để có cho đủ.
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:**
  - Chưa sửa lỗi chặn event loop (đề xuất đổi `/chat` sang `def` hoặc dùng `run_in_threadpool`), vì không phải TODO và tôi muốn giữ nguyên hành vi khi chạy challenge. Các preventive measure 2–4 ở mục 7 (timeout/fallback retrieval, `retrieval_ms` trong log, alert theo span) mới là đề xuất.
  - Alert mới định nghĩa trong YAML, chưa nối với hệ thống gửi Slack thật.
  - Quality proxy là heuristic (độ dài, có docs hay không), chưa phải đánh giá chất lượng thật.
  - Chưa làm phần bonus.

## 9. Checklist trước khi nộp

- [x] Kết quả và evidence thuộc commit SHA cuối.
- [x] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [x] Incident evidence nối đúng metric → log → trace.
- [x] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [x] Repository chạy lại được theo README.
- [x] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
