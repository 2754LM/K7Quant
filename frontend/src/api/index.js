import axios from 'axios'
import { log as sysLog, info as logInfo, error as logError } from '../utils/systemLog'

const api = axios.create({
  baseURL: '/api',
  timeout: 300000,
})

api.interceptors.request.use((cfg) => {
  cfg.metadata = { startTime: Date.now() }
  return cfg
})

api.interceptors.response.use(
  (r) => {
    const ms = Date.now() - (r.config.metadata?.startTime || 0)
    logInfo('api', `${r.config.method?.toUpperCase()} ${shortenUrl(r.config.url)} ${r.status} (${ms}ms)`)
    return r
  },
  (err) => {
    const ms = Date.now() - (err.config?.metadata?.startTime || 0)
    const status = err.response?.status || 'ERR'
    const msg = err?.response?.data?.detail || err.message
    logError('api', `${err.config?.method?.toUpperCase()} ${shortenUrl(err.config?.url || '')} ${status} (${ms}ms): ${typeof msg === 'string' ? msg : JSON.stringify(msg)}`)
    return Promise.reject(new Error(typeof msg === 'string' ? msg : JSON.stringify(msg)))
  }
)

function shortenUrl(url) {
  if (!url) return ''
  if (url.length > 60) return url.slice(0, 30) + '...' + url.slice(-25)
  return url
}

export const getConfig = () => api.get('/config')
export const getStrategies = () => api.get('/strategy/list')
export const getStrategy = (id) => api.get(`/strategy/${id}`)
export const createStrategy = (data) => api.post('/strategy/create', data)
export const updateStrategy = (id, data) => api.post('/strategy/update', { id, ...data })
export const deleteStrategy = (id) => api.delete(`/strategy/${id}`)
export const getStrategyTemplates = () => api.get('/strategy/templates')
export const getDslDocs = () => api.get('/strategy/dsl-docs')
export const validateStrategyCode = (code) => api.post('/strategy/validate', { code })

export const runBacktest = (data) => api.post('/backtest/single', data)
export const scanPool = (data) => api.post('/backtest/scan', data)
export const filterSymbols = (data) => api.post('/backtest/filter', data)
export const getKline = (symbol, timeframe, start, end) =>
  api.get(`/backtest/kline/${symbol}`, { params: { timeframe, start, end } })
export const backtestCode = (data) => api.post('/backtest/code', data)

export const listFactors = (category) => api.get('/factor/list', { params: { category } })
export const getFactor = (id) => api.get(`/factor/${id}`)
export const computeFactor = (data) => api.post('/factor/compute', data)
export const computeFactors = (data) => api.post('/factor/compute-many', data)
export const correlateFactors = (data) => api.post('/factor/correlate', data)
export const rankFactors = (data) => api.post('/factor/rank', data)
export const createCustomFactor = (data) => api.post('/factor/create-custom', data)
export const deleteCustomFactor = (id) => api.delete(`/factor/custom/${id}`)
export const getFactorDslDocs = () => api.get('/factor/dsl-docs')

// 自定义规则/查询 (落库 custom_rules)
export const listRules = () => api.get('/rule/list')
export const createRule = (data) => api.post('/rule/create', data)
export const deleteRule = (id) => api.delete(`/rule/${id}`)

export const listSymbols = (activeOnly = false) =>
  api.get('/symbol/list', { params: { active_only: activeOnly } })
export const getSymbol = (s) => api.get(`/symbol/${s}`)
export const upsertSymbol = (data) => api.post('/symbol/upsert', data)
export const setActiveSymbols = (symbols) => api.post('/symbol/active', { symbols })
export const getActiveSymbols = () => api.get('/symbol/active/current')

export const listData = () => api.get('/data/cache')
export const clearDataCache = (timeframe, symbol) =>
  api.delete('/data/cache', { params: { timeframe, symbol } })
export const listExchangeSymbols = () => api.get('/data/exchange-symbols')
export const testConnection = () => api.get('/data/test-connection')
export const getExchangeInfo = (symbol) => api.get(`/data/exchange-info/${symbol}`)

export const getSystemConfig = () => api.get('/config')
export const updateBacktestConfig = (data) => api.put('/config/backtest', data)
export const updateDataSourceConfig = (data) => api.put('/config/data-source', data)
export const updateUiConfig = (data) => api.put('/config/ui', data)
export const updateTradingConfig = (data) => api.put('/config/trading', data)

export const getTradeStatus = () => api.get('/trade/status')
export const listTrades = (mode, limit) => api.get('/trade/trades', { params: { mode, limit } })
export const recordTrade = (data) => api.post('/trade/record', data)
// 模拟盘 (Binance Demo Mode)
export const getTradeConnectivity = () => api.get('/trade/connectivity')
export const getTradeAccount = () => api.get('/trade/account')
export const getOpenOrders = (symbol) => api.get('/trade/open-orders', { params: { symbol } })
export const placeOrder = (data) => api.post('/trade/order', data)
export const cancelOrder = (symbol, orderId) =>
  api.delete('/trade/order', { params: { symbol, order_id: orderId } })
export const getMyTrades = (symbol, limit = 50) =>
  api.get('/trade/my-trades', { params: { symbol, limit } })

export default api