import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 300000,
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    const msg = err?.response?.data?.detail || err.message
    console.error('[API]', err.config?.url, msg)
    return Promise.reject(new Error(typeof msg === 'string' ? msg : JSON.stringify(msg)))
  }
)

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

export const getSystemConfig = () => api.get('/config')
export const updateBacktestConfig = (data) => api.put('/config/backtest', data)
export const updateDataSourceConfig = (data) => api.put('/config/data-source', data)
export const updateUiConfig = (data) => api.put('/config/ui', data)
export const updateTradingConfig = (data) => api.put('/config/trading', data)

export const getTradeStatus = () => api.get('/trade/status')
export const listTrades = (mode, limit) => api.get('/trade/trades', { params: { mode, limit } })
export const recordTrade = (data) => api.post('/trade/record', data)

export default api