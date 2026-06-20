"""系统日志: 记录 API 调用/错误, 供 UI 显示"""
import { reactive } from 'vue'

const MAX_LOGS = 200
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
