<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import {
  NSelect, NInput, NButton, NTag, NDataTable, NCard, NSpace, NAlert,
  NInputNumber, NRadioGroup, NRadioButton, NStatistic, NDivider, NCollapse,
  NCollapseItem, NCode, NTooltip, NIcon, NSwitch,
} from 'naive-ui'
import { listVerifyDatasets, runVerify } from '../api'

const datasets = ref([])
const codeType = ref('dsl')
const dataset = ref('uptrend')
const initialCapital = ref(10000)
const commissionRate = ref(0.0004)
const slippage = ref(0.0005)
const positionSize = ref(1.0)
const useCustomData = ref(false)
const customCsv = ref('')
const result = ref(null)
const loading = ref(false)
const error = ref('')

const dslTemplate = `# 信号: 当收盘价站上 3 根均线时买入
signal = close > MA(close, 3)
止损 = 0
止盈 = 0
仓位 = 1.0`

const pythonTemplate = `def init():
    return {"bought": False, "entry": 0}

def on_bar(state):
    p = ctx.now()
    if not state["bought"]:
        buy(100)
        state["bought"] = True
        state["entry"] = p
    elif p < state["entry"] * 0.99:
        # 跌 1% 加仓
        buy(100)
        state["entry"] = p
    elif p > state["entry"] * 1.03:
        # 涨 3% 平仓
        sell_all()
        state["bought"] = False`

const code = ref(dslTemplate)

onMounted(async () => {
  try {
    const r = await listVerifyDatasets()
    datasets.value = r.data.datasets
  } catch (e) {
    error.value = String(e)
  }
})

watch(codeType, (v) => {
  code.value = v === 'python' ? pythonTemplate : dslTemplate
})

const datasetOpts = computed(() =>
  datasets.value.map(d => ({
    label: `${d.id} (${d.rows} bars, buy&hold ${(d.buy_hold_return * 100).toFixed(2)}%)`,
    value: d.id,
    description: d.description,
  }))
)

const selectedDataset = computed(() =>
  datasets.value.find(d => d.id === dataset.value)
)

function parseCustomCsv() {
  // 解析: date,open,high,low,close,volume (每行一根 bar)
  const lines = customCsv.value.trim().split('\n').filter(l => l.trim())
  if (lines.length < 2) throw new Error('至少需要 1 行表头 + 1 行数据')
  const header = lines[0].split(',').map(s => s.trim().toLowerCase())
  const idx = (name) => header.indexOf(name)
  const need = ['date', 'open', 'high', 'low', 'close']
  for (const n of need) {
    if (idx(n) < 0) throw new Error(`缺少列: ${n}`)
  }
  const dates = [], open = [], high = [], low = [], close = [], volume = []
  for (let i = 1; i < lines.length; i++) {
    const cells = lines[i].split(',').map(s => s.trim())
    dates.push(cells[idx('date')])
    open.push(parseFloat(cells[idx('open')]))
    high.push(parseFloat(cells[idx('high')]))
    low.push(parseFloat(cells[idx('low')]))
    close.push(parseFloat(cells[idx('close')]))
    volume.push(idx('volume') >= 0 ? parseFloat(cells[idx('volume')]) : 1000)
  }
  return { dates, open, high, low, close, volume }
}

async function run() {
  error.value = ''
  result.value = null
  loading.value = true
  try {
    const payload = {
      code_type: codeType.value,
      code: code.value,
      dataset: useCustomData.value ? 'custom' : dataset.value,
      initial_capital: initialCapital.value,
      commission_rate: commissionRate.value,
      slippage: slippage.value,
      position_size: positionSize.value,
    }
    if (useCustomData.value) {
      payload.custom_data = parseCustomCsv()
    }
    const r = await runVerify(payload)
    result.value = r.data
    logInfo('verify', `验证完成: bars=${r.data.summary.bars}, ret=${(r.data.summary.total_return*100).toFixed(2)}%`)
  } catch (e) {
    error.value = String(e)
    logError('verify', `验证失败: ${e}`)
  } finally {
    loading.value = false
  }
}

function pct(v) {
  if (v == null) return 'N/A'
  return (v * 100).toFixed(2) + '%'
}
function num(v, d = 4) {
  if (v == null) return 'N/A'
  return Number(v).toFixed(d)
}

