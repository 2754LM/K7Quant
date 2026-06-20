# K7Quant - AI Agent 工作指南

本文件帮助 AI Agent (Claude/Cursor/Copilot 等) 快速理解项目并高效修改代码。

## 项目一句话总结

基于 Binance 公开 API 的加密货币量化回测系统，FastAPI + Vue3 + YAML 配置，4 种内置策略。

## 关键文件位置

| 想改什么 | 必读文件 |
|---------|---------|
| 加新策略 | `quant_core/strategies/base.py` 看基类 → 新建文件 → `strategies/__init__.py` 注册 |
| 改回测逻辑 | `quant_core/backtest/engine.py` (Backtester.run) + `metrics.py` (compute_metrics) |
| 改配置项 | `config/settings.yaml` + `quant_core/settings.py` (C 类) + 前端 `Settings.vue` |
| 加币种元信息 | `config/symbols.yaml` (中文名/英文/分类/市值排名/简介/tags) |
| 改 API 路由 | `backend/routers/` 按域加 endpoint → `app.py` include_router |
| 改业务逻辑 | `backend/services/` (注意与 router 解耦) |
| 改前端页面 | `frontend/src/views/` + 必要时 `components/` |
| 改前端样式 | `frontend/src/style.css` 全局 + 每个 .vue 的 `<style scoped>` |

## 代码规范

### Python

- 缩进: 4 空格
- import 顺序: 标准库 → 第三方 → 本地
- 类型提示: 函数参数和返回值必须有
- 文档字符串: 模块/类/公开函数都要 docstring
- 单文件不超过 500 行（超出就拆）

### Vue

- Composition API + `<script setup>`
- 每个 prop 都要 `defineProps` 声明
- 事件用 `defineEmits` 声明
- 全局样式用 `style.css`，组件私有样式用 `<style scoped>`
- 颜色变量用 CSS 变量（在 `style.css` 定义）

## 添加新策略的标准流程

1. 在 `quant_core/strategies/` 新建 `my_strategy.py`:

```python
from quant_core.strategies.base import Strategy
import pandas as pd

class MyStrategy(Strategy):
    id = "my_strategy"  # 全小写下划线
    name = "我的策略"
    icon = "🎯"
    description = "策略说明（白话）"
    category = "trend"  # trend / momentum / mean_reversion / breakout

    params_schema = {
        "my_param": {"label": "参数", "type": "int", "default": 14, "min": 2, "max": 100},
    }

    def generate(self, df: pd.DataFrame) -> pd.DataFrame:
        # 必须返回包含 date/close/position (0/1) 的 DataFrame
        out = df.copy()
        out["position"] = 0
        # ... 计算逻辑
        return out[["date", "close", "position"]].dropna().reset_index(drop=True)
```

2. 在 `quant_core/strategies/__init__.py` 注册:

```python
from quant_core.strategies.my_strategy import MyStrategy

ALL_STRATEGIES.append(MyStrategy())
```

3. 重启服务，前端自动显示新策略。

**前端无需任何改动！** StrategyPicker / Dashboard / Settings 都会自动识别。

## 添加新 API 端点

1. 在 `backend/routers/` 对应文件加 endpoint:

```python
@router.get("/my-endpoint")
def my_endpoint():
    # 注意：业务逻辑放 services/，router 只做编排
    return {"data": ...}
```

2. 如果是新的域，新建 `backend/routers/my_domain.py`，然后在 `backend/app.py` 注册:

```python
from backend.routers import my_domain as my_domain_router
app.include_router(my_domain_router.router)
```

## 修改配置项

1. 在 `config/settings.yaml` 加新字段
2. 在 `quant_core/settings.py` 的 `C` 类加便捷访问器:

```python
class C:
    @staticmethod
    def my_thing():
        return C.get("my_thing", "default")
```

3. 前端 `Settings.vue` 加表单 + 保存调用 (`setBacktestDefaults` / 新建对应 endpoint)

## 调试技巧

### 后端

```bash
# 直接测函数（无需启动 server）
python -c "from backend.services.backtest_service import scan_pool; print(scan_pool(...))"

# 查日志
cat server.err.log
```

### 前端

```bash
# 开发模式（热更新）
cd frontend && npm run dev

# 构建生产
npm run build
```

### API 测试

```bash
# 健康检查
curl http://127.0.0.1:8765/api/health

# 看配置
curl http://127.0.0.1:8765/api/config | python -m json.tool

# 跑扫描
curl -X POST http://127.0.0.1:8765/api/backtest/scan \
  -H "Content-Type: application/json" \
  -d '{"strategy":"ma_cross","timeframe":"4h","start_date":"20250101","end_date":"20250601"}'
```

## 常见陷阱

1. **缓存锁**: `update_settings` 已修复 reentrant 死锁，不要再在锁内调用 `load_settings`
2. **单例初始化顺序**: `data/access.py` 自己管理 fetcher/cache 单例，不要全局变量
3. **YAML 编码**: 始终用 `encoding="utf-8"` 打开
4. **Pydantic 模型**: router 的请求体必须用 BaseModel 声明，service 层不用
5. **前端代理**: dev 模式 vite 配置了 `/api` → 后端 8765，生产用 nginx 或 FastAPI 直接 serve
6. **Binance API 限流**: fetcher 加了 0.2-0.25s 间隔，不要去掉

## 部署清单

部署到生产前检查:
- [ ] `config/settings.yaml` 中 `server.host` 改成 `0.0.0.0`
- [ ] CORS 限制具体域名（不要用 `*`）
- [ ] 启用 HTTPS
- [ ] 添加用户认证（目前无）
- [ ] 限制 API 调用频率
- [ ] 日志收集（uvicorn log level 改成 info）

## 优先实现的功能 (Roadmap)

按 ROI 排序：

1. **参数扫描器**: `POST /api/backtest/sweep` 网格搜索，自动找最优
2. **样本外验证**: 自动划分训练/测试集，对比两组夏普
3. **更多策略**: Bollinger Bands, ATR止损, 海龟交易法
4. **实盘对接**: Binance Futures Testnet API 下单
5. **信号推送**: webhook + 微信/钉钉提醒
6. **Walk-forward**: 滚动窗口回测
7. **多因子选股**: PE/PB/ROE + 技术面综合打分

## Bug 报告 / 改进建议

在 GitHub Issues 提交：https://github.com/2754LM/K7Quant/issues