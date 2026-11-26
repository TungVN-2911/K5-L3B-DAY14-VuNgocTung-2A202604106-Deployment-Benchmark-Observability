# Day 14 Lab - Mission Answers

**Họ tên:** ____________________

**MSSV:** ____________________

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found

Đọc trong `01-localhost-vs-production/develop/app.py`, đã tìm thấy ít nhất 5 anti-pattern:

1. API key và database URL được hardcode trong source code.
2. Secret cũng được in ra console, có nguy cơ làm lộ credential qua log.
3. Dùng `print()` thay cho structured logging.
4. Debug mode và reload được bật trong cấu hình khởi động production.
5. Port và host được cố định thay vì đọc cấu hình nền tảng.
6. Không có `/health` hoặc `/ready`.
7. Không có lifecycle/graceful shutdown rõ ràng.

Lệnh chạy đã kiểm tra bản develop:

```bash
curl.exe -sS -X POST "http://localhost:8000/ask?question=Hello"
```

Kết quả:

```json
{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

### Exercise 1.3: Comparison table

| Feature | Develop | Production | Why Important? |
|---|---|---|---|
| Config | Secret, database URL và port hardcode | `config.py` đọc environment variables | Có thể đổi cấu hình theo môi trường mà không sửa/rebuild code |
| Secret | Dùng key giả hardcode và in ra log | Không log secret; truyền secret qua env | Giảm rủi ro lộ credential khi commit hoặc xem log |
| Health check | Không có | Có `/health` và `/ready` | Orchestrator biết restart hay dừng route traffic |
| Logging | `print()` | JSON structured logging | Log dễ tìm kiếm, lọc và đưa vào hệ thống observability |
| Shutdown | Uvicorn dừng đột ngột | Lifespan cleanup và SIGTERM handling | Giữ request đang chạy hoàn tất trước khi process exit |
| Binding | `localhost`, port cố định 8000 | `0.0.0.0`, port đọc từ `PORT` | Container/cloud có thể truy cập agent và tự cấp port |
| Debug | `DEBUG=True`, reload bật | Reload chỉ bật khi debug env cho phép | Production không nên dùng debug/reload |
| Metrics | Không có | Có `/metrics` cơ bản | Cho phép theo dõi uptime và môi trường |

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions

1. **Base image develop:** `python:3.11`, một full Python distribution.
2. **Base image production:** builder và runtime đều dùng `python:3.11-slim`.
3. **Working directory:** `/app`.
4. **COPY requirements trước:** Tận dụng Docker build cache; nếu source thay đổi nhưng requirements không đổi, dependency layer không cần cài lại.
5. **CMD khác ENTRYPOINT:**
   - `CMD` cung cấp command mặc định, có thể override khi chạy container.
   - `ENTRYPOINT` đặt executable chính, phù hợp để cố định hành vi của container.
6. **Multi-stage:** stage builder cài compiler và dependencies; stage runtime chỉ copy dependency và source cần thiết. Không copy build tools sang runtime nên image sạch và nhỏ hơn.

### Exercise 2.2–2.4

Lệnh build theo hướng dẫn từ gốc repo:

```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker build -f 02-docker/production/Dockerfile -t my-agent:advanced .
docker images my-agent
```

Đã build và đo bằng Docker trên ngày 26/11/2026:

- Develop: `1.67 GB` / `1667783975 bytes` / khoảng `1590.37 MiB`
- Production: `240 MB` / `239815393 bytes` / khoảng `228.69 MiB`
- Chênh lệch: khoảng `85.62%` nhỏ hơn

Số đo được lấy bằng `docker inspect` sau hai lệnh build:

```bash
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker build -f 02-docker/production/Dockerfile -t my-agent:advanced .
docker inspect my-agent:develop my-agent:advanced --format '{{.RepoTags}} {{.Size}}'
```

Stack Part 2 đã chạy bằng Docker Compose. Kết quả:

- Các service `agent`, `redis`, `qdrant`, `nginx` đều khởi động.
- `/health` qua Nginx trả `HTTP/1.1 200 OK`.
- `/ask` qua Nginx gửi JSON hợp lệ đã trả response mock `200 OK`.

Kiến trúc Docker Compose của Part 2:

```text
Client
  |
  v
