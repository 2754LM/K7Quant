"""controllers - HTTP 控制器层 (薄编排, 只做 req/res 适配)

每个 controller 对应一个域:
- backtest_api.py:  回测 API (单币 / 池扫描 / 自定义代码 / K线 / 历史 / 筛选)
- config_api.py:    配置 API (回测 / 数据源 / UI / 交易)
- data_api.py:      数据 API (缓存 / 拉取 / 交易所 / 连接 / 日志)
- factor_api.py:    因子 API (列表 / 计算 / 相关性 / 排名 / 自定义)
- rule_api.py:      自定义规则 API
- strategy_api.py:  策略 API (CRUD / 模板 / DSL 文档 / 校验)
- symbol_api.py:    币种 API (列表 / 详情 / 活跃池)
- trade_api.py:     交易 API (状态 / 下单 / 撤单 / 模拟盘 / 实盘)
- verify_api.py:    验证测试模块 (独立小数据回测, 每步严格回显)

约定:
- 每个 controller 一个 router = APIRouter(prefix="/api/<domain>", tags=[...])
- endpoint 函数尽量薄: 解析 req → 调 service → 返回 dict
- 业务异常 raise backend.exceptions.domain.* 让 handlers 统一处理
- 不直接 import repositories/, 走 services/ 间接访问
"""
from . import backtest_api as backtest_controller
from . import config_api as config_controller
from . import data_api as data_controller
from . import factor_api as factor_controller
from . import rule_api as rule_controller
from . import strategy_api as strategy_controller
from . import symbol_api as symbol_controller
from . import trade_api as trade_controller
from . import verify_api as verify_controller


__all__ = [
    "backtest_controller", "config_controller", "data_controller",
    "factor_controller", "rule_controller", "strategy_controller",
    "symbol_controller", "trade_controller", "verify_controller",
]