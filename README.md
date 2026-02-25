# BTC Whale Order Monitor — 比特币大额订单实时监控系统

基于 [CoinGlass API V4](https://docs.coinglass.com/reference/getting-started-with-your-api) 构建的比特币鲸鱼订单监控工具。系统从中心化交易所（CEX）、去中心化交易所（DEX）和链上数据三大维度，实时采集、聚合并推送 BTC 大额订单动态。

---

## 目录

- [核心功能](#核心功能)
- [系统架构](#系统架构)
- [项目结构](#项目结构)
- [环境要求](#环境要求)
- [快速开始](#快速开始)
  - [本地运行](#1-本地运行)
  - [Docker 运行](#2-docker-运行)
  - [Docker Compose](#3-docker-compose)
- [配置说明](#配置说明)
- [数据源详解](#数据源详解)
  - [中心化交易所 (CEX)](#中心化交易所-cex)
  - [去中心化交易所 (DEX)](#去中心化交易所-dex)
  - [链上数据](#链上数据)
- [API 接口文档](#api-接口文档)
  - [REST API（Pull 模式）](#rest-apipull-模式)
  - [WebSocket（Push 模式）](#websocketpush-模式)
- [数据模型](#数据模型)
- [告警规则引擎](#告警规则引擎)
- [CoinGlass API 等级说明](#coinglass-api-等级说明)
- [测试](#测试)
- [常见问题](#常见问题)

---

## 核心功能

- **多数据源采集**：CEX 合约/现货大额限价单、爆仓订单、Hyperliquid 鲸鱼仓位、链上大额转账
- **多交易所覆盖**：支持 Binance、OKX、Bybit 等 31 个交易所，可自定义扩展
- **Push + Pull 双模式**：
  - **Push**：WebSocket 实时推送告警、Webhook 回调通知
  - **Pull**：REST API 按条件查询历史订单
- **智能告警引擎**：多级告警规则、金额阈值过滤、按来源/交易所/方向自定义
- **数据持久化**：SQLite 本地存储，支持多维度查询
- **自动降级**：API 等级不足时自动暂停对应采集器，不影响其他功能
- **断线重连**：WebSocket 自动重连，指数退避策略
- **请求限流**：内置令牌桶限流器，避免触发 API 频率限制

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                   消费端 (Consumers)                          │
│       REST API Client / WebSocket Client / Webhook          │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                FastAPI 服务器 (server.py)                     │
│   REST: /api/orders, /api/stats, /api/config                │
│   WS:   /ws (实时推送)                                       │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│              推送层 (Push Layer)                              │
│   WebSocketPushManager ─── 管理连接、广播告警                  │
│   WebhookDispatcher ────── POST 回调到配置的 URL              │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│         聚合引擎 + 告警规则 (Engine)                          │
│   Aggregator ──── 去重、存储、分发                             │
│   AlertEngine ─── 规则匹配 (5 条默认规则)                      │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│               数据采集层 (Collectors)                         │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ CEX 合约/现货  │  │  CEX 爆仓     │  │  DEX + 链上       │   │
│  │               │  │              │  │                  │   │
│  │ • 大额订单簿   │  │ • REST 轮询   │  │ • Hyperliquid    │   │
│  │   (Pull)      │  │ • WebSocket  │  │   鲸鱼提醒/持仓   │   │
│  │ • 大额订单历史  │  │   实时推送    │  │ • 链上大额转账    │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
│                                                              │
│  支持交易所: Binance, OKX, Bybit, Bitget, Coinbase...        │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                CoinGlass API V4                              │
│   REST:  https://open-api-v4.coinglass.com                  │
│   WS:    wss://open-ws.coinglass.com/ws-api                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 项目结构

```
BTC-Whale-Order-Monitoring-Tool/
├── .env                          # 环境变量配置（含 API Key，已 gitignore）
├── .env.example                  # 配置模板
├── .gitignore
├── Dockerfile                    # Docker 镜像构建
├── docker-compose.yml            # Docker Compose 编排
├── requirements.txt              # Python 依赖
├── README.md
│
├── config/
│   └── settings.py               # Pydantic 配置管理（类型安全）
│
├── src/
│   ├── main.py                   # 主入口 & 系统编排器
│   ├── __main__.py               # python -m src.main 入口
│   ├── server.py                 # FastAPI 服务器（REST + WebSocket）
│   │
│   ├── api/
│   │   ├── coinglass_client.py   # CoinGlass REST 客户端（限流、重试）
│   │   └── coinglass_ws.py       # CoinGlass WebSocket 客户端（自动重连）
│   │
│   ├── collectors/
│   │   ├── base.py               # 采集器基类（轮询、降级）
│   │   ├── large_order.py        # CEX 合约 & 现货大额订单采集器
│   │   ├── liquidation.py        # 爆仓订单采集器（REST + WS 解析）
│   │   ├── hyperliquid.py        # Hyperliquid 鲸鱼仓位采集器
│   │   └── onchain.py            # 链上大额转账采集器
│   │
│   ├── engine/
│   │   ├── aggregator.py         # 数据聚合器（去重、存储、告警分发）
│   │   └── alert_rules.py        # 多级告警规则引擎
│   │
│   ├── models/
│   │   └── whale_order.py        # 统一数据模型 WhaleOrder
│   │
│   ├── push/
│   │   ├── websocket_server.py   # WebSocket 推送管理器（广播）
│   │   └── webhook.py            # Webhook 回调分发器
│   │
│   └── storage/
│       └── database.py           # SQLite 持久化（异步）
│
├── data/
│   └── whale_orders.db           # SQLite 数据库文件（自动创建）
│
└── tests/
    ├── test_all.py               # 单元测试 + 集成测试（49 项）
    └── test_data_quality.py      # 数据质量测试（273 项）
```

---

## 环境要求

- **Python** >= 3.9
- **Docker** >= 20.0（可选，用于容器化部署）
- **CoinGlass API Key**：在 [CoinGlass 官网](https://www.coinglass.com/zh/pricing) 获取

### 依赖库

| 库 | 版本 | 用途 |
|---|---|---|
| `fastapi` | >= 0.115.0 | Web 框架（REST + WebSocket） |
| `uvicorn` | >= 0.32.0 | ASGI 服务器 |
| `httpx` | >= 0.28.0 | 异步 HTTP 客户端 |
| `websockets` | >= 14.0 | WebSocket 客户端 |
| `pydantic` | >= 2.10.0 | 数据模型验证 |
| `pydantic-settings` | >= 2.7.0 | 环境变量配置管理 |
| `aiosqlite` | >= 0.20.0 | 异步 SQLite |
| `python-dotenv` | >= 1.0.1 | .env 文件加载 |
| `apscheduler` | >= 3.10.4 | 任务调度 |
| `aiohttp` | >= 3.11.0 | 异步 HTTP |

---

## 快速开始

### 1. 本地运行

```bash
# 克隆项目
git clone <repo-url>
cd BTC-Whale-Order-Monitoring-Tool

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate    # macOS/Linux
# .venv\Scripts\activate     # Windows

# 安装依赖
pip install -r requirements.txt

# 配置 API Key
cp .env.example .env
# 编辑 .env，填入你的 CoinGlass API Key

# 启动服务
python -m src.main
```

启动后日志输出：

```
============================================================
  BTC Whale Order Monitor v1.0.0
  Exchanges: ['Binance', 'OKX', 'Bybit']
  Large order threshold: $500,000
  Liquidation threshold: $100,000
============================================================
Database initialized at data/whale_orders.db
CoinGlass REST client started
Collector [futures_large_order] started (interval=10s)
Collector [spot_large_order] started (interval=10s)
Collector [liquidation_poll] started (interval=10s)
Collector [hyperliquid_whale] started (interval=10s)
Collector [onchain_transfer] started (interval=60s)
CoinGlass WebSocket client started
All collectors started. System ready.
Uvicorn running on http://0.0.0.0:8000
```

### 2. Docker 运行

```bash
# 构建镜像
docker build -t btc-whale-monitor .

# 运行容器
docker run -d \
  -p 8000:8000 \
  --env-file .env \
  -v whale_data:/app/data \
  --name whale-monitor \
  btc-whale-monitor
```

### 3. Docker Compose

```bash
# 启动（后台）
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止
docker-compose down
```

---

## 配置说明

所有配置通过 `.env` 文件管理，支持环境变量覆盖。

### 完整配置项

| 变量名 | 说明 | 默认值 | 必需 |
|---|---|---|---|
| `CG_API_KEY` | CoinGlass API Key | - | 是 |
| `HOST` | 服务监听地址 | `0.0.0.0` | 否 |
| `PORT` | 服务端口 | `8000` | 否 |
| `LOG_LEVEL` | 日志级别 (DEBUG/INFO/WARNING/ERROR) | `INFO` | 否 |
| `DB_PATH` | SQLite 数据库路径 | `data/whale_orders.db` | 否 |
| `POLL_INTERVAL_LARGE_ORDER` | 大额订单轮询间隔（秒） | `10` | 否 |
| `POLL_INTERVAL_LIQUIDATION` | 爆仓订单轮询间隔（秒） | `10` | 否 |
| `POLL_INTERVAL_WHALE_ALERT` | Hyperliquid 鲸鱼提醒轮询间隔（秒） | `10` | 否 |
| `POLL_INTERVAL_ONCHAIN` | 链上转账轮询间隔（秒） | `60` | 否 |
| `EXCHANGES` | 监控的交易所列表（逗号分隔） | `Binance,OKX,Bybit` | 否 |
| `LARGE_ORDER_THRESHOLD` | 大额订单金额阈值（美元） | `500000` | 否 |
| `LIQUIDATION_THRESHOLD` | 爆仓订单金额阈值（美元） | `100000` | 否 |
| `WS_PUSH_ENABLED` | 是否启用 WebSocket 推送 | `true` | 否 |
| `WEBHOOK_PUSH_ENABLED` | 是否启用 Webhook 推送 | `false` | 否 |
| `WEBHOOK_URLS` | Webhook 回调 URL（逗号分隔多个） | 空 | 否 |

### 配置示例

```env
CG_API_KEY=your_api_key_here

# 只监控 Binance 和 OKX
EXCHANGES=Binance,OKX

# 提高阈值，只关注超大额订单
LARGE_ORDER_THRESHOLD=2000000
LIQUIDATION_THRESHOLD=500000

# 开启 Webhook 推送到自己的服务
WEBHOOK_PUSH_ENABLED=true
WEBHOOK_URLS=https://your-server.com/webhook,https://backup-server.com/webhook
```

---

## 数据源详解

### 中心化交易所 (CEX)

#### 1. 合约大额订单簿

- **接口**：`/api/futures/orderbook/large-limit-order`
- **说明**：当前挂单中的大额限价单（BTC 阈值 >= $1M）
- **数据字段**：订单 ID、交易所、交易对、价格、初始/当前数量和金额、成交量、买卖方向、订单状态
- **API 等级**：Standard 及以上
- **轮询间隔**：10 秒（可配置）

#### 2. 合约大额订单历史

- **接口**：`/api/futures/orderbook/large-limit-order-history`
- **说明**：已完成（成交/撤单）的历史大额限价单
- **API 等级**：Standard 及以上

#### 3. 现货大额订单簿

- **接口**：`/api/spot/orderbook/large-limit-order`
- **说明**：现货市场的大额限价单
- **API 等级**：Standard 及以上

#### 4. 爆仓订单

- **REST 接口**：`/api/futures/liquidation/order`（过去 7 天数据，支持金额筛选）
- **WebSocket 频道**：`liquidationOrders`（实时推送）
- **API 等级**：Standard 及以上

#### 5. 鲸鱼指数

- **接口**：`/api/futures/whale-index/history`
- **说明**：衡量鲸鱼活动水平的综合指标
- **API 等级**：Startup 及以上

### 去中心化交易所 (DEX)

#### 6. Hyperliquid 鲸鱼提醒

- **接口**：`/api/hyperliquid/whale-alert`
- **说明**：仓位价值超过 $1M 的实时鲸鱼交易动态
- **数据字段**：钱包地址、币种、仓位大小、入场价、强平价、仓位价值、操作类型（开仓/平仓）
- **API 等级**：Startup 及以上
- **轮询间隔**：10 秒

#### 7. Hyperliquid 鲸鱼持仓

- **接口**：`/api/hyperliquid/whale-position`
- **说明**：当前所有鲸鱼的持仓快照
- **数据字段**：钱包地址、币种、仓位大小、入场价、标记价、强平价、杠杆倍数、保证金余额、未实现盈亏、保证金模式
- **API 等级**：Startup 及以上

### 链上数据

#### 8. 交易所链上转账

- **接口**：`/api/exchange/chain/tx/list`
- **说明**：交易所之间的链上 ERC-20 代币转账记录
- **数据字段**：交易哈希、资产符号、金额（USD）、数量、交易所名称、转账类型、发送/接收地址、时间戳
- **API 等级**：Startup 及以上

---

## API 接口文档

服务启动后，访问 `http://localhost:8000/docs` 可查看自动生成的 Swagger 文档。

### REST API（Pull 模式）

#### 健康检查

```
GET /health
```

响应示例：

```json
{
  "status": "ok",
  "timestamp": 1771992058149
}
```

#### 查询大额订单

```
GET /api/orders
```

查询参数：

| 参数 | 类型 | 说明 | 默认值 |
|---|---|---|---|
| `limit` | int | 返回数量（1-500） | 50 |
| `source` | string | 数据源过滤 | 无 |
| `exchange` | string | 交易所过滤 | 无 |
| `min_amount` | float | 最小金额过滤（美元） | 无 |

`source` 可选值：`cex_futures`、`cex_spot`、`dex_hyperliquid`、`onchain`

请求示例：

```bash
# 查询最近 10 条大额订单
curl "http://localhost:8000/api/orders?limit=10"

# 查询 Hyperliquid 上超过 500 万美元的订单
curl "http://localhost:8000/api/orders?source=dex_hyperliquid&min_amount=5000000"

# 查询 Binance 的订单
curl "http://localhost:8000/api/orders?exchange=Binance"
```

响应示例：

```json
{
  "code": 0,
  "data": [
    {
      "id": "61025ce29e9685f3",
      "source": "dex_hyperliquid",
      "order_type": "whale_position",
      "exchange": "Hyperliquid",
      "symbol": "BTC-PERP",
      "side": "buy",
      "price": 65563.9,
      "amount_usd": 11455675.0,
      "quantity": 175.0,
      "status": "open",
      "timestamp": 1771989929000,
      "metadata": "{\"wallet\": \"0x931153...\", \"liq_price\": 60268.63, \"action\": \"open\"}"
    }
  ],
  "count": 1
}
```

#### 系统统计

```
GET /api/stats
```

响应示例：

```json
{
  "code": 0,
  "data": {
    "database": {
      "total_orders": 39,
      "by_source": {
        "dex_hyperliquid": 39
      },
      "by_exchange": {
        "Hyperliquid": 39
      }
    },
    "aggregator": {
      "received": 26,
      "new": 26,
      "alerted": 26
    },
    "ws_clients": 0
  }
}
```

#### 监控配置

```
GET /api/config
```

响应示例：

```json
{
  "code": 0,
  "data": {
    "exchanges": ["Binance", "OKX", "Bybit"],
    "large_order_threshold": 500000.0,
    "liquidation_threshold": 100000.0,
    "poll_intervals": {
      "large_order": 10,
      "liquidation": 10,
      "whale_alert": 10,
      "onchain": 60
    },
    "push": {
      "websocket": true,
      "webhook": false,
      "webhook_targets": 0
    }
  }
}
```

### WebSocket（Push 模式）

#### 连接

```
ws://localhost:8000/ws
```

连接成功后会收到欢迎消息：

```json
{
  "type": "connected",
  "client_id": "client_1",
  "message": "Connected to BTC Whale Order Monitor",
  "timestamp": 1771992000000
}
```

#### 心跳

发送 `ping`，返回 `pong`。

#### 告警消息格式

```json
{
  "type": "whale_alert",
  "rules": ["mega_whale", "large_cex_order"],
  "order": {
    "id": "e0cc83b089805dce",
    "source": "cex_futures",
    "type": "large_limit",
    "exchange": "Binance",
    "symbol": "BTCUSDT",
    "side": "buy",
    "price": 95000.00,
    "amount_usd": 6000000,
    "quantity": 63.2,
    "status": "open",
    "timestamp": 1771992000000
  },
  "summary": "[cex_futures] Binance BTCUSDT 🟢 买入 $6,000,000 @ 95,000.00 (large_limit)",
  "timestamp": 1771992001000
}
```

#### JavaScript 连接示例

```javascript
const ws = new WebSocket('ws://localhost:8000/ws');

ws.onopen = () => {
  console.log('已连接到鲸鱼监控');
  setInterval(() => ws.send('ping'), 20000);
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'whale_alert') {
    console.log(`🐋 ${data.summary}`);
    console.log(`   触发规则: ${data.rules.join(', ')}`);
    console.log(`   金额: $${data.order.amount_usd.toLocaleString()}`);
  }
};
```

#### Python 连接示例

```python
import asyncio
import json
import websockets

async def monitor():
    async with websockets.connect("ws://localhost:8000/ws") as ws:
        async for message in ws:
            data = json.loads(message)
            if data["type"] == "whale_alert":
                print(f"🐋 {data['summary']}")

asyncio.run(monitor())
```

### Webhook（Push 模式）

在 `.env` 中配置 Webhook：

```env
WEBHOOK_PUSH_ENABLED=true
WEBHOOK_URLS=https://your-server.com/api/whale-alert
```

系统会向配置的 URL 发送 POST 请求，请求体格式：

```json
{
  "event": "whale_alert",
  "rules": ["hyperliquid_whale"],
  "order": {
    "id": "abc123",
    "source": "dex_hyperliquid",
    "type": "whale_position",
    "exchange": "Hyperliquid",
    "symbol": "BTC-PERP",
    "side": "sell",
    "price": 65000.0,
    "amount_usd": 3000000,
    "quantity": 46.15,
    "status": "open",
    "timestamp": 1771992000000
  },
  "summary": "[dex_hyperliquid] Hyperliquid BTC-PERP 🔴 卖出 $3,000,000 @ 65,000.00 (whale_position)",
  "timestamp": 1771992001000
}
```

---

## 数据模型

### WhaleOrder — 统一鲸鱼订单模型

所有数据源的数据都统一转换为 `WhaleOrder` 模型存储和推送：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 16 位哈希唯一标识（基于 source+exchange+symbol+price+amount+timestamp 生成） |
| `source` | enum | 数据来源：`cex_futures` / `cex_spot` / `dex_hyperliquid` / `onchain` |
| `order_type` | enum | 订单类型：`large_limit` / `liquidation` / `whale_position` / `chain_transfer` |
| `exchange` | string | 交易所名称（如 Binance、Hyperliquid） |
| `symbol` | string | 交易对（如 BTCUSDT、BTC-PERP） |
| `side` | enum | 方向：`buy` / `sell` / `unknown` |
| `price` | float | 价格（美元） |
| `amount_usd` | float | 金额（美元） |
| `quantity` | float | 数量（BTC） |
| `status` | enum | 状态：`open` / `filled` / `cancelled` / `unknown` |
| `timestamp` | int | 时间戳（毫秒） |
| `metadata` | dict | 源数据特有字段（如钱包地址、交易哈希、强平价等） |

### 不同数据源的 metadata 示例

**CEX 大额订单**：

```json
{
  "start_usd": 2299638.89,
  "executed_usd": 515520.89,
  "trade_count": 15
}
```

**DEX Hyperliquid**：

```json
{
  "wallet": "0x931153baac031d055389b41d12cd32c9bf0ae7a3",
  "liq_price": 60268.63,
  "action": "open"
}
```

**链上转账**：

```json
{
  "tx_hash": "0xe2e2dce7dfccaa...",
  "from": "0x21a31ee1afc51d...",
  "to": "0xc4067b2c6ce55c..."
}
```

---

## 告警规则引擎

系统内置 5 条默认告警规则，满足条件时触发 Push 通知：

| 规则名称 | 触发条件 | 说明 |
|---|---|---|
| `mega_whale` | 任意来源，金额 >= **$5,000,000** | 超级鲸鱼，不限交易所和类型 |
| `large_cex_order` | CEX 合约/现货，大额限价单，金额 >= **$1,000,000** | CEX 大单监控 |
| `large_liquidation` | 爆仓订单，金额 >= **$500,000** | 大额爆仓监控 |
| `hyperliquid_whale` | Hyperliquid 来源，金额 >= **$1,000,000** | DEX 鲸鱼监控 |
| `large_onchain` | 链上转账，金额 >= **$10,000,000** | 链上巨额转账 |

### 规则匹配逻辑

一条订单可以同时触发多条规则。例如，一笔 $6M 的 Binance 大额限价单会同时触发 `mega_whale` 和 `large_cex_order`。

### 自定义规则

可通过代码添加自定义规则：

```python
from src.engine.alert_rules import AlertRule
from src.models.whale_order import OrderSide

engine.add_rule(AlertRule(
    name="binance_sell_alert",
    min_amount_usd=200_000,
    exchanges=["Binance"],
    sides=[OrderSide.SELL],
))
```

支持的过滤维度：

- `min_amount_usd`：最小金额阈值
- `sources`：数据来源列表
- `order_types`：订单类型列表
- `exchanges`：交易所列表
- `sides`：买卖方向列表

---

## CoinGlass API 等级说明

不同接口对 API 等级的要求不同。系统会在启动时自动检测，对于等级不足的接口会优雅降级（打印一次警告后暂停该采集器，不影响其他功能）。

| API 等级 | 价格 | 频率限制 | 可用数据源 |
|---|---|---|---|
| **Hobbyist** | $29/月 | 30次/分 | 支持币种、交易所列表 |
| **Startup** | $79/月 | 80次/分 | + 鲸鱼指数、Hyperliquid 鲸鱼提醒/持仓、链上转账 |
| **Standard** | $299/月 | 300次/分 | + 合约/现货大额订单簿、爆仓订单、WebSocket |
| **Professional** | $699/月 | 1200次/分 | + 扩展历史数据范围 |
| **Enterprise** | 定制 | 6000次/分 | 全量接口 |

### API 频率预算估算（Standard 等级，300次/分）

| 采集器 | 计算方式 | 请求数/分钟 |
|---|---|---|
| 合约大额订单 | 3 交易所 x 6 次/分 | 18 |
| 现货大额订单 | 3 交易所 x 6 次/分 | 18 |
| 爆仓订单 | 3 交易所 x 6 次/分 | 18 |
| Hyperliquid | 6 次/分 | 6 |
| 链上转账 | 1 次/分 | 1 |
| **合计** | | **~61 次/分** |

余量充足，可安全运行。

---

## 测试

项目包含两套测试：

### 单元测试 + 集成测试

```bash
python tests/test_all.py
```

覆盖 9 大模块、49 项测试：
- 数据模型（创建、ID 生成、序列化）
- 数据解析（大额订单、爆仓订单、WebSocket 消息）
- 告警引擎（规则匹配、自定义规则、边界条件）
- 数据库（CRUD、去重、多维查询、统计）
- 聚合引擎（去重、告警分发）
- API 客户端（真实 API 调用）
- 采集器（端到端数据采集）
- 推送层（WebSocket 管理器）
- 配置管理（加载验证）

### 数据质量测试

```bash
python tests/test_data_quality.py
```

覆盖 12 大模块、273 项测试，基于真实 API 数据验证：
- CEX 交易所元数据验证（31 个交易所、交易对字段完整性）
- CEX 支持币种验证（1020 个币种）
- CEX 鲸鱼指数数据验证（时间戳、单调性、值域）
- CEX 大额订单解析准确性（官方文档格式、边界条件）
- CEX 爆仓订单解析准确性（REST + WebSocket 两种格式）
- DEX Hyperliquid 鲸鱼提醒验证（Schema、类型、范围、钱包格式、强平价一致性）
- DEX Hyperliquid 鲸鱼持仓验证（14 字段覆盖率、杠杆范围、mark_price 一致性、多空分布）
- 链上转账数据验证（tx_hash 格式、地址格式、资产分布、交易所分布）
- 采集器转换准确性（逐字段验证）
- 全链路端到端验证（采集 → 聚合 → 存储 → 查询 → 去重 → 告警）
- 跨数据源一致性验证（价格偏差、钱包方向一致性）

测试结果和数据样本会自动输出到桌面 `BTC_Whale_Test_Data/` 目录。

---

## 常见问题

### 1. 启动后看到 "Upgrade plan" 警告

```
[futures_large_order] API plan insufficient, collector paused. Upgrade your CoinGlass plan to enable.
```

这是正常现象。你的 CoinGlass API 等级不支持该接口，系统会自动暂停对应采集器。升级 API 等级后重启即可自动启用。其他等级满足的采集器不受影响。

### 2. 如何连接 WebSocket 测试？

```bash
# 使用 websocat 工具
websocat ws://localhost:8000/ws

# 或使用 Python
python -c "
import asyncio, websockets, json
async def test():
    async with websockets.connect('ws://localhost:8000/ws') as ws:
        async for msg in ws:
            print(json.loads(msg))
asyncio.run(test())
"
```

### 3. 如何修改监控的交易所？

编辑 `.env` 文件中的 `EXCHANGES` 配置项，多个交易所用逗号分隔：

```env
EXCHANGES=Binance,OKX,Bybit,Bitget,Coinbase
```

支持的交易所可通过 API 查看：

```bash
curl "http://localhost:8000/api/config"
```

### 4. 数据存储在哪里？

默认存储在项目根目录下的 `data/whale_orders.db`（SQLite 文件）。可通过 `DB_PATH` 配置修改。Docker 部署时数据挂载在 `whale_data` 卷中，容器重启不会丢失。

### 5. 如何查看已采集的数据量？

```bash
curl "http://localhost:8000/api/stats"
```

返回包含数据库总量、按来源/交易所分布、聚合器统计和 WebSocket 客户端数等信息。
