import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 300000
})

export const getConfig = () => api.get('/config')
export const runBacktest = (params) => api.post('/backtest', params)
export const scanPool = (params) => api.post('/scan', params)
export const getKline = (symbol, timeframe, start, end) =>
  api.get(`/kline/${symbol}`, { params: { timeframe, start, end } })
export const filterStocks = (params) => api.post('/filter', params)
export const listData = () => api.get('/data')

export default api