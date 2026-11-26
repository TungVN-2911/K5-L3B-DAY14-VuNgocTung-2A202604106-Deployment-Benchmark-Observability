# Benchmark & Observability Report — Day 14

**Họ tên:** ...
**Ngày chạy:** 26/11/2026 (Bước 1 — develop)
**Môi trường:** Windows 11, Python 3.12.10 (venv), agent chạy native (1 process uvicorn mỗi phiên bản), load generator chạy trên cùng máy

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Mock LLM trả lời trong ~120–230 ms, nên 500 ms chừa đủ chỗ cho retrieval và jitter. Đặt theo p95 để tail latency (request chậm ~1.5 s) không bị giá trị trung bình che mất |
| Error rate `/ask` | < 2 % | Upstream mock lỗi ~1% (`MOCK_ERROR_RATE=0.01`). 2% cho error budget gấp đôi mức nền, vượt ngưỡng nghĩa là có sự cố thật |
| Accuracy trên golden dataset | ≥ 80 % (gate mặc định), 100 % cho bản release cuối | 80% chặn được bản tệ rõ rệt như v1 (4.3%). Bản sau khi sửa KB phải đạt 100% và không có regression |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

Nguồn: `reports/load_v2_c{1,10,50,100}.json` (300 request mỗi mức).

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 3.97 | 199.8 | 234.3 | 1716.5 | 0.33% | ✅ PASS |
| 10 | 38.31 | 199.3 | 447.9 | 1726.0 | 1.33% | ✅ PASS |
| 50 | 95.2 | 201.8 | 482.0 | 1701.9 | 1.67% | ✅ PASS |
| 100 | 56.25 | 603.1 | 3366.6 | 3897.1 | 0.33% | ❌ FAIL (p95) |

**Nhận xét:** RPS tăng gần tuyến tính từ 1 → 10 (×9.6), vì mỗi request chủ yếu là `await asyncio.sleep` (I/O-bound), event loop xử lý song song được. Từ 10 → 50 chỉ tăng ×2.5, và p95 tiến sát 500 ms. Tới 100 thì RPS **giảm** còn 56 req/s, p50 vọt lên 603 ms, p95 lên 3.4 s: chỉ có 1 process / 1 event loop, nên overhead CPU (parse JSON, middleware metrics, logging) cộng với load generator chạy chung máy làm request phải xếp hàng. Concurrency vượt quá điểm bão hoà (~50) chỉ làm tăng latency do xếp hàng chứ không tăng throughput. Muốn hơn phải scale ngang (nhiều worker/instance), xem mục 5.

### 2.2 Tail latency

Nguồn: `reports/load_v2_slow_{0,0.03,0.1}.json` (300 request, concurrency 20).

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 206.5 | 433.8 | 440.0 |
| 0.03 (mặc định) | 237.2 | 441.7 | 1684.8 |
| 0.1 | 343.6 | 1699.0 | 1914.9 |

**Nhận xét:** p99 nhạy nhất: chỉ 3% request chậm đã kéo p99 từ 440 ms lên 1685 ms (×3.8), trong khi avg chỉ tăng 15% (206 → 237 ms) và p95 gần như không đổi. Ở 10% request chậm, p95 cũng vượt SLO (1699 ms), còn avg vẫn chỉ 344 ms, trông "ổn". SLO không nên đặt theo average vì average trộn lẫn đa số request nhanh với số ít request rất chậm, nên che mất trải nghiệm tệ của 3–10% người dùng. Percentile đo trực tiếp đúng nhóm người dùng đó.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

