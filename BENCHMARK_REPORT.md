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

### 4.1 Screenshot

- [ ] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals)
- [ ] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian)
- [ ] Một trace lỗi trong Jaeger (có event `exception`)
- [ ] Trang Alerts của Prometheus với ít nhất 1 alert đang **firing**

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | | | |
| B | `MOCK_SLOW_RATE=0.3` | | | |
| C | `LLM_MODEL=mock-llm-large` | | | |
| D | `docker pause` 1 instance | | | |
| E | `AGENT_VERSION=v1` | | | |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

...

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất bạn tìm được:

- `trace_id`: ...
- Tổng thời gian: ... ms
- Span chiếm nhiều thời gian nhất: ... (... ms, ...%)
- Dòng log tương ứng (grep theo `trace_id`):

```json

```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | | | | | |
| 3 | | | | | |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

...

---

## 6. Kết luận

- 3 điều bạn học được về benchmark & observability:
  1. ...
  2. ...
  3. ...
- Nếu đưa agent này lên production thật, bạn sẽ thêm metric / alert nào nữa?

...
