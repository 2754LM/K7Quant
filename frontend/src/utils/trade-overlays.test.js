import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildTradeOverlay,
  mapMarkerToKLinePoint,
  parseTradeTimestamp,
  syncTradeOverlays,
} from './trade-overlays.js'

test('parseTradeTimestamp treats naive backend ISO timestamps as UTC', () => {
  assert.equal(parseTradeTimestamp('2026-06-22T03:21:00'), Date.parse('2026-06-22T03:21:00Z'))
})

test('buildTradeOverlay maps a buy marker to a locked kline overlay', () => {
  const overlay = buildTradeOverlay({
    id: 7,
    side: 'buy',
    price: 64270,
    amount: 0.01,
    created_at: '2026-06-22T03:21:00',
  })

  assert.equal(overlay.name, 'k7TradeMarker')
  assert.equal(overlay.groupId, 'k7-trade-markers')
  assert.equal(overlay.lock, true)
  assert.equal(overlay.points[0].timestamp, Date.parse('2026-06-22T03:21:00Z'))
  assert.equal(overlay.points[0].value, 64270)
  assert.equal(overlay.extendData.side, 'buy')
})

test('mapMarkerToKLinePoint snaps an in-range trade to the containing candle dataIndex', () => {
  const dataList = [
    { timestamp: Date.parse('2026-06-22T03:00:00Z') },
    { timestamp: Date.parse('2026-06-22T04:00:00Z') },
    { timestamp: Date.parse('2026-06-22T05:00:00Z') },
  ]

  assert.deepEqual(
    mapMarkerToKLinePoint({ created_at: '2026-06-22T03:21:00', price: 64270 }, dataList),
    {
      timestamp: Date.parse('2026-06-22T03:00:00Z'),
      dataIndex: 0,
      value: 64270,
    }
  )
})

test('mapMarkerToKLinePoint uses the candle containing the trade instead of the nearest future candle', () => {
  const dataList = [
    { timestamp: Date.parse('2026-06-22T03:00:00Z') },
    { timestamp: Date.parse('2026-06-22T04:00:00Z') },
  ]

  assert.deepEqual(
    mapMarkerToKLinePoint({ created_at: '2026-06-22T03:45:00', price: 64270 }, dataList),
    {
      timestamp: Date.parse('2026-06-22T03:00:00Z'),
      dataIndex: 0,
      value: 64270,
    }
  )
})

test('mapMarkerToKLinePoint skips out-of-range trades instead of letting klinecharts pin them to the edge', () => {
  const dataList = [
    { timestamp: Date.parse('2026-06-22T03:00:00Z') },
    { timestamp: Date.parse('2026-06-22T04:00:00Z') },
  ]

  assert.equal(mapMarkerToKLinePoint({ created_at: '2026-06-22T02:59:59', price: 64270 }, dataList), null)
  assert.equal(mapMarkerToKLinePoint({ created_at: '2026-06-22T05:00:00', price: 64270 }, dataList), null)
})

test('mapMarkerToKLinePoint skips trades inside missing kline gaps', () => {
  const dataList = [
    { timestamp: Date.parse('2026-06-21T11:00:00Z') },
    { timestamp: Date.parse('2026-06-21T12:00:00Z') },
    { timestamp: Date.parse('2026-06-22T05:00:00Z') },
  ]

  assert.equal(mapMarkerToKLinePoint({ created_at: '2026-06-22T03:21:00', price: 64270 }, dataList), null)
})

test('syncTradeOverlays clears old marker group and creates new overlays through Pro internal chart api', () => {
  const calls = []
  const chart = {
    _chartApi: {
      getDataList: () => [
        { timestamp: Date.parse('2026-01-01T00:00:00Z') },
        { timestamp: Date.parse('2026-01-01T01:00:00Z') },
      ],
      removeOverlay: (payload) => calls.push(['remove', payload]),
      createOverlay: (payload) => calls.push(['create', payload]),
    },
  }

  const result = syncTradeOverlays(chart, [
    { id: 1, side: 'buy', price: 100, amount: 1, created_at: '2026-01-01T00:00:00' },
    { id: 2, side: 'sell', price: 110, amount: 1, created_at: '2026-01-01T01:00:00' },
  ])

  assert.equal(result.ok, true)
  assert.equal(calls[0][0], 'remove')
  assert.deepEqual(calls[0][1], { groupId: 'k7-trade-markers' })
  assert.equal(calls[1][0], 'create')
  assert.equal(calls[1][1].length, 2)
  assert.equal(calls[1][1][1].points[0].dataIndex, 1)
  assert.equal(calls[1][1][1].extendData.side, 'sell')
})

test('syncTradeOverlays does not fall back to raw timestamps when chart data is unavailable', () => {
  const calls = []
  const chart = {
    _chartApi: {
      removeOverlay: (payload) => calls.push(['remove', payload]),
      createOverlay: (payload) => calls.push(['create', payload]),
    },
  }

  const result = syncTradeOverlays(chart, [
    { id: 1, side: 'buy', price: 100, amount: 1, created_at: '2026-01-01T00:00:00' },
  ])

  assert.equal(result.ok, false)
  assert.equal(result.reason, 'chart-data-unavailable')
  assert.deepEqual(calls, [['remove', { groupId: 'k7-trade-markers' }]])
})
