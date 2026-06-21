// KLineChart Pro 数据源适配器
// 历史 K 线走后端 getKline (缓存优先), 实时走 Binance 公开 WS (binance-ws.js)
import { getKline, listSymbols } from '../api'
import { subscribeKline } from './binance-ws'

const pad = (n) => String(n).padStart(2, '0')

// ms(UTC) -> YYYYMMDD (后端按 UTC 解析, 与实时 epoch 对齐)
function toYmd(ms) {
  const d = new Date(ms)
  return `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}`
}

// 后端 date 字符串 (pandas UTC naive, 无时区) -> epoch ms
// 'YYYY-MM-DD' 或 'YYYY-MM-DD HH:MM:SS', 统一按 UTC 处理, 和 WS 的 k.t 对齐
function recTime(s) {
  if (!s) return 0
  if (s.length <= 10) return new Date(`${s}T00:00:00Z`).getTime()
  return new Date(`${s.replace(' ', 'T')}Z`).getTime()
}

// Pro Period -> Binance interval ('1m'/'1h'/'4h'/'1d'/'1w')
const SPAN = { minute: 'm', hour: 'h', day: 'd', week: 'w', month: 'M' }
function periodToInterval(p) {
  return `${p.multiplier}${SPAN[p.timespan] || 'm'}`
}

export class BinanceDatafeed {
  constructor() {
    this._unsub = null
    this._symbols = null
  }

  async _ensureSymbols() {
    if (this._symbols) return this._symbols
    try {
      const r = await listSymbols(false)
      const list = r.data?.symbols || r.data || []
      this._symbols = list.map((s) => ({
        ticker: s.symbol,
        name: s.name_zh || s.symbol,
        shortName: (s.symbol || '').replace('USDT', ''),
        exchange: 'Binance',
        market: 'spot',
        pricePrecision: 2,
        volumePrecision: 4,
        priceCurrency: 'USDT',
        type: 'ADRC',
      }))
    } catch {
      this._symbols = []
    }
    return this._symbols
  }

  async searchSymbols(search = '') {
    const all = await this._ensureSymbols()
    const q = (search || '').toUpperCase()
    if (!q) return all
    return all.filter((s) => s.ticker.includes(q) || (s.shortName || '').includes(q))
  }

  async getHistoryKLineData(symbol, period, from, to) {
    const tf = periodToInterval(period)
    try {
      // 后端按"天"过滤 (date <= end 当天 00:00)。end 不 +1 天的话会丢掉 to 当天的
      // 全部日内分钟, 只剩午夜一根 -> 分钟级图表会退化成"每日午夜单点"。
      const start = toYmd(from)
      const end = toYmd(to + 86400000)
      const r = await getKline(symbol.ticker, tf, start, end)
      const arr = r.data?.kline || []
      return arr.map((k) => ({
        timestamp: recTime(k.date),
        open: +k.open,
        high: +k.high,
        low: +k.low,
        close: +k.close,
        volume: +(k.volume || 0),
      }))
    } catch {
      return []
    }
  }

  subscribe(symbol, period, callback) {
    const tf = periodToInterval(period)
    if (this._unsub) { this._unsub(); this._unsub = null }
    this._unsub = subscribeKline(symbol.ticker, tf, (bar) => {
      callback({
        timestamp: bar.time,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
        volume: bar.volume,
      })
    })
  }

  unsubscribe() {
    if (this._unsub) { this._unsub(); this._unsub = null }
  }
}
