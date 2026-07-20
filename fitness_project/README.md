# SmartFit API 使用说明

SmartFit 是一个基于 FastAPI 的健身后端服务，提供 AI 训练计划生成、训练记录保存与查询、Apple 登录鉴权等能力。

## 目录结构

```
fitness_project/
├── main.py                     # FastAPI 应用入口，注册路由/异常处理/限流
├── config/
│   └── settings.py             # 全局配置（从环境变量 / .env 加载）
├── core/
│   ├── logger.py                # 日志初始化
│   ├── security.py              # JWT 生成与鉴权依赖 parse_token
│   └── dependencies.py          # FastAPI 依赖注入（缓存/计划服务单例）
├── cache/
│   └── impl.py                   # 训练计划内存缓存（PlanCache）
├── infrastructure/
│   └── db/mysql.py               # MySQL 连接与建表、用户/训练记录持久化
├── services/
│   ├── plan_service.py           # 调用千问(Qwen) API 生成并规范化训练计划
│   └── training_service.py       # 训练记录保存与按日汇总
└── api/v1/
    ├── login.py                   # Sign in with Apple 登录接口
    ├── plan.py                    # 训练计划生成接口（带限流）
    └── training.py                # 训练记录保存/查询接口
```

## 环境要求

- Python 3.10+
- MySQL 5.7+ / 8.0（用于持久化用户与训练记录）
- Redis（可选，配置中预留，当前计划缓存默认使用进程内内存缓存 `PlanCache`）

## 安装依赖

项目未提供 `requirements.txt`，请根据代码中实际用到的第三方库安装（建议在虚拟环境中执行）：

```bash
pip install fastapi uvicorn slowapi pyjwt requests pymysql pydantic pydantic-settings
```

> 提示：如需固化依赖版本，建议自行执行 `pip freeze > requirements.txt` 并提交到仓库。

## 环境变量配置

项目通过 `pydantic-settings` 从项目根目录的 `.env` 文件（或系统环境变量）加载配置，对应字段见 `fitness_project/config/settings.py`。

在仓库根目录（`SmartFit_Backend/`，与 `fitness_project/` 同级）创建 `.env` 文件，示例：

```dotenv
# 服务
APP_HOST=0.0.0.0
APP_PORT=8001

# 千问（Qwen）大模型
QWEN_API_KEY=your_qwen_api_key
QWEN_MODEL=qwen-turbo
QWEN_TEMPERATURE=0.3

# 限流（slowapi 语法）
RATE_LIMIT=100/minute

# MySQL
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASS=your_db_password
DB_NAME=smartfit

# 鉴权
JWT_SECRET=change_this_to_a_random_secret
JWT_EXPIRE_DAYS=7
APPLE_CLIENT_ID=com.SmartFitness

# Redis（预留配置，当前未强制依赖）
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
```

各配置项说明：

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `APP_HOST` / `APP_PORT` | 服务监听地址与端口 | `0.0.0.0` / `8001` |
| `QWEN_API_KEY` | 千问 API Key，未配置时生成训练计划会报错 | 空 |
| `QWEN_MODEL` / `QWEN_TEMPERATURE` | 千问模型与生成温度 | `qwen-turbo` / `0.3` |
| `CACHE_EXPIRE_HOURS` | 训练计划内存缓存过期时间（小时） | `24` |
| `RATE_LIMIT` | `/api/plans/generate` 接口限流规则 | `100/minute` |
| `DB_HOST/PORT/USER/PASS/NAME` | MySQL 连接信息 | 见 `settings.py` |
| `JWT_SECRET` | JWT 签名密钥，**生产环境必须修改** | 内置默认值（不安全） |
| `JWT_EXPIRE_DAYS` | 登录态过期天数 | `7` |
| `APPLE_CLIENT_ID` | Sign in with Apple 的客户端 ID（Bundle ID） | `com.SmartFitness` |
| `EXERCISE_DB_PATH` | 动作库 JSON 路径（用于训练计划动作补全信息） | `free-exercise-db-main/dist/exercisesCN.json` |

> `EXERCISE_DB_PATH` 是相对路径，程序会基于当前工作目录（即启动 `uvicorn`/`python` 的目录）拼接，请确保在仓库根目录启动服务，且 `free-exercise-db-main/dist/exercisesCN.json` 文件存在。

## 启动服务

在仓库根目录（`SmartFit_Backend/`）下执行：

```bash
python -m fitness_project.main
```

或使用 uvicorn 直接启动（默认关闭热重载，可自行加 `--reload` 用于本地开发）：

```bash
uvicorn fitness_project.main:app --host 0.0.0.0 --port 8001 --reload
```

服务启动时会自动执行 `mysql_client.init_tables()` 创建缺失的数据库表（`users`、`training_sessions` 等），无需手动建表；若数据库连接失败，仅记录错误日志，不影响健康检查接口。

启动后可访问自动生成的接口文档：

- Swagger UI: `http://localhost:8001/docs`
- ReDoc: `http://localhost:8001/redoc`

## 鉴权说明

除健康检查和 Apple 登录接口外，其余接口均需要在请求头中携带登录令牌：

```
Authorization: Bearer <token>
```

`<token>` 通过 `/api/auth/apple/login` 登录接口获取，有效期由 `JWT_EXPIRE_DAYS` 控制。令牌过期或无效会返回 `401`。

## 统一响应格式

除 `/api/training/gettraining` 外，各接口统一返回如下结构：

```json
{
  "code": 200,
  "msg": "ok",
  "data": {}
}
```

异常情况下由全局异常处理器统一包装：