Nguồn: `reports/eval_v1.json`, `reports/eval_v2.json`, `reports/eval_v2_fixed.json` (golden dataset 23 câu).

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 58.4 | 109.0 | 116.5 |
| Tổng cost (USD) | 0.000423 | 0.000759 | 0.000815 |
| Cost / câu đúng (USD) | 0.00042255 | 0.00003616 | 0.00003544 |
| Quality gate | FAIL (≥ 80%) | PASS (≥ 80%, baseline v1) | PASS (≥ 100%, baseline v2, 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| security-02 ("JWT khác gì API key trong xác thực?") | `token`, `hết hạn`, `chữ ký` | Thêm entry `KNOWLEDGE_BASE` với trigger `jwt`, `api key`, `xác thực`: API key cố định, không tự hết hạn; JWT là token có claims `exp` và chữ ký số |
| scaling-03 ("Kubernetes HPA scale dựa trên những chỉ số nào?") | `cpu`, `memory`, `custom metrics` | Thêm entry với trigger `kubernetes`, `hpa`, `autoscal`: HPA scale theo CPU, memory hoặc custom metrics |

Trước khi thêm, đã kiểm tra không câu nào khác trong `golden_dataset.jsonl` chứa các trigger mới, nên retrieval của 21 câu cũ không đổi (0 regression). Cùng thay đổi đã chép sang `production/utils/mock_llm.py` để stack Docker ở Bước 2 cũng đạt 100%.

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

v2 tốn gần gấp đôi token mỗi câu (109 so với 58.4) vì prompt có thêm context retrieval, tổng cost tăng 79%, và p95 eval tăng khoảng 31 ms (200.6 → 232.0 ms) do thêm bước retrieval. Đổi lại, accuracy tăng từ 4.3% lên 91.3%, nên **cost / câu đúng giảm ~11.7 lần** (0.00042 → 0.000036 USD). Tính theo câu trả lời hữu ích thì v2 rẻ hơn hẳn, vì vậy "cost / câu đúng" mới là chỉ số đúng để so hai phiên bản. Bản sửa KB tăng thêm 7.5 token/câu nhưng cost / câu đúng còn giảm nhẹ.

Lưu ý: p95 của `eval_v2_fixed.json` là 1569.6 ms vì với 23 mẫu, chỉ 1 request rơi vào nhóm slow 3% là đủ kéo p95 lên. Đây là nhiễu của mock (`MOCK_SLOW_RATE`), không phải do thay đổi KB. Latency nên đo bằng load test 300 request, không đo bằng eval.

### Quality gate trong CI (Exercise 7.3)

`run_eval.py` trả **exit code 1** khi accuracy dưới `--min-accuracy` hoặc có regression so với `--baseline`, và **0** khi đạt. Đã kiểm tra: eval v1 với `--baseline reports/eval_v2.json` trả exit code **1** (bị chặn); eval cuối của v2 trả **0**. Trong CI, bước nào exit khác 0 thì job fail, và nếu bật branch protection "Require status checks to pass" thì PR không merge được:

```yaml
# .github/workflows/eval.yml
name: quality-gate
on: pull_request
jobs:
  eval:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: 06-lab-complete/benchmark-observability/develop
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r requirements.txt
      - name: Start agent v2
        run: |
          AGENT_VERSION=v2 PORT=8002 python app.py &
          for i in $(seq 1 30); do curl -sf localhost:8002/health && break; sleep 1; done
      - name: Eval quality gate (exit 1 → chặn merge)
        run: python eval/run_eval.py --url http://localhost:8002 --min-accuracy 1.0 --baseline reports/eval_v2.json
```

---

## 4. Observability stack (production)

Stack chạy bằng `docker compose -p k5-day14-observability`, tải nền bằng Locust 30 user / ramp 5 (Exercise 7.4). Ảnh trong `screenshots/`.

> Ghi chú khi dựng stack: image agent ban đầu crash (`ModuleNotFoundError: No module named 'uvicorn'`), vì user `agent` có HOME là `/app` nên Python tìm user site ở `/app/.local`, còn package được copy vào `/home/agent/.local`. Đã sửa `production/Dockerfile` bằng cách thêm `ENV PYTHONUSERBASE=/home/agent/.local`.

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải: `screenshots/grafana-dashboard.png`
- [x] Một trace chậm trong Jaeger: `screenshots/jaeger-slow-trace.png`
- [x] Một trace lỗi trong Jaeger (có event `exception`): `screenshots/jaeger-error-trace.png`
- [x] Trang Alerts của Prometheus với 2 alert đang **firing** (`AgentHighErrorRate`, `AgentHighLatencyP95`): `screenshots/prometheus-alert-firing.png`

### Exercise 7.4: Trả lời câu hỏi

Số liệu lấy từ Prometheus tại thời điểm chụp dashboard (17:04, 2 instance, 30 user):

1. **p95 = 294.6 ms, avg = 237.9 ms, p99 = 1850 ms.** p95 chỉ cao hơn avg khoảng 57 ms, nhưng p99 gấp gần 8 lần avg. Phần lớn request nhanh và đều (~190–230 ms), còn một đuôi nhỏ (~3% request bị mock làm chậm thêm 1.5 s) rất chậm. Avg che mất đuôi này, chỉ percentile cao mới thấy.
2. **Có, chia đều:** `172.20.0.7` nhận 9.29 req/s, `172.20.0.8` nhận 9.22 req/s (chênh dưới 1%). Nginx dùng round-robin. Khi scale lên 3 instance ở mục 5 cũng chia đều như vậy.
3. **Input tokens/s (1450) lớn hơn output (770)** vì agent v2 nhét system prompt và tài liệu retrieval vào prompt, cộng thêm câu hỏi. Còn câu trả lời mock chỉ là một đoạn tài liệu ngắn. Với LLM thật, giá output thường đắt hơn input, nên cần theo dõi riêng từng loại.
4. **`curl http://localhost:8080/metrics` trả 404.** `nginx.conf` chặn `location = /metrics`, vì metrics chỉ dành cho Prometheus scrape trực tiếp từng agent trong mạng nội bộ Docker. Public ra ngoài sẽ lộ thông tin nội bộ (route, model, cost) và cho người ngoài spam endpoint.

### Unit test alert rules (Exercise 7.6)

`promtool test rules /p/alert_rules_test.yml`: **SUCCESS**.

### 4.2 Thí nghiệm "phá hệ thống"

Đổi biến môi trường bằng `VAR=... docker compose -p k5-day14-observability up -d --scale agent=3 agent`, giữ Locust 30 user suốt thí nghiệm. Thời gian đo bằng script poll `GET /api/v1/alerts` mỗi 2 giây, tính từ lúc chạy lệnh đổi cấu hình.

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (giá trị ~19.1%) | pending sau 33 s, **firing sau 93 s** (`for: 1m`) | Error rate (Golden Signals) chuyển đỏ; "Requests/s theo status code" có đường 503 tăng; "LLM calls theo kết quả" phần error tăng |
| B | `MOCK_SLOW_RATE=0.3` (giữ A) | `AgentHighLatencyP95` (p95 ~1.89 s) | pending sau 26 s, **firing sau 146 s** (`for: 2m`) | "Latency /ask p50/p95/p99": p95/p99 vọt lên ~1.9 s, p50 gần như không đổi |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` | pending sau 25 s, **firing sau 143 s** (`for: 2m`) | "Cost burn rate (USD/giờ)": từ 1.67 lên **34.4 USD/giờ**; p95 tăng lên ~690 ms (latency_factor 2.5) |
| D | `docker pause k5-day14-observability-agent-1` | `AgentInstanceDown` | pending sau 8 s, **firing sau 39 s** (`for: 30s`) | "Instances up" giảm từ 3 xuống 2. Locust ghi nhận 25 lỗi 504, nhưng error rate phía agent vẫn chỉ 0.66% (xanh) |
| E | `AGENT_VERSION=v1` | **Không có** (sau 2.5 phút; error rate 1.7%, p95 198 ms đều xanh) | — | "Retrieval hit ratio" mất dữ liệu (v1 không retrieval), tokens/s giảm, bảng "Phiên bản đang chạy" đổi sang v1 |

Ảnh `prometheus-alert-firing.png` chụp lúc A + B cùng bật: 2 alert `AgentHighErrorRate` và `AgentHighLatencyP95` cùng firing. Lưu ý: `LLMCostBurnRateHigh` đã firing ngay từ đầu, do 2 lần Locust 100 user ở mục 5 đẩy cost/giờ vượt 2 USD (cửa sổ `rate[5m]`). Nó cũng còn firing vài phút sau C vì cửa sổ 5 phút vẫn còn dữ liệu model lớn. Ngưỡng cost alert nên tính theo traffic dự kiến.

Vì sao D không làm error rate đỏ: request bị treo ở instance đang pause hết thời gian chờ tại Nginx (504). Agent chưa từng xử lý xong request đó nên metric của agent không đếm. Cần giám sát thêm ở tầng load balancer hoặc dùng synthetic check từ bên ngoài.

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Metric hạ tầng (latency, lỗi, up) chỉ cho biết agent *có trả lời không*, không cho biết *trả lời có đúng không*. Cách phát hiện:

1. **Chặn trước khi deploy:** chạy eval golden dataset làm quality gate trong CI (mục 3; v1 bị exit code 1).
2. **Online eval / canary:** định kỳ chạy một tập nhỏ golden question vào production, xuất metric `eval_accuracy` lên Prometheus và đặt alert khi accuracy giảm.
3. **Proxy metric chất lượng:** alert khi retrieval hit ratio giảm hoặc mất series (`absent(agent_retrieval_total)`), khi `agent_info{version}` đổi ngoài kế hoạch, hoặc khi token/câu giảm đột ngột.
4. **Tín hiệu từ người dùng:** thumbs down / tỉ lệ hỏi lại, và LLM-as-judge chấm mẫu ngẫu nhiên.

### 4.3 Debug bằng trace

Trace chậm nhất trong log khi chạy tải (`screenshots/jaeger-slow-trace.png`):

- `trace_id`: `d9c2e1de46a0e9529f3aeef0638e3f17`
- Tổng thời gian: 1756.9 ms (span `POST /ask`)
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (1733.1 ms, 98.6%). `agent.retrieve_context` chỉ 19.2 ms. Nút thắt là LLM (request rơi vào nhóm slow của mock), không phải code của agent.
- Dòng log tương ứng (`docker compose -p k5-day14-observability logs agent`, lọc theo `trace_id`):

```json
{"ts": "2026-11-26T10:07:20.841355+00:00", "level": "INFO", "service": "observable-agent", "instance": "7c4400bc2a2a", "event": "llm_call", "trace_id": "d9c2e1de46a0e9529f3aeef0638e3f17", "span_id": "941db602dd826a11", "request_id": "696eeb35c10d", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 76, "output_tokens": 39, "cost_usd": 3.5e-05, "llm_ms": 1669.2}
{"ts": "2026-11-26T10:07:20.843589+00:00", "level": "INFO", "service": "observable-agent", "instance": "7c4400bc2a2a", "event": "http_request", "trace_id": "d9c2e1de46a0e9529f3aeef0638e3f17", "span_id": "941db602dd826a11", "request_id": "696eeb35c10d", "method": "POST", "route": "/ask", "status": 200, "ms": 1755.3}
```

Trace lỗi (`screenshots/jaeger-error-trace.png`): `trace_id` `059380d5b298bfbf2d1b3b76dfb2c6f7`, `POST /ask` trả 503 trong 101 ms. Span `chat mock-llm-small` có `error.type = upstream_unavailable` và event `exception` (`utils.mock_llm.LLMError: Upstream LLM error: 503 Service Unavailable (mock)`). Log khớp:

```json
{"ts": "2026-11-26T10:10:11.146355+00:00", "level": "INFO", "service": "observable-agent", "instance": "7c4400bc2a2a", "event": "llm_error", "trace_id": "059380d5b298bfbf2d1b3b76dfb2c6f7", "span_id": "5da637c46aa28666", "request_id": "290f917c6dc4", "error": "Upstream LLM error: 503 Service Unavailable (mock)"}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Nguồn: `benchmark-results/scale_1_stats.csv`, `benchmark-results/scale_3_stats.csv` (dòng `POST /ask`).

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 59.77 | 190 | 250 | 1700 | 89 / 7142 (1.25%) |
| 3 | 59.79 | 190 | 220 | 1700 | 51 / 7142 (0.71%) |

> Lưu ý quy trình: lệnh `docker compose run --rm locust` trong CHECKPOINTS tự khởi động lại các service phụ thuộc (`locust → nginx → agent`) theo `deploy.replicas: 2`, nên lần đo đầu cả hai kịch bản thực ra đều chạy 2 instance. Hai file CSV trên được đo lại bằng `run --rm --no-deps`, và đã kiểm tra số container agent trước và sau mỗi lần chạy (đúng 1 và 3), cũng như tải được chia đều cho 3 target trong Prometheus.

**Giải thích kết quả:** Scale lên 3 instance **không tăng RPS** (59.8 req/s cả hai lần) và chỉ cải thiện nhẹ p95 (250 → 220 ms, giảm request phải chờ trong hàng đợi của 1 instance). p50 và p99 không đổi. Lý do:

- **Tải là closed-loop:** 100 user, mỗi user nghỉ 0.5–2 s giữa các request, nên tổng tải tối đa khoảng 100 / (1.25 s + 0.2 s) ≈ 60–70 req/s, bất kể có bao nhiêu instance. 1 instance (async, I/O-bound) đã đủ phục vụ mức đó.
- **Nút thắt nằm ở LLM:** gần như toàn bộ latency là thời gian chờ LLM (~120–180 ms nền, cộng 1.5 s cho ~3% request chậm, xem panel LLM latency và trace ở 4.3). Thêm instance không làm LLM nhanh hơn, nên p50 và p99 giữ nguyên.
- Scale ngang chỉ có lợi khi một instance bị bão hoà CPU hoặc kết nối (như c=100 ở mục 2.1). Với workload này, muốn giảm latency phải xử lý phía LLM: cache, model nhanh hơn, timeout/hedging cho request chậm, streaming.

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. **Đo percentile, không đo trung bình:** 3% request chậm làm p99 tăng ×3.8 trong khi avg chỉ tăng 15%. SLO và alert phải đặt theo p95/p99.
  2. **Metric hạ tầng không thấy lỗi chất lượng:** đổi sang v1 (accuracy 4.3%) nhưng mọi panel vẫn xanh. Cần eval golden dataset làm quality gate trong CI, và chỉ số "cost / câu đúng" để so phiên bản.
  3. **Metrics, trace và log phải nối được với nhau qua `trace_id`:** từ alert → panel → trace chậm/lỗi trong Jaeger → dòng log JSON, tìm ra nguyên nhân (LLM chậm, upstream 503) trong vài phút. Metric chỉ thấy những gì chính service đó thấy (504 ở Nginx không hiện trên agent).
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?
  - Metric ở tầng Nginx/LB (tỉ lệ 5xx, 504, upstream timeout) và synthetic check từ bên ngoài.
  - Online eval định kỳ (`eval_accuracy`), alert khi `absent()` metric retrieval hoặc hit ratio giảm, alert khi `agent_info{version}` thay đổi.
  - Alert theo **burn rate của error budget** (multi-window, vd 1h + 5m) thay cho ngưỡng cố định, để giảm alert fatigue.
  - Alert ngân sách theo ngày/tháng (cost guard), tách theo model; theo dõi token/câu để bắt prompt phình to.
  - Saturation: in-flight request, CPU/RAM container, độ dài hàng đợi; alert khi p99 LLM tăng kéo dài (provider chậm).
