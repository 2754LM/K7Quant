// 时间框架工具: 把 K 线周期转成分钟数 / 人类可读时长
// 全部从 Binance 白名单派生 (后端 /api/data/timeframes 是 source of truth)
// 这里只做客户端 fallback (API 失败时用)

const UNIT_TO_MIN = {
  s: 1 / 60,
  m: 1,
  h: 60,
  d: 60 * 24,
  w: 60 * 24 * 7,
  M: 60 * 24 * 30,  // 月近似 30 天
}

export function tfMinutes(tf) {
  if (!tf) return 1
  const n = parseInt(tf.slice(0, -1), 10)
  const unit = tf.slice(-1)
  if (isNaN(n) || !UNIT_TO_MIN[unit]) return 1
  return n * UNIT_TO_MIN[unit]
}

const UNIT_LABEL = { s: '秒', m: '分钟', h: '小时', d: '天', w: '周', M: '月' }
export function tfLabel(tf) {
  if (!tf) return ''
  const n = parseInt(tf.slice(0, -1), 10)
  const unit = tf.slice(-1)
  if (isNaN(n) || !UNIT_LABEL[unit]) return tf
  return `${n} ${UNIT_LABEL[unit]}`
}

// Binance 全部 16 个时间框架 (与后端 BINANCE_TIMEFRAMES 一致)
// 客户端 fallback: API 失败时用这个
export const BINANCE_TIMEFRAMES = [
  '1s', '1m', '3m', '5m', '15m', '30m',
  '1h', '2h', '4h', '6h', '8h', '12h',
  '1d', '3d', '1w', '1M',
]

// 按单位分组, 给 UI 用 (分组顺序: 秒, 分, 时, 日, 周, 月)
export const BINANCE_TIMEFRAMES_GROUPED = [
  { label: '秒',  unit: 's', tfs: ['1s'] },
  { label: '分钟', unit: 'm', tfs: ['1m', '3m', '5m', '15m', '30m'] },
  { label: '小时', unit: 'h', tfs: ['1h', '2h', '4h', '6h', '8h', '12h'] },
  { label: '天',   unit: 'd', tfs: ['1d', '3d'] },
  { label: '周',   unit: 'w', tfs: ['1w'] },
  { label: '月',   unit: 'M', tfs: ['1M'] },
]
