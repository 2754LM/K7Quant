<script setup>
const indicators = [
  { icon: '📏', name: '均线 MA', short: '过去 N 根 K 线收盘价的平均值',
    long: '把过去 N 根收盘价加总除以 N。短期均线 (MA7) 反映最近价格情绪, 长期均线 (MA25/99) 反映更大趋势。',
    usage: 'MA 短上穿长 = 金叉做多, 下穿 = 死叉平仓', tip: '震荡市容易假信号' },
  { icon: '🚀', name: '动量 Momentum', short: '过去 N 根涨幅排名',
    long: '计算每根 K 线过去 N 根的涨幅, 正数说明涨, 负数说明跌。',
    usage: '动量轮动: 每周期选过去 N 根涨幅最高 Top K 买入', tip: '趋势市/牛市好用' },
  { icon: '⚖️', name: '夏普比率', short: '每承担一单位风险换多少收益',
    long: '(年化收益 - 无风险利率) / 年化波动率。简单说: 性价比。',
    usage: '> 1 不错, > 2 优秀, < 0 别碰', tip: '比较策略时优先看' },
  { icon: '📉', name: '最大回撤', short: '从最高点跌下来的最大幅度',
    long: '回测期间任意时刻相比之前最高点的跌幅最大值。',
    usage: '< 20% 可接受, > 50% 心理压力大', tip: '回撤大不代表策略差' },
  { icon: '🔗', name: 'Beta', short: '与 BTC 的相关性',
    long: '策略相对 BTC 的波动倍数。Beta=1.0 表示和 BTC 同步。',
    usage: '低 Beta (0.3-0.7) 稳健, 高 Beta (>1.5) 激进', tip: '币圈 BTC 是基准' },
  { icon: '🌊', name: '波动率', short: '价格上下蹦跶的剧烈程度',
    long: '收益率的标准差 × √年化系数。币圈波动远高于股市。',
    usage: 'BTC 50% 正常, 山寨币 100%+ 是常态', tip: '高波动 ≠ 高收益' },
  { icon: '🎯', name: 'Calmar', short: '收益 / 最大回撤',
    long: '年化收益除以最大回撤的绝对值。衡量"冒着多大风险赚的钱"。',
    usage: '> 1.5 优秀, > 3 神级', tip: '比 Sharpe 更直观' },
  { icon: '✅', name: '胜率', short: '赚钱的 K 线占比',
    long: '收益为正的 K 线数 / 总交易 K 线数。',
    usage: '> 50% 较好, 但胜率高不等于赚钱多', tip: '盈亏比更重要' },
  { icon: '🆎', name: 'Alpha', short: '超额收益 (扣 Beta 后)',
    long: '策略相对基准 (BTC) 的纯超额收益, 反映选币能力。',
    usage: '> 0 跑赢 BTC, > 0.1 显著', tip: '用 BTC 做基准' },
]

const concepts = [
  { title: 'K 线周期', desc: '1m=1分钟, 15m=15分钟, 1h=1小时, 4h=4小时, 1d=日线, 1w=周线。短线用小周期, 长线用大周期。' },
  { title: '现货 vs 合约', desc: '现货只做多, 合约可做空可加杠杆。本系统默认现货模式, 杠杆=1就是现货。' },
  { title: '复利效应', desc: '年化 50% 看似普通, 5 年后 1 万变 7.6 万。回测要尽量拉长周期。' },
  { title: '手续费', desc: 'Binance 现货 0.1%, VIP 用户更低。频繁交易容易被手续费吃掉。' },
  { title: '滑点', desc: '回测按收盘价算, 实盘有滑点。保守起见, 每次交易额外扣 0.05%。' },
  { title: '样本外测试', desc: '用 2024 数据调参数 (样本内), 留 2025 数据验证 (样本外)。差距太大就是过拟合。' },
  { title: '金叉死叉', desc: '短均线上穿长均线叫"金叉"是买入信号; 下穿叫"死叉"是卖出信号。' },
  { title: '回撤 vs 亏损', desc: '回撤是浮亏, 亏损是已实现。回撤大但涨回来没事, 回撤大又割肉才真亏。' },
]
</script>