Nginx :80/:443
  |
  v
Agent (FastAPI)
  |       |
  v       v
Redis   Qdrant
```

Các service là `agent`, `redis`, `qdrant`, `nginx`. Agent dùng Redis cho cache/session và Qdrant cho RAG; Nginx là reverse proxy/load balancer. Redis và Qdrant dùng named volumes để giữ dữ liệu.

---

## Part 3: Cloud Deployment

### Exercise 3.1 / 3.2: Deploy (nền tảng chính: Render)

Deploy agent Part 6 trong `06-lab-complete/` bằng Blueprint `06-lab-complete/render.yaml` (web service Docker + Key Value Redis, đều gói Free). Chi tiết: [DEPLOYMENT.md](DEPLOYMENT.md).

- Public URL: https://day14-agent-render.onrender.com
- 4 lệnh tự kiểm CP6 (ảnh `screenshots/test.png`): `/health` → **200** · `/ready` → **200** · `/ask` không key → **401** · `/ask` có key → **200**
- `AGENT_API_KEY` do Render sinh (`generateValue`), `REDIS_URL` lấy từ Key Value qua `fromService`; không có secret trong repo.
- Lần đầu tạo Blueprint, Render báo `services[1] must specify IP allow list` vì đọc nhầm file mẫu `03-cloud-deployment/render/render.yaml`. Đặt **Blueprint Path** là `06-lab-complete/render.yaml` thì deploy thành công.

### So sánh `railway.toml` và `render.yaml` (nền tảng còn lại)

Cả hai file đều build agent từ cùng một `06-lab-complete/Dockerfile` và cùng dùng `/health` làm health check. Khác nhau ở chỗ mỗi file mô tả được bao nhiêu phần của hệ thống:

| Khía cạnh | `railway.toml` | `render.yaml` | Vì sao khác |
|---|---|---|---|
| Phạm vi | Chỉ cấu hình **một service** (build + deploy) | **Blueprint (IaC)** khai báo cả web service lẫn Redis (`type: keyvalue`) | Railway thêm Redis bằng plugin/service trên dashboard, ngoài file; Render cho dựng cả hạ tầng từ một file |
| Build | `builder = "DOCKERFILE"`, `dockerfilePath = "Dockerfile"` | `runtime: docker`, `rootDir: 06-lab-complete`, `dockerfilePath`, `dockerContext` | `railway.toml` nằm trong thư mục được `railway up`, nên đường dẫn tính từ đó; Render đọc Blueprint từ repo nên phải chỉ ra `rootDir` |
| Health check | `healthcheckPath = "/health"`, `healthcheckTimeout = 30` | `healthCheckPath: /health` | Giống nhau về ý nghĩa; Railway cho chỉnh timeout ngay trong file |
| Restart | `restartPolicyType = "ON_FAILURE"`, tối đa 3 lần | Không khai báo; Render tự restart theo health check | Railway cho phép cấu hình chính sách restart, Render quản lý thay |
| Biến môi trường và secret | Không có trong file: `AGENT_API_KEY`, `REDIS_URL` đặt bằng `railway variables` hoặc dashboard (Redis plugin cấp sẵn `REDIS_URL`) | Có trong file nhưng không ghi giá trị secret: `AGENT_API_KEY` dùng `generateValue: true`, `REDIS_URL` lấy bằng `fromService` (connection string của Key Value) | Render nối các service trong Blueprint với nhau nên tham chiếu được; với Railway, để env ngoài file giúp không lộ secret vào git |
| Gói và vùng | Không khai báo (chọn trên dashboard) | `plan: free`, `region: oregon` cho cả hai service | Blueprint mô tả cả chi phí và vị trí hạ tầng |
| `PORT` | Railway cấp `PORT`; app đọc `${PORT:-8000}` | Render cấp `PORT`; app đọc cùng biến | Cả hai nền tảng tự cấp port, nên app không được cố định 8000 |

Kết luận: `railway.toml` là file cấu hình deploy gọn cho một service. `render.yaml` là Infrastructure as Code, dựng lại được toàn bộ stack (agent + Redis + nối env) từ repo. Đổi lại, Render bản Free có cold start khoảng 1 phút và Key Value không lưu dữ liệu khi restart.

### Exercise 3.3: Pipeline CI/CD Cloud Run

Đọc `03-cloud-deployment/production-cloud-run/cloudbuild.yaml` và `service.yaml`:

1. **Trigger:** push lên `main` chạy Cloud Build. Bước `test` cài `requirements.txt` + `pytest` trong `python:3.11-slim` và chạy `pytest tests/`; test fail thì pipeline dừng.
2. **Build:** `docker build` gắn 2 tag `ai-agent:$COMMIT_SHA` và `:latest`, dùng `--cache-from :latest` để tái dùng layer cache.
3. **Push:** đẩy mọi tag lên Container Registry `gcr.io/$PROJECT_ID/ai-agent`.
4. **Deploy:** `gcloud run deploy` image theo `$COMMIT_SHA` (nên rollback được về đúng commit) lên `asia-southeast1`. Cấu hình min 1 / max 10 instance, 512Mi, 1 CPU, timeout 60s. Env `ENVIRONMENT=production`, secret lấy từ Secret Manager bằng `--set-secrets`.
5. **`service.yaml`** mô tả cùng service dạng IaC (Knative), áp dụng bằng `gcloud run services replace`. Thêm `containerConcurrency: 80`, `livenessProbe` gọi `/health`, `startupProbe` gọi `/ready` (instance chỉ nhận traffic khi sẵn sàng). `AGENT_API_KEY` và `OPENAI_API_KEY` dùng `secretKeyRef`, không hardcode.

---

## Part 4: API Security

### Exercise 4.1: API key

Kiểm tra API key diễn ra trong `verify_api_key()` thông qua dependency `APIKeyHeader(name="X-API-Key")`.

- Thiếu key: `401 Missing API key`
- Sai key: `403 Invalid API key`
- Đúng key: request được xử lý

Đầu ra thực tế:

```text
HTTP/1.1 401 Unauthorized
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```

Lệnh có key dùng JSON body đã trả `200 OK` trên bản develop:

```text
HTTP/1.1 200 OK
```

Rotate key bằng cách thay `AGENT_API_KEY` ở secret manager/platform, rolling restart service và thu hồi key cũ; không thay key hardcode trong source.

### Exercise 4.2: JWT

Flow JWT:

1. `POST /auth/token` xác thực username/password.
2. Server tạo JWT có `sub`, `role`, `iat`, `exp`.
3. Client gửi `Authorization: Bearer <token>`.
4. `verify_token()` kiểm tra chữ ký và expiry.
5. Endpoint lấy `username`, `role` để cấp quyền.

Tài khoản demo:

- `student` / `demo123`, role user
- `teacher` / `teach456`, role admin

### Exercise 4.3: Rate limiting

Rate limiter production dùng sliding window counter bằng deque timestamp trong từng process:

- User: tối đa 10 request/60 giây.
- Admin: tối đa 100 request/60 giây.
- Vượt giới hạn trả `429` với `Retry-After`.

Kiểm tra thực tế bằng 15 request liên tiếp:

```text
1 200
2 200
3 200
4 200
5 200
6 200
7 200
8 200
9 200
10 200
11 429
12 429
13 429
14 429
15 429
```

Trong phiên bản production phải lưu state bằng Redis thay vì deque RAM để tất cả worker cùng áp dụng cùng giới hạn.

### Exercise 4.4: Cost guard

Cost guard cần lưu spending theo user và theo ngày/tháng trong Redis:

```text
before ask:
1. Tính spending hiện tại
2. Reset counter khi sang ngày/tháng mới
3. Nếu spending + estimated_cost > budget thì trả 402
4. Nếu đạt cảnh báo 80% thì ghi warning

