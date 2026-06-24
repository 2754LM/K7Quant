"""services - 业务逻辑编排层

调 core/ (纯计算) + repositories/ (DB/Binance) 组合出业务能力。
被 controllers/ 调用, 不直接对外。

每个 service 对应一个域:
- backtest_service: 回测编排 (拉数据 → 跑策略 → 算指标 → 生成图表)
- config_service:   配置读写 / 导出
- data_service:     数据下载触发 / 缓存清理
- factor_service:   因子 CRUD / 自定义 DSL 因子
- strategy_service: 策略 CRUD / 内置策略注册 / 编译测试
- symbol_service:   币种 CRUD / 活跃池 / 内置币种注册
- trade_service:    模拟盘下单/撤单/查询/重置
- live_trader:      策略实盘 runner (单例 + 后台线程)

不直接 import controllers/, 不 import fastapi。
"""