| 场景 | HTTP 状态码 | 说明 |
| --- | --- | --- |
| `HTTPException` | 由业务代码指定 | 返回 `{code, msg, data: null}` |
| 请求参数校验失败 | 422 | 返回 `{code: 422, msg: "请求参数校验失败", data: [校验错误详情]}` |
| 触发限流 | 429 | 由 `slowapi` 处理 |
| 未捕获异常 | 500 | 返回 `{code: 500, msg: "服务器内部错误", data: null}`，同时记录日志 |

## 接口说明

### 1. 健康检查

```
GET /test
```

返回：

```json
{ "code": 200, "msg": "samrtfit服务器正常运行", "data": null }
```

### 2. Apple 登录

```
POST /api/auth/apple/login
Content-Type: application/json
```

请求体：

```json
{
  "id_token": "<Apple 返回的 identity token>",
  "code": "<可选，Apple 授权码>",
  "name": "<可选，用户昵称，首次登录时传入>"
}
```

服务端会向 `https://appleid.apple.com/auth/keys` 校验 `id_token` 签名，校验通过后按 `apple_sub`（Apple 用户唯一标识）创建或更新用户，并返回登录令牌：

```json
{
  "code": 200,
  "msg": "ok",
  "data": {
    "user_id": 1,
    "apple_sub": "000123.abcdef...",
    "email": "user@example.com",
    "name": "张三",
    "token": "<JWT，用于后续接口鉴权>"
  }
}
```

### 3. 生成训练计划

```
POST /api/plans/generate
Authorization: Bearer <token>
Content-Type: application/json
```

请求体：

```json
{
  "user_input": "希望增肌，一周练4次，主要练胸和背",
  "user_profile": { "age": 25, "gender": "male", "height": 175, "weight": 70 }
}
```

- 会先根据 `user_id + user_input + user_profile` 的哈希查询内存缓存（`CACHE_EXPIRE_HOURS` 内有效），命中则直接返回。
- 未命中时调用千问 API 生成计划，并结合本地动作库（`EXERCISE_DB_PATH`）补全动作的图片、说明、肌群等信息后写入缓存并返回。
- 该接口受 `RATE_LIMIT`（默认 `100/minute`，按客户端 IP）限流，超限返回 429。

返回示例（节选）：

```json
{
  "code": 200,
  "msg": "训练计划生成成功",
  "data": {
    "training_split": "推拉腿",
    "daily_plans": [
      {
        "training_day": "Day 1 胸部",
        "exercise_list": [
          {
            "id": "1",
            "exercise_name": "杠铃卧推",
            "sets": 4,
            "reps": "8-12",
            "order": 1,
            "images": ["Barbell_Bench_Press"],
            "primary_muscles": ["Chest"],
            "secondary_muscles": ["Triceps"],
            "instructionsCN": ["..."],
            "exercise_type": "strength"
          }
        ]
      }
    ]
  }
}
```

### 4. 保存训练记录

```
POST /api/training/save
Authorization: Bearer <token>
Content-Type: application/json
```

请求体（字段均为必填，见 `TrainingRecordPayload`；禁止未声明的多余字段）：

```json
{
  "id": "客户端生成的 UUID",
  "date": "2026-07-20T10:00:00Z",
  "focus_area": "胸部",
  "duration": 3600,
  "is_completed": true,
  "exercises": [
    {
      "id": "动作实例 UUID",
      "backend_id": "动作库中的动作 id（可选）",
      "order": 1,
      "exercise_name": "杠铃卧推",
      "sets": 4,
      "reps": "8-12",
      "equipment": "杠铃",
      "difficulty": "中级",
      "images": [],
      "instructions": "",
      "focus_area": "胸部",
      "primary_muscles": ["Chest"],
      "rest_time": 90,
      "exercise_sets": [
        { "id": "组 UUID", "weight": 60, "reps": 10, "is_completed": true }
      ]
    }
  ]
}
```

返回：

```json
{
  "code": 200,
  "msg": "saved",
  "data": {
    "id": "客户端生成的 UUID",
    "version": 1,
    "synced_at": "2026-07-20T02:00:00Z"
  }
}
```

### 5. 查询某日训练汇总

```
GET /api/training/gettraining?date=2026-07-20
Authorization: Bearer <token>
```

- `date` 为可选查询参数，格式 `YYYY-MM-DD`，缺省时取服务器当天日期。
- 该接口直接返回汇总结果（未经全局包装，格式与其他接口一致但由 service 层自行组装）：

```json
{
  "code": 200,
  "msg": "ok",
  "data": [
    {
      "date": "2026-07-20",
      "summary": {
        "total_volume": 2400.0,
        "total_duration": 3600,
        "focus_areas": ["胸部"]
      },
      "exercises": [
        {
          "exercise_name": "杠铃卧推",
          "max_weight": 60.0,
          "sets": 4,
          "detailed_sets": [
            { "id": "组 UUID", "weight": 60.0, "reps": 10, "is_completed": true }
          ]
        }
      ]
    }
  ]
}
```

当日无记录时返回 `"data": []`。

## 常见问题

- **生成训练计划报 500 / `QWEN_API_KEY 未配置`**：请检查根目录 `.env` 是否配置了有效的 `QWEN_API_KEY`。
- **动作图片/说明未被补全**：确认 `EXERCISE_DB_PATH` 指向的动作库 JSON 文件存在，且启动目录为仓库根目录。
- **接口返回 401**：检查请求头是否携带 `Authorization: Bearer <token>`，以及 token 是否已过期（`JWT_EXPIRE_DAYS`）。
- **接口返回 429**：`/api/plans/generate` 触发了限流，请降低请求频率或调整 `RATE_LIMIT`。
- **数据库连接失败但服务仍能启动**：`lifespan` 中的建表逻辑失败仅记录日志，不会阻塞服务启动，请检查日志（`logs/` 目录）定位 MySQL 连接问题。
