## 📝Summary
实现了 Polymarket 链上市场与交易数据的索引器（Stage 2），包括自动市场发现、历史交易回溯同步、以及基于 FastAPI 的查询服务。

## ✨ Key Features

### 1. Market Discovery Service (`src/indexer/market_discovery.py`)
- 集成了 Gamma API，定期拉取并更新市场元数据。
- 实现了链上参数（Client ID, Token IDs）与 Gamma 数据的交叉验证。
- 数据持久化至 `markets` 表，支持增量更新。

### 2. Trades Indexer (`src/indexer/run.py`)
- 基于 `eth_getLogs` 实现了 Exchange 合约的 `OrderFilled` 事件扫描。
- 核心功能：
  - **Backfill**: 支持指定区块范围的历史数据同步。
  - **Decoding**: 解析交易日志，关联 Market ID，计算价格和数量。
  - **Idempotency**: 利用 `(tx_hash, log_index)` 唯一键防止重复写入。
  - **Checkpoint**: 维护 `sync_state` 表，支持断点续传。

### 3. API Server (`src/api/server.py`)
- 提供了 RESTful API 用于数据查询：
  - `GET /markets/{slug}`: 获取市场详情。
  - `GET /markets/{slug}/trades`: 分页查询交易历史。

### 4. Database & Infrastructure
- 设计了 SQLite 数据库 Schema (`markets`, `trades`, `sync_state`)。
- 包含了错误重试（Resilience）和数据一致性处理逻辑。

## 🧪 Testing
- 已通过 Demo 脚本 `src/demo.py` 验证：
  - [x] 市场发现功能正常。
  - [x] 指定 TX Hash 和区块范围的交易能够正确索引。
  - [x] 两个核心 API 端点响应正确。

## ⚠️ Notes
- 需配置 `.env` 文件中的 `RPC_URL` 才能运行。
- 首次运行时会自动初始化 SQLite 数据库。
