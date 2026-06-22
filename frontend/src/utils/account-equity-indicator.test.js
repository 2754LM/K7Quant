import assert from 'node:assert/strict'
import test from 'node:test'

import {
  ACCOUNT_EQUITY_INDICATOR,
  buildAccountEquityMarkers,
  buildAccountEquitySeries,
  syncAccountEquityIndicator,
} from './account-equity-indicator.js'

const hour = 60 * 60 * 1000
const t0 = Date.parse('2026-06-22T00:00:00Z')

function kline(count, gapAfter = null) {
  return Array.from({ length: count }, (_, index) => {
    const gap = gapAfter != null && index > gapAfter ? 5 * hour : 0
    return { timestamp: t0 + index * hour + gap }
  })
}

test('buildAccountEquitySeries maps account history into containing candles and carries forward', () => {
  const dataList = kline(4)
  const series = buildAccountEquitySeries(dataList, [
    { time: t0 + 30 * 60 * 1000, totalValue: 10000 },
    { time: t0 + 2 * hour + 15 * 60 * 1000, totalValue: 10035.6 },
  ])

  assert.deepEqual(series, [
    { equity: 10000 },
    { equity: 10000 },
    { equity: 10035.6 },
    { equity: 10035.6 },
  ])
})

test('buildAccountEquitySeries skips history points inside missing kline gaps', () => {
  const dataList = kline(4, 1)
  const series = buildAccountEquitySeries(dataList, [
    { time: t0 + 3 * hour, totalValue: 10010 },
    { time: t0 + 7 * hour + 10, totalValue: 10020 },
  ])

  assert.deepEqual(series, [
    {},
    {},
    { equity: 10020 },
    { equity: 10020 },
  ])
})

test('buildAccountEquityMarkers snaps buy and sell marks to the matching equity candle', () => {
  const dataList = kline(3)
  const series = buildAccountEquitySeries(dataList, [
    { time: t0 + 10 * 60 * 1000, totalValue: 10000 },
    { time: t0 + hour + 20 * 60 * 1000, totalValue: 9988 },
  ])
  const markers = buildAccountEquityMarkers(dataList, series, [
    { id: 1, side: 'buy', created_at: '2026-06-22T00:35:00', price: 64000 },
    { id: 2, side: 'sell', created_at: '2026-06-22T01:05:00', price: 64120 },
  ])

  assert.deepEqual(markers, [
    { id: 1, side: 'buy', dataIndex: 0, timestamp: t0, equity: 10000, price: 64000 },
    { id: 2, side: 'sell', dataIndex: 1, timestamp: t0 + hour, equity: 9988, price: 64120 },
  ])
})

test('syncAccountEquityIndicator creates or refreshes the klinecharts account equity pane', () => {
  const calls = []
  const chart = {
    _chartApi: {
      getDataList: () => kline(2),
      getIndicatorByPaneId: () => null,
      createIndicator: (...args) => {
        calls.push(['create', args])
        return 'k7-account-equity-pane'
      },
      overrideIndicator: (...args) => calls.push(['override', args]),
    },
  }

  const result = syncAccountEquityIndicator(chart, [
    { time: t0 + 10, totalValue: 10000 },
  ], [])

  assert.equal(result.ok, true)
  assert.equal(result.count, 1)
  assert.equal(calls[0][0], 'create')
  assert.equal(calls[0][1][0], ACCOUNT_EQUITY_INDICATOR)
  assert.equal(calls[1][0], 'override')
})
