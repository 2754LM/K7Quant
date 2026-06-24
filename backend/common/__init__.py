"""common - 通用基础设施层

放置:
- models.py: SQLAlchemy 2.0 ORM 模型
- helpers.py: 通用工具 (df_dates, to_records, sanitize, fmt)
- data/: 数据下载/缓存/访问 (Binance fetcher + cache + access + demo client)
- storage/: DB CRUD 兼容层 (旧 crud.xxx 转发到 models)
- services/: 业务编排层 (调用 core 计算 + DB CRUD)

区别于 core/ (纯计算, 无 I/O) 和 api/ (HTTP 路由):
common 包含一切"需要 I/O 但与 HTTP 无关"的东西 (数据库 / 网络 / 文件)。
"""