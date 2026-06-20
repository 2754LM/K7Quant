<script setup>
import { ref, onMounted, computed } from 'vue'
import { getTradeStatus, listTrades } from '../api'
import StateView from '../components/StateView.vue'

const status = ref({})
const trades = ref([])
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  try {
    const [s, t] = await Promise.all([getTradeStatus(), listTrades(null, 50)])
    status.value = s.data
    trades.value = t.data.trades
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="trade-page">
    <div class="card placeholder">
      <div class="placeholder-icon">🚧</div>
      <h2>交易模块 (占位)</h2>
      <p>模拟盘 / 实盘功能尚未实装, 这里只展示当前状态</p>
      <div class="status-grid" v-if="Object.keys(status).length">
        <div class="stat">
          <span class="lbl">启用</span>
          <span class="val" :class="status.enabled ? 'pos' : ''">
            {{ status.enabled ? '是' : '否' }}
          </span>
        </div>
        <div class="stat">
          <span class="lbl">模式</span>
          <span class="val">{{ status.mode === 'simulation' ? '模拟盘' : '实盘' }}</span>
        </div>
        <div class="stat">
          <span class="lbl">单币最大仓位</span>
          <span class="val">{{ ((status.max_position_pct || 0) * 100).toFixed(0) }}%</span>
        </div>
        <div class="stat">
          <span class="lbl">止损</span>
          <span class="val">{{ ((status.stop_loss_pct || 0) * 100).toFixed(1) }}%</span>
        </div>
        <div class="stat">
          <span class="lbl">止盈</span>
          <span class="val">{{ ((status.take_profit_pct || 0) * 100).toFixed(1) }}%</span>
        </div>
      </div>
      <div class="coming-soon">
        <strong>即将到来:</strong> Webhook 信号推送 · 自动下单 · 实时盈亏跟踪
      </div>
      <p class="hint">在「配置中心」 → 「交易」可调整这些参数</p>
    </div>

    <div class="card">
      <h3>交易记录 (最近 50 条)</h3>
      <StateView :loading="loading" :error="error" empty-text="暂无交易" empty-icon="📋" />
      <table v-if="!loading && !error && trades.length">
        <thead><tr><th>时间</th><th>模式</th><th>币种</th><th>方向</th><th>价格</th><th>数量</th><th>盈亏</th></tr></thead>
        <tbody>
          <tr v-for="t in trades" :key="t.id">
            <td>{{ t.created_at }}</td>
            <td>{{ t.mode === 'simulation' ? '模拟' : '实盘' }}</td>
            <td class="sym-cell">{{ t.symbol }}</td>
            <td :class="t.side === 'buy' ? 'pos' : 'neg'">
              {{ t.side === 'buy' ? '买入' : '卖出' }}
            </td>
            <td>{{ Number(t.price).toFixed(4) }}</td>
            <td>{{ Number(t.amount).toFixed(4) }}</td>
            <td :class="t.pnl >= 0 ? 'pos' : 'neg'">{{ Number(t.pnl).toFixed(2) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.trade-page { display: flex; flex-direction: column; gap: 16px; }
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 24px;
}
.placeholder { text-align: center; }
.placeholder-icon { font-size: 64px; margin-bottom: 16px; }
.placeholder h2 { font-size: 20px; color: var(--yellow); margin-bottom: 8px; }
.placeholder > p { color: var(--text-secondary); }
.status-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
  margin: 24px 0;
}
.stat {
  background: var(--bg);
  border: 1px solid var(--border);
  padding: 12px;
  border-radius: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.stat .lbl { font-size: 11px; color: var(--text-secondary); }
.stat .val { font-size: 18px; font-weight: 600; color: var(--yellow); font-family: 'Consolas', monospace; }
.stat .val.pos { color: var(--green); }
.coming-soon {
  background: rgba(240,185,11,0.08);
  border: 1px solid rgba(240,185,11,0.3);
  padding: 12px;
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  margin: 16px 0;
}
.coming-soon strong { color: var(--yellow); margin-right: 8px; }
.hint { font-size: 12px; color: var(--text-muted); }
table { width: 100%; border-collapse: collapse; margin-top: 12px; }
th {
  text-align: left;
  padding: 10px 12px;
  background: var(--bg);
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 500;
  border-bottom: 1px solid var(--border);
}
td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  font-family: 'Consolas', monospace;
}
.sym-cell { font-weight: 600; color: var(--yellow); }
.pos { color: var(--green); }
.neg { color: var(--red); }
</style>