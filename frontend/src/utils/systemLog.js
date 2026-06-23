// 系统日志: 记录 API 调用/错误 + 后端 tail 拉取, 供 UI 显示
import { reactive } from 'vue'
import { tailLogs } from '../api'

const MAX_LOGS = 500
const logs = reactive([])

let listeners = []

function notify() {
  for (const fn of listeners) {
    try { fn(logs) } catch (e) {}
  }
}

export function log(level, source, message) {
  const entry = {
    id: Date.now() + Math.random(),
    ts: new Date(),
    level,    // 'info' | 'success' | 'warn' | 'error'
    source,   // 'api' | 'backtest' | 'factor' | 'system' ...
    message,
  }
  logs.unshift(entry)
  if (logs.length > MAX_LOGS) logs.length = MAX_LOGS
  notify()
  return entry
}

export function clear() {
  logs.splice(0, logs.length)
  notify()
}

export function getLogs() {
  return logs
}

export function subscribe(fn) {
  listeners.push(fn)
  return () => { listeners = listeners.filter(x => x !== fn) }
}

export function info(source, msg) { log('info', source, msg) }
export function success(source, msg) { log('success', source, msg) }
export function warn(source, msg) { log('warn', source, msg) }
export function error(source, msg) { log('error', source, msg) }

// ============ 后端日志拉取 (轮询) ============
// 解析 backend 格式: "[2026-06-23 22:08:14] [INFO] [k7quant] message"
const _BACKEND_LINE = /^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s+\[(\w+)\]\s+\[([^\]]+)\]\s+(.*)$/
let _backendPollTimer = null
let _backendTotalLines = 0
let _backendMtime = 0
let _seenBackendIds = new Set()

export function _startBackendLogPolling(intervalMs = 3000) {
  if (_backendPollTimer) return  // 单例
  _pullBackendLogs()
  _backendPollTimer = setInterval(_pullBackendLogs, intervalMs)
}

export function _stopBackendLogPolling() {
  if (_backendPollTimer) { clearInterval(_backendPollTimer); _backendPollTimer = null }
}

async function _pullBackendLogs() {
  try {
    // 每次拉末尾 50 行, 用 total 去重
    const r = await tailLogs(50, 0)
    const data = r?.data
    if (!data) return
    const lines = data.lines || []
    const total = data.total || 0
    const mtime = data.mtime || 0
    // 文件被截断或轮转时重置 seen set
    if (mtime !== _backendMtime || total < _backendTotalLines) {
      _seenBackendIds = new Set()
      _backendMtime = mtime
    }
    _backendTotalLines = total
    for (const ln of lines) {
      // 用行内容做 id (时间戳 + 内容)
      const id = ln
      if (_seenBackendIds.has(id)) continue
      _seenBackendIds.add(id)
      _pushBackendLine(ln)
    }
    // 防 seen set 无限增长
    if (_seenBackendIds.size > 1000) {
      _seenBackendIds = new Set([..._seenBackendIds].slice(-500))
    }
  } catch (e) {
    // 后端不可用时静默 (前端也跑不了)
  }
}

function _pushBackendLine(rawLine) {
  const m = _BACKEND_LINE.exec(rawLine)
  if (!m) {
    log('info', 'backend', rawLine)
    return
  }
  const [, tsStr, level, source, message] = m
  const lvl = ({ INFO: 'info', WARNING: 'warn', ERROR: 'error', DEBUG: 'info' }[level?.toUpperCase()]) || 'info'
  log(lvl, source || 'backend', `[${tsStr.slice(11, 19)}] ${message}`)
}
