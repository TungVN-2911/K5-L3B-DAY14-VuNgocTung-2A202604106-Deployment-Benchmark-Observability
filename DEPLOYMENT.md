# Deployment Information

## Public URL

https://day14-agent-render.onrender.com

> Gói Render Free tự ngủ sau 15 phút không có traffic. Request đầu tiên sau khi ngủ có thể mất khoảng 50–60 giây để service khởi động lại; gọi `/health` một lần và chờ trả 200 trước khi kiểm tra.

## Platform

**Render** (Blueprint `06-lab-complete/render.yaml`), deploy từ nhánh `main`, commit `1212f9c`.

| Resource | Loại | Plan | Region | Ghi chú |
|---|---|---|---|---|
| `day14-agent-render` | Web Service, Docker (build từ `06-lab-complete/Dockerfile`) | Free | Oregon | `healthCheckPath: /health` |
| `day14-redis-render` | Key Value (Redis-compatible) | Free | Oregon | `ipAllowList: []`, chỉ kết nối nội bộ |

## Test Commands

Kết quả chạy ngày 26/11/2026 (ảnh `screenshots/test.png`): **200 · 200 · 401 · 200**.

```bash
BASE=https://day14-agent-render.onrender.com
read -s -p "AGENT_API_KEY: " AGENT_API_KEY; echo   # lấy từ Render → Environment, không ghi vào repo

curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"     # 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"      # 200 (Redis kết nối được)
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -d '{"question":"Hello"}'   # 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" -d '{"question":"Hello"}'   # 200
```

### Health Check

```bash
curl https://day14-agent-render.onrender.com/health
# {"status":"ok"}
```

### API Test (with authentication)

```bash
curl -X POST https://day14-agent-render.onrender.com/ask \
  -H "X-API-Key: $AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
```

Thiếu hoặc sai `X-API-Key` → `401`.

## Environment Variables Set

Đặt trên Render qua Blueprint, không ghi giá trị secret trong code hay repo:

| Biến | Nguồn |
|---|---|
| `PORT` | Render tự cấp; app đọc `${PORT}` |
| `ENVIRONMENT` | `production` |
| `AGENT_API_KEY` | `generateValue: true` (Render sinh ngẫu nhiên 256-bit) |
| `REDIS_URL` | `fromService` → `connectionString` của Key Value `day14-redis-render` (URL nội bộ) |
| `RATE_LIMIT_PER_MINUTE` | `10` |
| `DAILY_BUDGET_USD` | `1.0` |

## Screenshots

- [Deployment dashboard](screenshots/dashboard.png): service `day14-agent-render`, Docker, Free, **Live**, biến môi trường đã đặt (giá trị bị che)
- [Service running](screenshots/running.png): Events, "Deploy live for 1212f9c"
- [Test results](screenshots/test.png): 4 lệnh tự kiểm → 200 / 200 / 401 / 200

## Giới hạn gói Free

- Web service ngủ sau 15 phút không có traffic, khởi động lại mất khoảng 1 phút; mỗi workspace có 750 giờ Free/tháng.
- Key Value Free: 25 MB, 50 kết nối, không lưu dữ liệu xuống đĩa và có thể bị restart bất cứ lúc nào, nên trạng thái rate limit / cost guard có thể mất. Mỗi workspace chỉ có 1 Key Value Free.
- Chỉ phù hợp cho lab / demo, không dùng cho production thật.
