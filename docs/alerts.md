# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

Rule nằm trong [`config/alert_rules.yaml`](../config/alert_rules.yaml), SLO nằm trong [`config/slo.yaml`](../config/slo.yaml). Cả ba runbook điều tra theo cùng thứ tự **Metrics → Logs → Traces**. Mỗi runbook có bước lọc log bằng Python, không cần cài thêm công cụ.

## Alert 1

- Tên: `chat_latency_p95_high`
- Severity: P2
- Duration: 5m
- Kênh thông báo: Slack `#k4-l3a-day13-oncall`
- SLI/SLO liên quan: `fast_successful_requests`, tức 99.5% request có `response_sent` với `latency_ms <= 1000` trong 28 ngày.
- Điều kiện và thời gian duy trì: P95 của `response_sent.latency_ms` trong cửa sổ 5 phút lớn hơn 1000 ms, và kéo dài liên tục 5 phút. Baseline warm là P95 khoảng 160 ms. Practice `rag_slow` đẩy latency lên khoảng 2666 ms.
- Ảnh hưởng tới người dùng: câu trả lời chậm rõ rệt. Latency phía client còn cao hơn nhiều so với `latency_ms` trong log, vì request phải xếp hàng chờ. Khi đo `rag_slow` với concurrency 5, client chờ khoảng 13.4 s. Mỗi request chậm đều tiêu error budget.
- Ba bước kiểm tra đầu tiên:
  1. **Metrics.** Mở panel Latency và so P95/P99 với TTFT P95. Nếu TTFT vẫn khoảng 55 ms mà latency tăng, thì phần chậm nằm trước bước generation (retrieval hoặc fetch prompt). Nếu TTFT cũng tăng, thì phần chậm nằm ở LLM. Ghi lại khoảng thời gian bị ảnh hưởng.
  2. **Logs.** Lấy các request chậm trong khoảng đó:
     `python -c "import json; [print(r['ts'], r['correlation_id'], r['latency_ms'], r['feature']) for r in map(json.loads, open('data/logs.jsonl')) if r.get('event')=='response_sent' and r['latency_ms']>1000]"`
  3. **Traces.** Trên Langfuse, lọc trace theo metadata `correlation_id` và so thời lượng của `retrieval`, `llm-generation` và `lab-agent-run`. Nếu root dài hơn nhiều so với tổng hai span con, thì thời gian đang bị tiêu vào bước fetch prompt, nằm giữa hai span con.
- Mitigation tạm thời:
  - Nếu `retrieval` chậm: chuyển sang trả lời bằng tài liệu fallback hoặc cache, giảm top-k, kiểm tra hoặc failover vector store.
  - Nếu `llm-generation` chậm: giảm `max_tokens` hoặc chuyển sang model nhanh hơn.
  - Nếu chậm do fetch prompt: giữ prompt đã cache, tăng `cache_ttl_seconds`.
- Owner: Đỗ Ngọc Phi (AI platform on-call)

## Alert 2

- Tên: `chat_error_rate_high`
- Severity: P1
- Duration: 2m
- Kênh thông báo: Slack `#k4-l3a-day13-oncall`
- SLI/SLO liên quan: `fast_successful_requests`, vì request lỗi không có `response_sent` nên bị tính là bad event. Ngoài ra có guardrail `error_rate_pct_max: 2` và `retrieval_success_rate_pct_min: 90`.
- Điều kiện và thời gian duy trì: tỉ lệ `request_failed / request_received` trong 5 phút lớn hơn 2%, kéo dài 2 phút. Duration ngắn hơn Alert 1 vì người dùng nhận HTTP 500 và không có câu trả lời nào. Ở mức 100% lỗi, error budget 28 ngày bị đốt hết trong khoảng 3.4 giờ.
- Ảnh hưởng tới người dùng: nhận HTTP 500 và không có câu trả lời. Practice `tool_fail` làm 10/10 request lỗi với `RuntimeError`.
- Ba bước kiểm tra đầu tiên:
  1. **Metrics.** Mở panel Errors và xem error rate, breakdown theo `error_type` và retrieval success. Nếu retrieval success giảm cùng lúc error rate tăng, thì lỗi nằm ở bước retrieval.
  2. **Logs.** Lấy các request lỗi:
     `python -c "import json; [print(r['ts'], r['correlation_id'], r['error_type'], r.get('tool_name'), r['payload'].get('detail')) for r in map(json.loads, open('data/logs.jsonl')) if r.get('event')=='request_failed']"`
  3. **Traces.** Mở trace có cùng `correlation_id` và tìm observation có level `ERROR`. Nếu `retrieval` lỗi và không có `llm-generation`, thì lỗi xảy ra trước khi gọi LLM.
- Mitigation tạm thời:
  - Nếu vector store timeout: tạm bỏ retrieval và trả lời bằng tài liệu fallback (kèm cảnh báo chất lượng), failover sang replica, thêm timeout và retry có giới hạn.
  - Nếu lỗi bắt đầu ngay sau một deploy hoặc sau khi đổi prompt label: rollback deploy hoặc prompt.
- Owner: Đỗ Ngọc Phi (AI platform on-call)

## Alert 3

- Tên: `chat_cost_per_request_spike`
- Severity: P3
- Duration: 15m
- Kênh thông báo: Slack `#k4-l3a-day13-oncall`
- SLI/SLO liên quan: guardrail `daily_cost_usd_max: 2.5` (panel Cost có threshold tổng ≤ 2.5 USD).
- Điều kiện và thời gian duy trì: cost trung bình mỗi `response_sent` trong 15 phút lớn hơn 0.0045 USD, tức khoảng 2 lần baseline 0.00227 USD, và kéo dài 15 phút. Cửa sổ dài vì cost không gây hỏng ngay, nên cần tránh báo động do vài câu trả lời dài lẻ tẻ. Practice `cost_spike` đẩy cost lên 0.00782 USD mỗi request (gấp 3.4 lần).
- Ảnh hưởng tới người dùng: câu trả lời dài bất thường, khó đọc hơn. Với LLM thật, câu trả lời dài hơn cũng làm tổng latency tăng; riêng FakeLLM trong lab sleep cố định nên latency không đổi. Về phía vận hành, ngân sách ngày sẽ bị dùng hết sớm.
- Ba bước kiểm tra đầu tiên:
  1. **Metrics.** So panel Cost với panel Tokens. Nếu `tokens_out` tăng mà `tokens_in` giữ nguyên, thì model đang sinh câu trả lời dài hơn. Nếu `tokens_in` tăng, thì prompt hoặc context đang dài hơn.
  2. **Logs.** Liệt kê các request tốn token nhất:
     `python -c "import json; rs=[r for r in map(json.loads, open('data/logs.jsonl')) if r.get('event')=='response_sent']; [print(r['ts'], r['correlation_id'], r['tokens_in'], r['tokens_out'], r['cost_usd']) for r in sorted(rs, key=lambda r: -r['tokens_out'])[:10]]"`
  3. **Traces.** Mở observation `llm-generation` của các request đó, kiểm tra usage, cost và **prompt name/version**. Nếu tất cả dùng một prompt version mới, thì prompt vừa đổi là nghi vấn chính.
- Mitigation tạm thời:
  - Rollback label `production` của prompt về version trước.
  - Đặt giới hạn `max_tokens` cho output.
  - Chuyển các feature ít quan trọng sang model rẻ hơn.
- Owner: Đỗ Ngọc Phi (AI platform on-call)