const traceColumns = [
  { title: 'Bar', key: 'bar', width: 50, fixed: 'left' },
  { title: 'Date', key: 'date', width: 100 },
  { title: 'Open', key: 'open', width: 80 },
  { title: 'High', key: 'high', width: 80 },
  { title: 'Low', key: 'low', width: 80 },
  { title: 'Close', key: 'close', width: 80 },
  { title: 'Signal', key: 'signal', width: 70 },
  { title: 'Pos→', key: 'position_after', width: 60 },
  { title: 'Action', key: 'action', width: 90,
    render: (row) => {
      const tagType = row.action === 'buy' ? 'success' : row.action === 'sell' ? 'error' : 'default'
      return h(NTag, { type: tagType, size: 'small', round: true }, () => row.action)
    }
  },
  { title: 'Fee', key: 'fee_paid', width: 70 },
  { title: 'Qty', key: 'qty_after', width: 90 },
  { title: 'Cash', key: 'cash_after', width: 90 },
  { title: 'Equity', key: 'equity', width: 100,
    render: (row) => h('span', { style: { color: row.equity > initialCapital ? '#02c076' : '#f6465d' } }, num(row.equity, 2))
  },
]

import { h } from 'vue'
import { info as logInfo, error as logError } from '../utils/systemLog'
</script>

