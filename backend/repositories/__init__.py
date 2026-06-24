"""repositories - 数据访问层 (DB + 远端 API + 缓存)

放置:
- models.py:        SQLAlchemy 2.0 ORM (Symbol/Strategy/Factor/CustomRule/BacktestRun/Trade)
- crud.py:          DB CRUD 兼容层 (旧 crud.xxx 调用转发到 models)
- binance_fetcher.py: Binance 公开 REST API
- binance_cache.py: 本地 Parquet 缓存
- binance_data.py:  统一访问 (get_kline / get_many) - 编排 fetcher + cache
- demo_client.py:   Binance Demo 账户 (模拟盘)

区别于 core/ (纯计算) 和 services/ (业务编排):
repositories 负责一切 I/O 边界 (DB 读写 / HTTP 调用 / 文件缓存)。

不依赖 services/, 也不被 core/ 依赖。services/ 同时调 core/ 和 repositories/。
"""