import { IndicatorSeries, registerIndicator } from 'klinecharts/dist/index.esm.js'

import { parseTradeTimestamp } from './trade-overlays.js'

export const ACCOUNT_EQUITY_INDICATOR = 'K7_ACCOUNT_EQUITY'
export const ACCOUNT_EQUITY_PANE_ID = 'k7-account-equity-pane'

const EQUITY_COLOR = '#f0b90b'
const BUY_COLOR = '#02c076'
const SELL_COLOR = '#f6465d'

let indicatorRegistered = false
let indicatorHistory = []
let indicatorMarkers = []
let indicatorRevision = 0

function num(value) {
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

function validKLineDataList(dataList) {
  if (!Array.isArray(dataList)) return []
  return dataList
    .map((item, index) => ({ timestamp: Number(item?.timestamp), dataIndex: index }))
    .filter((item) => Number.isFinite(item.timestamp) && item.timestamp > 0)
}

function estimateStep(dataList) {
  const steps = []
  for (let i = 1; i < dataList.length; i += 1) {
    const diff = dataList[i].timestamp - dataList[i - 1].timestamp
    if (diff > 0) steps.push(diff)
  }
  if (!steps.length) return 0
  steps.sort((a, b) => a - b)
  return steps[Math.floor((steps.length - 1) / 2)]
}

function findContainingKLine(dataList, timestamp) {
  if (!dataList.length || !Number.isFinite(timestamp) || timestamp <= 0) return null

  const first = dataList[0]
  const last = dataList[dataList.length - 1]
  if (timestamp < first.timestamp) return null

  const step = estimateStep(dataList)
  if (step > 0 && timestamp >= last.timestamp + step) return null
  if (step === 0 && dataList.length === 1 && timestamp !== first.timestamp) return null

  let left = 0
  let right = dataList.length - 1
  let matched = null
  let matchedIndex = -1
  while (left <= right) {
    const mid = Math.floor((left + right) / 2)
    if (dataList[mid].timestamp <= timestamp) {
      matched = dataList[mid]
      matchedIndex = mid
      left = mid + 1
    } else {
      right = mid - 1
    }
  }
  if (!matched) return null

  const next = dataList[matchedIndex + 1]
  if (
    step > 0 && next
    && next.timestamp - matched.timestamp > step * 1.5
    && timestamp >= matched.timestamp + step
  ) {
    return null
  }
  return matched
}

function normalizeHistory(history) {
  if (!Array.isArray(history)) return []
  return history
    .map((row) => ({
      time: num(row?.time),
      totalValue: num(row?.totalValue),
    }))
    .filter((row) => row.time > 0 && row.totalValue > 0)
    .sort((a, b) => a.time - b.time)
}

export function buildAccountEquitySeries(dataList = [], history = []) {
  const kline = validKLineDataList(dataList)
  const points = normalizeHistory(history)
  const series = Array.from({ length: Array.isArray(dataList) ? dataList.length : 0 }, () => ({}))
  if (!kline.length || !points.length) return series

  for (const point of points) {
    const candle = findContainingKLine(kline, point.time)
    if (candle) series[candle.dataIndex] = { equity: point.totalValue }
  }

  let lastValue = null
  return series.map((item) => {
    const value = num(item.equity)
    if (value > 0) lastValue = value
    return lastValue > 0 ? { equity: lastValue } : {}
  })
}

function markerSide(marker) {
  return String(marker?.side || '').toLowerCase() === 'sell' ? 'sell' : 'buy'
}

export function buildAccountEquityMarkers(dataList = [], equitySeries = [], markers = []) {
  const kline = validKLineDataList(dataList)
  if (!kline.length || !Array.isArray(markers) || !markers.length) return []

  return markers
    .map((marker) => {
      const candle = findContainingKLine(kline, parseTradeTimestamp(marker?.created_at))
      if (!candle) return null
      const equity = num(equitySeries[candle.dataIndex]?.equity)
      if (equity <= 0) return null
      return {
        id: marker?.id,
        side: markerSide(marker),
        dataIndex: candle.dataIndex,
        timestamp: candle.timestamp,
        equity,
        price: num(marker?.price),
      }
    })
    .filter(Boolean)
}

function getVisibleBounds(visibleRange, total) {
  const from = Math.max(0, Math.floor(num(visibleRange?.from)))
  const to = Math.min(total - 1, Math.ceil(num(visibleRange?.to)))
  return { from, to: to > 0 ? to : total - 1 }
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value))
}

