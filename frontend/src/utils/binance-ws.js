// Binance 实时行情 WebSocket
// 单例 per stream, 多订阅复用同一连接, 避免开太多 socket
const streams = new Map()  // key = stream name -> { ws, subscribers: Set, lastValue: Object|null }
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
    entry = _createEntry(parseKlineMessage)
    streams.set(key, entry)
    _connect(key, entry)
  }
  entry.subscribers.add(onUpdate)

  // 立即把最近一根 K 线推给新订阅者 (避免空白期)
  if (entry.lastValue) onUpdate(entry.lastValue)

  return _unsubscribe(key, onUpdate)
}

/**
 * 订阅 Binance 24h ticker stream
 * @param symbol e.g. "BTCUSDT"
 * @param onUpdate 收到最新 ticker 时调用
 * @returns unsubscribe 函数
 */
export function subscribeTicker(symbol, onUpdate) {
  const s = symbol.toLowerCase()
  const key = `${s}@ticker`

  let entry = streams.get(key)
  if (!entry) {
    entry = _createEntry(parseTickerMessage)
    streams.set(key, entry)
    _connect(key, entry)
  }
  entry.subscribers.add(onUpdate)

  if (entry.lastValue) onUpdate(entry.lastValue)

  return _unsubscribe(key, onUpdate)
}

function _createEntry(parseMessage) {
  return {
    ws: null,
    subscribers: new Set(),
    lastValue: null,
    reconnectTimer: null,
    alive: true,
    parseMessage,
  }
}

function _unsubscribe(key, onUpdate) {
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
      const value = entry.parseMessage(msg)
      if (!value) return
      entry.lastValue = value
      for (const sub of entry.subscribers) {
        try { sub(value) } catch {}
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

function parseKlineMessage(msg) {
  // Binance kline 事件格式: { e: "kline", k: { t, o, h, l, c, v, ... x: 是否已关闭 } }
  const k = msg.k
  if (!k) return null
  return {
    time: k.t,
    open: parseFloat(k.o),
    high: parseFloat(k.h),
    low: parseFloat(k.l),
    close: parseFloat(k.c),
    volume: parseFloat(k.v),
    closed: !!k.x,
  }
}

function parseTickerMessage(msg) {
  if (!msg || !msg.s || msg.c == null) return null
  return {
    symbol: msg.s,
    eventTime: msg.E,
    price: parseFloat(msg.c),
    priceChange: parseFloat(msg.p),
    priceChangePercent: parseFloat(msg.P),
    open: parseFloat(msg.o),
    high: parseFloat(msg.h),
    low: parseFloat(msg.l),
    volume: parseFloat(msg.v),
    quoteVolume: parseFloat(msg.q),
  }
}

export function closeAllStreams() {
  for (const [key, entry] of streams.entries()) {
    entry.alive = false
    if (entry.reconnectTimer) clearTimeout(entry.reconnectTimer)
    try { entry.ws?.close() } catch {}
  }
  streams.clear()
}
