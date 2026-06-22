import { registerOverlay } from 'klinecharts/dist/index.esm.js'

export const TRADE_MARKER_OVERLAY = 'k7TradeMarker'
export const TRADE_MARKER_GROUP = 'k7-trade-markers'

let registered = false

function num(value) {
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

export function parseTradeTimestamp(value) {
  if (!value) return 0
  if (typeof value === 'number') return value
  const raw = String(value)
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(raw)
  const normalized = hasZone ? raw : `${raw}Z`
  const parsed = Date.parse(normalized)
  return Number.isFinite(parsed) ? parsed : 0
}

function markerColor(side) {
  return side === 'sell' ? '#f6465d' : '#02c076'
}

function markerLabel(side) {
  return side === 'sell' ? 'S' : 'B'
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

export function mapMarkerToKLinePoint(marker, dataList) {
  const timestamp = parseTradeTimestamp(marker?.created_at)
  const price = num(marker?.price)
  const kline = findContainingKLine(validKLineDataList(dataList), timestamp)
  if (!kline || price <= 0) return null
  return {
    timestamp: kline.timestamp,
    dataIndex: kline.dataIndex,
    value: price,
  }
}

function createMarkerFigures({ overlay, coordinates, bounding }) {
  const point = coordinates[0]
  if (!point) return []

  const side = overlay.extendData?.side === 'sell' ? 'sell' : 'buy'
  const color = markerColor(side)
  const markerY = side === 'sell'
    ? Math.max(16, point.y - 22)
    : Math.min((bounding?.height || point.y + 22) - 16, point.y + 22)

  return [
    {
      type: 'line',
      attrs: { coordinates: [{ x: point.x, y: point.y }, { x: point.x, y: markerY }] },
      styles: { color, size: 1 },
      ignoreEvent: true,
    },
    {
      type: 'circle',
      attrs: { x: point.x, y: markerY, r: 9 },
      styles: { color, borderColor: '#0b1018', borderSize: 2 },
      ignoreEvent: true,
    },
    {
      type: 'text',
      attrs: { x: point.x, y: markerY + 1, text: markerLabel(side), align: 'center', baseline: 'middle' },
      styles: { color: '#07120c', backgroundColor: 'transparent', size: 11, weight: '700', family: 'Consolas' },
      ignoreEvent: true,
    },
  ]
}

export function registerTradeMarkerOverlay() {
  if (registered) return
  registerOverlay({
    name: TRADE_MARKER_OVERLAY,
    totalStep: 2,
    needDefaultPointFigure: false,
    needDefaultXAxisFigure: false,
    needDefaultYAxisFigure: false,
    createPointFigures: createMarkerFigures,
  })
  registered = true
}

export function buildTradeOverlay(marker, dataList = null) {
  const side = String(marker?.side || '').toLowerCase() === 'sell' ? 'sell' : 'buy'
  const price = num(marker?.price)
  const hasDataList = Array.isArray(dataList)
  const mappedPoint = hasDataList ? mapMarkerToKLinePoint(marker, dataList) : null
  if (hasDataList && !mappedPoint) return null
  const point = mappedPoint || { timestamp: parseTradeTimestamp(marker?.created_at), value: price }
  return {
    name: TRADE_MARKER_OVERLAY,
    groupId: TRADE_MARKER_GROUP,
    lock: true,
    visible: true,
    zLevel: 10,
    needDefaultPointFigure: false,
    needDefaultXAxisFigure: false,
    needDefaultYAxisFigure: false,
    points: [point],
    styles: null,
    extendData: {
      id: marker?.id,
      side,
      price,
      amount: num(marker?.amount),
      notional: num(marker?.notional),
      realizedPnl: num(marker?.realizedPnl),
    },
  }
}

function getChartApi(chartPro) {
  return chartPro?._chartApi || chartPro?.chartApi || null
}

export function syncTradeOverlays(chartPro, markers = []) {
  const chartApi = getChartApi(chartPro)
  if (!chartApi?.createOverlay || !chartApi?.removeOverlay) {
    return { ok: false, reason: 'chart-api-unavailable' }
  }

  registerTradeMarkerOverlay()
  chartApi.removeOverlay({ groupId: TRADE_MARKER_GROUP })

  const dataList = typeof chartApi.getDataList === 'function' ? chartApi.getDataList() : null
  if (markers.length && (!Array.isArray(dataList) || dataList.length === 0)) {
    return { ok: false, reason: 'chart-data-unavailable' }
  }

  const overlays = markers
    .map((marker) => buildTradeOverlay(marker, dataList))
    .filter((overlay) => overlay?.points[0]?.timestamp > 0 && overlay.points[0].value > 0)

  if (!overlays.length) return { ok: true, count: 0 }

  chartApi.createOverlay(overlays)
  return { ok: true, count: overlays.length }
}