after ask:
1. Ghi input/output token
2. Cộng chi phí chính xác
3. Lưu usage vào Redis
```

Trong production không dùng `_records` trong RAM vì state mất khi restart và không nhất quán khi nhiều instance.

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Health vs readiness

- `/health` là liveness: trả 200 nếu process còn sống. Container orchestrator dùng để restart process bị treo.
- `/ready` là readiness: trả 200 chỉ khi Redis/DB/dependencies sẵn sàng. Khi Redis chết, trả 503 để load balancer không route traffic vào instance.
- `/health` vẫn phải 200 dù Redis chết; đây là liveness, không phải readiness.

### Exercise 5.2: Graceful shutdown

Container nhận SIGTERM cần:

1. Ngừng nhận request mới.
2. Cho request đang xử lý hoàn thành.
3. Đóng Redis/database connection.
4. Process thoát exit code 0.

Không nên dùng `kill -9`/SIGKILL vì cắt ngang request.

### Exercise 5.3: Stateless design

State không nằm trong dictionary/biến Python vì từng instance có memory riêng. State cần nằm trong Redis, ví dụ:

```text
session:{session_id} -> JSON conversation state
```

Khi một request đi tới instance khác, instance đó vẫn load được history/session trong Redis.

### Exercise 5.4: Load balancing

Stack Part 5 lắng nghe ở cổng 8080 và dùng Nginx làm reverse proxy cho ba agent. Lệnh:

```bash
docker compose -p k5-day14-scaling up -d --build --scale agent=3
python test_stateless.py
docker compose -p k5-day14-scaling down
```

Đã chạy stack thực tế với 3 agent. Kết quả:

- Session ID giữ nguyên: `5819c9a3-baa2-4ee8-b133-46f8eb4ff014`.
- 5 request được phân tán tới 3 instance:
  `instance-7f6f4b`, `instance-e06c34`, `instance-0ca318`.
- Conversation history đọc lại có đủ `10 messages`: 5 câu user và 5 câu assistant.
- Khi Redis có state, traffic chuyển sang instance khác không làm mất session/history.

### Exercise 5.5: Test stateless

Script `test_stateless.py` gửi 5 câu trong cùng một session, ghi `served_by` và đọc lại toàn bộ history qua `/chat/{session_id}/history`.

Kết luận: chỉ có Redis/shared external state mới tạo được agent stateless hoạt động đúng khi scale ngang.

## AI log

Ghi lại lần dùng AI cho giai đoạn này:

- Hỏi: cách đọc và phân tích yêu cầu, cách viết bảng Part 1–5.
- AI gợi ý: cấu trúc MISSION_ANSWERS, điểm cần kiểm tra và cách diễn đạt health/readiness.
- Tôi tự kiểm tra: đọc source `app.py`, `auth.py`, `rate_limiter.py`, `cost_guard.py`, `redis_client.py` và chạy endpoint Part 1, Part 4.
- Docker đã được bật để build hai image, chạy Compose Part 2 và chạy test stateless 3 instance. Các số đo trong file lấy từ `docker inspect` và output script thực tế, không phải số ước lượng.
- Hỏi cho Part 6 giai đoạn 2: triển khai cấu hình environment, logging JSON, health/readiness và API key theo script chấm.
- AI gợi ý và sửa cùng tôi: settings đọc env có kiểm tra giá trị, dependency `X-API-Key`, logger JSON, `/health`, `/ready` và Redis ping không chặn startup.
- Tôi tự kiểm tra: `python -m compileall -q app`; static checker; gọi endpoint. Thiếu/sai API key trả 401, key hợp lệ trả 200, Redis hoạt động thì `/ready` 200, Redis vắng mặt thì agent vẫn khởi động, `/health` 200 và `/ready` 503. Đã xác nhận log request là JSON hợp lệ.
- Hỏi cho Part 6 giai đoạn 3: triển khai rate limit dùng chung qua Redis và cost guard theo ngân sách.
- AI gợi ý và sửa cùng tôi: sliding window atomic với Redis sorted set/Lua, chi phí ngày UTC được cộng nguyên tử và các bước được nối vào `POST /ask`.
- Tôi tự kiểm tra: `python -m compileall -q app` và `python check_production_ready.py --skip-docker`. Checker xác nhận 5 request được phép rồi trả 429, state rate limit còn sau restart agent, và budget test trả 402.
- Hỏi cho Part 6 giai đoạn 4: hoàn thiện graceful shutdown, Docker image, `.dockerignore` và Compose với Redis.
- AI gợi ý và sửa cùng tôi: lifespan đóng Redis client, multi-stage non-root image có healthcheck và CMD exec uvicorn theo PORT, Compose agent+Redis chờ health.
- Tôi tự kiểm tra: `docker compose config`, `python -m compileall -q app`, build image và chạy Compose. Image đạt 238 MB; agent chạy bằng user `appuser`; `/health` và `/ready` trả 200; request có key trả 200. Full checker xác nhận `docker stop` exit code 0 trong 0.6 giây. Thử thêm SIGTERM trong lúc request đang chạy: request trả 200, container thoát exit code 0 trong 0.97 giây.
- Hỏi cho Part 6 giai đoạn 5: hoàn thiện `.env.example` và cấu hình deploy Railway/Render.
- AI gợi ý và sửa cùng tôi: khai báo đủ biến không kèm secret, cấu hình Railway dùng Dockerfile và health check `/health`.
- Tôi tự kiểm tra: `.env.example` có đủ `PORT`, `ENVIRONMENT`, `AGENT_API_KEY`, `REDIS_URL`, `RATE_LIMIT_PER_MINUTE`, `DAILY_BUDGET_USD`; `railway.toml` parse được bằng TOML parser; static checker xác nhận cả hai cấu hình đạt.
- Full checker sau giai đoạn 5 đạt 11/12; phần còn ⚠️ là direct SIGTERM test mà checker không chạy trên Windows. Docker stop và request in-flight đã được kiểm tra riêng ở giai đoạn 4. WSL có Python nhưng chưa có pip/dependencies nên direct checker trong WSL chưa chạy.
- Hỏi cho Part 6 giai đoạn 6: chạy static readiness check trước full check.
- AI hỗ trợ đọc kết quả checker; tôi tự xác nhận `python -m compileall -q app` thành công và `python check_production_ready.py --static-only` có `26/26 checks passed`, không có lỗi tĩnh. Các ⚠️ là runtime/Docker checks được bỏ qua theo chế độ static-only.
- Hỏi cho Part 6 giai đoạn 7: chạy full production readiness checker, gồm cả SIGTERM.
- AI hỗ trợ xử lý môi trường WSL và chạy checker; sau khi người dùng bật Docker Desktop WSL integration, Docker daemon đã truy cập được từ Ubuntu.
- Tôi tự kiểm tra: full `python check_production_ready.py` chạy từ WSL bằng Python 3.11 cô lập trong `/tmp`, không đổi manifest project. Kết quả `PASS 12/12` và `41/41 checks passed`; Docker image 238 MB, SIGTERM khi request đang chạy trả 200 và process exit code 0, `docker stop` exit code 0 trong 0.8 giây.
- Đã xóa môi trường Python/dependencies tạm trong `/tmp`; checker không để lại container test đang chạy.