function drawMarker(ctx, x, y, side, lane, bounding) {
  const color = side === 'sell' ? SELL_COLOR : BUY_COLOR
  const label = side === 'sell' ? 'S' : 'B'
  const direction = side === 'sell' ? -1 : 1
  const markerY = clamp(y + direction * (16 + lane * 16), 14, Math.max(14, bounding.height - 14))

  ctx.save()
  ctx.strokeStyle = color
  ctx.fillStyle = color
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(x, y)
  ctx.lineTo(x, markerY)
  ctx.stroke()

  ctx.beginPath()
  ctx.arc(x, markerY, 7, 0, Math.PI * 2)
  ctx.fill()

  ctx.fillStyle = side === 'sell' ? '#1a0608' : '#06120b'
  ctx.font = '700 10px Consolas, monospace'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(label, x, markerY + 0.5)
  ctx.restore()
}

function drawAccountEquityIndicator({
  ctx,
  kLineDataList,
  indicator,
  visibleRange,
  bounding,
  xAxis,
  yAxis,
}) {
  const result = Array.isArray(indicator?.result) ? indicator.result : []
  if (!result.length) return true

  const { from, to } = getVisibleBounds(visibleRange, result.length)
  ctx.save()
  ctx.strokeStyle = EQUITY_COLOR
  ctx.lineWidth = 1.6
  ctx.beginPath()
  let started = false

  for (let i = from; i <= to; i += 1) {
    const value = num(result[i]?.equity)
    if (value <= 0) {
      started = false
      continue
    }
    const x = xAxis.convertToPixel(i)
    const y = yAxis.convertToPixel(value)
    if (!started) {
      ctx.moveTo(x, y)
      started = true
    } else {
      ctx.lineTo(x, y)
    }
  }
  ctx.stroke()

  const marks = buildAccountEquityMarkers(kLineDataList, result, indicatorMarkers)
  const lanes = new Map()
  for (const mark of marks) {
    if (mark.dataIndex < from || mark.dataIndex > to) continue
    const lane = lanes.get(mark.dataIndex) || 0
    lanes.set(mark.dataIndex, lane + 1)
    drawMarker(
      ctx,
      xAxis.convertToPixel(mark.dataIndex),
      yAxis.convertToPixel(mark.equity),
      mark.side,
      lane,
      bounding
    )
  }

  ctx.restore()
  return true
}

export function registerAccountEquityIndicator() {
  if (indicatorRegistered) return
  registerIndicator({
    name: ACCOUNT_EQUITY_INDICATOR,
    shortName: '账户资产',
    series: IndicatorSeries.Normal,
    precision: 2,
    shouldFormatBigNumber: true,
    figures: [{
      key: 'equity',
      title: '账户资产: ',
      type: 'line',
      styles: () => ({ color: EQUITY_COLOR, size: 1.6, smooth: false }),
    }],
    calc: (dataList) => buildAccountEquitySeries(dataList, indicatorHistory),
    draw: drawAccountEquityIndicator,
  })
  indicatorRegistered = true
}

function getChartApi(chartPro) {
  return chartPro?._chartApi || chartPro?.chartApi || null
}

export function syncAccountEquityIndicator(chartPro, history = [], markers = []) {
  const chartApi = getChartApi(chartPro)
  if (!chartApi?.createIndicator || !chartApi?.overrideIndicator) {
    return { ok: false, reason: 'chart-api-unavailable' }
  }

  registerAccountEquityIndicator()
  indicatorHistory = normalizeHistory(history)
  indicatorMarkers = Array.isArray(markers) ? markers : []
  indicatorRevision += 1

  const existing = typeof chartApi.getIndicatorByPaneId === 'function'
    ? chartApi.getIndicatorByPaneId(ACCOUNT_EQUITY_PANE_ID, ACCOUNT_EQUITY_INDICATOR)
    : null

  if (!existing) {
    chartApi.createIndicator(ACCOUNT_EQUITY_INDICATOR, false, {
      id: ACCOUNT_EQUITY_PANE_ID,
      height: 132,
      minHeight: 92,
    })
  }

  chartApi.overrideIndicator({
    name: ACCOUNT_EQUITY_INDICATOR,
    extendData: { revision: indicatorRevision },
  }, ACCOUNT_EQUITY_PANE_ID)

  return { ok: true, count: indicatorHistory.length, markerCount: indicatorMarkers.length }
}
