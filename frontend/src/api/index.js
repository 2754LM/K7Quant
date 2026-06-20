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
    return Promise.reject(new Error(msg))
  }
)

// 回测
export const backtestSingle = (data) => api.post('/backtest/single', data)
export const scanPool = (data) => api.post('/backtest/scan', data)
export const filterSymbols = (data) => api.post('/backtest/filter', data)
export const getKline = (symbol, timeframe, start, end) =>
  api.get(`/backtest/kline/${symbol}`, { params: { timeframe, start, end } })

// 数据
export const listData = () => api.get('/data')
export const clearData = (timeframe, symbol) =>
  api.delete('/data', { params: { timeframe, symbol } })

// 配置
export const getConfig = () => api.get('/config')
export const setActiveSymbols = (symbols) => api.put('/config/active-symbols', { symbols })
export const setStrategyDefaults = (strategy, params) =>
  api.put('/config/strategy-defaults', { strategy, params })
export const setBacktestDefaults = (patch) => api.put('/config/backtest-defaults', patch)
export const setTimeframes = (timeframes) => api.put('/config/timeframes', { timeframes })
export const resetConfig = () => api.post('/config/reset')

export default api