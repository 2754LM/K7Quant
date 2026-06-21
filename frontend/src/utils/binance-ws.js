// Binance 实时行情 WebSocket
// 单例 per (symbol, interval), 多订阅复用同一连接, 避免开太多 socket
const streams = new Map()  // key = "{symbol}@kline_{interval}" -> { ws, subscribers: Set, lastBar: Object|null }
const FRAMES = 1440  // 1m 一根, 1440 = 24h

/**
 * 订阅 Binance kline stream
 * @param symbol  e.g. "BTCUSDT"
 * @param interval e.g. "1m" / "5m" / "1h"
 * @param onUpdate 收到每根 K 线 (open 状态变化 / close 状态) 时调用
 * @returns unsubscribe 函数
 */
export function subscribeKline(symbol, interval, onUpdate) {
  const s = symbol.toLowerCase()
  const i = interval
  const key = `${s}@kline_${i}`

  let entry = streams.get(key)
  if (!entry) {
    entry = { ws: null, subscribers: new Set(), lastBar: null, reconnectTimer: null, alive: true }
    streams.set(key, entry)
    _connect(key, entry)
  }
  entry.subscribers.add(onUpdate)

  // 立即把最近一根 K 线推给新订阅者 (避免空白期)
  if (entry.lastBar) onUpdate(entry.lastBar)

  return () => {
    if (!streams.has(key)) return
    const e = streams.get(key)
    e.subscribers.delete(onUpdate)
    if (e.subscribers.size === 0) {
      e.alive = false
      if (e.reconnectTimer) clearTimeout(e.reconnectTimer)
      try { e.ws?.close() } catch {}
      streams.delete(key)
    }
  }
}

function _connect(key, entry) {
  const url = `wss://stream.binance.com:9443/ws/${key}`
  let ws
  try {
    ws = new WebSocket(url)
  } catch (e) {
    _scheduleReconnect(key, entry)
    return
  }
  entry.ws = ws

  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data)
      // Binance kline 事件格式: { e: "kline", k: { t, o, h, l, c, v, ... x: 是否已关闭 } }
      const k = msg.k
      if (!k) return
      const bar = {
        time: k.t,
        open: parseFloat(k.o),
        high: parseFloat(k.h),
        low: parseFloat(k.l),
        close: parseFloat(k.c),
        volume: parseFloat(k.v),
        closed: !!k.x,
      }
      entry.lastBar = bar
      for (const sub of entry.subscribers) {
        try { sub(bar) } catch {}
      }
    } catch {}
  }

  ws.onerror = () => {
    // 自动重连
    if (entry.alive) _scheduleReconnect(key, entry)
  }
  ws.onclose = () => {
    if (entry.alive) _scheduleReconnect(key, entry)
  }
}

function _scheduleReconnect(key, entry) {
  if (!entry.alive) return
  if (entry.reconnectTimer) clearTimeout(entry.reconnectTimer)
  entry.reconnectTimer = setTimeout(() => {
    if (entry.alive) _connect(key, entry)
  }, 3000)
}

export function closeAllStreams() {
  for (const [key, entry] of streams.entries()) {
    entry.alive = false
    if (entry.reconnectTimer) clearTimeout(entry.reconnectTimer)
    try { entry.ws?.close() } catch {}
  }
  streams.clear()
}