<template>
  <div class="learn-view">
    <div class="hero">
      <h2>📚 量化指标一本通</h2>
      <p>看不太懂的术语都在这里 · 白话讲解 + 实战例子</p>
    </div>

    <div class="indicators-grid">
      <div v-for="ind in indicators" :key="ind.name" class="indicator-card">
        <div class="ind-header">
          <span class="icon">{{ ind.icon }}</span>
          <h3>{{ ind.name }}</h3>
        </div>
        <div class="short">{{ ind.short }}</div>
        <div class="long">{{ ind.long }}</div>
        <div class="section">
          <span class="badge">怎么用</span>
          <p>{{ ind.usage }}</p>
        </div>
        <div class="tip">💡 {{ ind.tip }}</div>
      </div>
    </div>

    <div class="concepts-section">
      <h2>🧠 必须懂的核心概念</h2>
      <div class="concepts-grid">
        <div v-for="(c, i) in concepts" :key="i" class="concept-card">
          <h4>{{ c.title }}</h4>
          <p>{{ c.desc }}</p>
        </div>
      </div>
    </div>

    <div class="workflow">
      <h2>🔄 量化策略的标准工作流</h2>
      <div class="steps">
        <div class="step"><div class="num">1</div><h4>观察现象</h4><p>币圈 24h 不停盘, 找规律</p></div>
        <div class="arrow">→</div>
        <div class="step"><div class="num">2</div><h4>形成假设</h4><p>"过去 20 根涨的下一根还会涨"</p></div>
        <div class="arrow">→</div>
        <div class="step"><div class="num">3</div><h4>回测验证</h4><p>看夏普多少、回撤多大</p></div>
        <div class="arrow">→</div>
        <div class="step"><div class="num">4</div><h4>样本外测试</h4><p>留 3 个月数据验证</p></div>
        <div class="arrow">→</div>
        <div class="step"><div class="num">5</div><h4>模拟盘</h4><p>实盘前 1-3 个月</p></div>
        <div class="arrow">→</div>
        <div class="step"><div class="num">6</div><h4>小仓实盘</h4><p>先 10% 资金跑</p></div>
      </div>
    </div>

    <div class="warning-box">
      <h3>⚠️ 重要提醒</h3>
      <ul>
        <li><strong>币圈 7×24 小时</strong>, 没有熔断, 暴跌时无法出场</li>
        <li><strong>过去表现不代表未来</strong>: 2021 牛市策略 2022 熊市必亏</li>
        <li><strong>过拟合是最大坑</strong>: 参数调太完美反而坏事</li>
        <li><strong>本系统只是研究工具</strong>, 不构成投资建议</li>
        <li><strong>先求不亏再求赚</strong>: 回撤 &lt; 30% 优于年化 +100%</li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.learn-view { display: flex; flex-direction: column; gap: 24px; max-width: 1200px; margin: 0 auto; }
.hero {
  background: linear-gradient(135deg, rgba(240,185,11,0.15), transparent);
  border: 1px solid rgba(240,185,11,0.4);
  border-radius: 16px;
  padding: 32px;
  text-align: center;
}
.hero h2 { font-size: 28px; margin-bottom: 8px; color: var(--yellow); }
.hero p { color: var(--text-secondary); }
.indicators-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}
.indicator-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
}
.ind-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.ind-header .icon { font-size: 28px; }
.ind-header h3 { font-size: 18px; color: var(--yellow); }
.short {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
}
.long { font-size: 13px; color: var(--text-secondary); line-height: 1.7; margin-bottom: 16px; }
.section {
  margin-bottom: 12px;
  padding: 10px;
  background: var(--bg);
  border-radius: 6px;
  border-left: 3px solid var(--yellow);
}
.section .badge {
  display: inline-block;
  background: var(--yellow);
  color: #000;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  margin-right: 8px;
  font-weight: 600;
}
.section p { display: inline; font-size: 13px; line-height: 1.6; }
.tip {
  margin-top: 12px;
  padding: 8px 12px;
  background: rgba(30,136,229,0.1);
  border-radius: 6px;
  font-size: 12px;
  color: #64b5f6;
}
.concepts-section h2 { font-size: 20px; margin-bottom: 16px; }
.concepts-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.concept-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 16px;
}
.concept-card h4 { font-size: 14px; color: var(--yellow); margin-bottom: 8px; }
.concept-card p { font-size: 13px; color: var(--text-secondary); line-height: 1.6; }
.workflow {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 24px;
}
.workflow h2 { font-size: 20px; margin-bottom: 16px; }
.steps { display: flex; gap: 8px; align-items: stretch; flex-wrap: wrap; }
.step {
  flex: 1;
  min-width: 130px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  text-align: center;
}
.step .num {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--yellow);
  color: #000;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 8px;
}
.step h4 { font-size: 13px; margin-bottom: 6px; }
.step p { font-size: 11px; color: var(--text-secondary); line-height: 1.5; }
.arrow { display: flex; align-items: center; color: var(--yellow); font-size: 20px; }
.warning-box {
  background: rgba(246,70,93,0.08);
  border: 1px solid rgba(246,70,93,0.3);
  border-radius: 12px;
  padding: 20px;
}
.warning-box h3 { color: var(--red); margin-bottom: 12px; font-size: 18px; }
.warning-box ul { list-style: none; padding-left: 0; }
.warning-box li {
  padding: 8px 0 8px 24px;
  position: relative;
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-secondary);
}
.warning-box li::before {
  content: '⚠';
  position: absolute;
  left: 0;
  color: var(--red);
}
.warning-box strong { color: var(--red); }

@media (max-width: 900px) {
  .indicators-grid { grid-template-columns: 1fr; }
  .concepts-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>