<template>
  <div class="verify-root">
    <n-card title="✅ 验证测试模块" size="small" class="verify-card">
      <template #header-extra>
        <n-tag :bordered="false" size="small" type="info">
          独立小数据回测 · 每步严格回显 · 验证回测引擎运算
        </n-tag>
      </template>

      <n-space vertical :size="12">
        <!-- 输入区 -->
        <n-space :wrap="false" align="center" :size="12">
          <n-radio-group v-model:value="codeType" size="small">
            <n-radio-button value="dsl">DSL</n-radio-button>
            <n-radio-button value="python">Python</n-radio-button>
          </n-radio-group>

          <n-select
            v-model:value="dataset"
            :options="datasetOpts"
            size="small"
            style="width: 320px"
            :disabled="useCustomData"
          />
          <n-tooltip>
            <template #trigger>
              <n-switch v-model:value="useCustomData" size="small" />
            </template>
            切换: 内置数据集 / 自定义 CSV
          </n-tooltip>

          <n-input-number v-model:value="initialCapital" size="small" :min="0" :step="1000" style="width: 110px" placeholder="本金">
            <template #suffix>U</template>
          </n-input-number>
          <n-input-number v-model:value="positionSize" size="small" :min="0" :max="1" :step="0.1" style="width: 80px" placeholder="仓位">
          </n-input-number>

          <n-button type="primary" size="small" :loading="loading" @click="run">
            ▶ 运行验证
          </n-button>
        </n-space>

        <!-- 自定义 CSV 输入 -->
        <n-collapse-transition>
          <div v-if="useCustomData">
            <n-input
              v-model:value="customCsv"
              type="textarea"
              placeholder="粘贴 CSV, 每行一根 bar: date,open,high,low,close,volume"
              :autosize="{ minRows: 4, maxRows: 10 }"
              size="small"
            />
            <n-text depth="3" style="font-size: 11px">
              例: 2024-01-01,100,102,98,101,1000
            </n-text>
          </div>
        </n-collapse-transition>

        <!-- 数据集说明 -->
        <n-alert v-if="selectedDataset && !useCustomData" type="default" :show-icon="false" size="small">
          <template #header>{{ selectedDataset.id }} ({{ selectedDataset.rows }} bars)</template>
          <div style="font-size: 12px">
            <n-text depth="3">{{ selectedDataset.description }}</n-text>
            <br>
            起 {{ num(selectedDataset.first_close) }} → 终 {{ num(selectedDataset.last_close) }},
            区间 buy&hold = <strong :style="{color: selectedDataset.buy_hold_return >= 0 ? '#02c076' : '#f6465d'}">{{ pct(selectedDataset.buy_hold_return) }}</strong>,
            最高 {{ num(selectedDataset.max_high) }}, 最低 {{ num(selectedDataset.min_low) }}
          </div>
        </n-alert>

        <!-- 策略代码 -->
        <n-input
          v-model:value="code"
          type="textarea"
          :placeholder="codeType === 'dsl' ? 'signal = ...\n止损 = 0\n止盈 = 0\n仓位 = 1.0' : 'def init()...\ndef on_bar(state)...'"
          :autosize="{ minRows: 6, maxRows: 14 }"
          size="small"
          style="font-family: 'Cascadia Code', 'Consolas', monospace"
        />

        <!-- 错误提示 -->
        <n-alert v-if="error" type="error" :show-icon="true" size="small">
          {{ error }}
        </n-alert>

        <!-- 结果 -->
        <template v-if="result">
          <n-divider style="margin: 8px 0">📊 验证结果</n-divider>

          <!-- 摘要卡片 -->
          <n-space :size="12" :wrap="true">
            <n-statistic label="总收益" :value="pct(result.summary.total_return)" />
            <n-statistic label="Buy&Hold 收益" :value="pct(result.summary.buy_hold_return)" />
            <n-statistic label="夏普" :value="num(result.summary.sharpe, 2)" />
            <n-statistic label="最大回撤" :value="pct(result.summary.max_drawdown)" />
            <n-statistic label="胜率" :value="pct(result.summary.win_rate)" />
            <n-statistic label="交易次数" :value="result.summary.trades" />
            <n-statistic label="手续费" :value="num(result.summary.fees_paid, 2)" />
            <n-statistic label="最终净值" :value="num(result.summary.final_equity, 2)" />
          </n-space>

          <!-- 净值曲线 (简单 sparkline) -->
          <div v-if="result.trace.length" class="equity-chart">
            <svg :viewBox="`0 0 ${result.trace.length * 60} 100`" preserveAspectRatio="none" style="width: 100%; height: 80px">
              <polyline
                :points="result.trace.map((t, i) => `${i*60 + 30},${100 - t.equity / result.summary.final_equity * 80 - 5}`).join(' ')"
                fill="none" stroke="#f0b90b" stroke-width="2"
              />
              <polyline
                :points="result.trace.map((t, i) => `${i*60 + 30},${100 - (initialCapital * (1 + result.data_meta.buy_hold_return * (i / (result.trace.length - 1)))) / result.summary.final_equity * 80 - 5}`).join(' ')"
                fill="none" stroke="#474d57" stroke-width="1" stroke-dasharray="3 3"
              />
            </svg>
            <div style="display: flex; justify-content: space-between; font-size: 10px; color: #b7bdc6; margin-top: 4px">
              <span>黄: 策略净值</span>
              <span>灰: Buy&Hold 基准</span>
            </div>
          </div>

          <!-- 逐步日志 -->
          <n-collapse :default-expanded-names="['log', 'trace']">
            <n-collapse-item title="📋 逐步日志 (每根 bar 严格回显)" name="log">
              <div class="log-box">
                <div v-for="(line, i) in result.log" :key="i" class="log-line">{{ line }}</div>
              </div>
            </n-collapse-item>

            <n-collapse-item title="📊 详细 Trace 表 (bar → ohlcv → signal → action → equity)" name="trace">
              <n-data-table
                :columns="traceColumns"
                :data="result.trace"
                size="small"
                :bordered="false"
                :max-height="400"
                :pagination="false"
              />
            </n-collapse-item>

            <n-collapse-item
              v-if="result.trades && result.trades.length"
              :title="`💰 成交明细 (${result.trades.length} 笔)`"
              name="trades"
            >
              <n-data-table
                :columns="[
                  { title: 'Date', key: 'date', width: 100 },
                  { title: 'Side', key: 'side', width: 60 },
                  { title: 'Qty', key: 'qty', width: 100 },
                  { title: 'Price', key: 'price', width: 100 },
                  { title: 'USDT/Proceeds', key: 'usdt', width: 120,
                    render: (row) => row.usdt ? num(row.usdt, 2) : num(row.proceeds, 2)
                  },
                  { title: 'PnL', key: 'pnl', width: 100,
                    render: (row) => row.pnl != null ? h('span', { style: { color: row.pnl >= 0 ? '#02c076' : '#f6465d' } }, num(row.pnl, 2)) : '-'
                  },
                ]"
                :data="result.trades"
                size="small"
                :max-height="400"
                :pagination="false"
              />
            </n-collapse-item>
          </n-collapse>
        </template>
      </n-space>
    </n-card>
  </div>
</template>

<style scoped>
.verify-root {
  padding: 12px;
  height: 100%;
  overflow: auto;
}
.verify-card {
  max-width: 1400px;
  margin: 0 auto;
}
.equity-chart {
  background: #1e2329;
  border: 1px solid #2b3139;
  border-radius: 4px;
  padding: 8px;
  margin-top: 8px;
}
.log-box {
  background: #181a20;
  border: 1px solid #2b3139;
  border-radius: 4px;
  padding: 12px;
  font-family: 'Cascadia Code', 'Consolas', monospace;
  font-size: 12px;
  line-height: 1.6;
  max-height: 400px;
  overflow: auto;
}
.log-line {
  white-space: pre;
  color: #b7bdc6;
}
.log-line:hover {
  background: #1e2329;
}
</style>