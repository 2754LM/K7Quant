import assert from 'node:assert/strict'
import test from 'node:test'

import { buildTradeAnalytics } from './trade-stats.js'

test('buildTradeAnalytics computes FIFO realized and unrealized PnL for the selected symbol', () => {
  const trades = [
    { id: 4, symbol: 'ETHUSDT', side: 'buy', price: 2000, amount: 1, created_at: '2026-01-01T09:00:00' },
    { id: 3, symbol: 'BTCUSDT', side: 'sell', price: 150, amount: 1.5, created_at: '2026-01-01T12:00:00' },
    { id: 2, symbol: 'BTCUSDT', side: 'buy', price: 120, amount: 1, created_at: '2026-01-01T11:00:00' },
    { id: 1, symbol: 'BTCUSDT', side: 'buy', price: 100, amount: 1, created_at: '2026-01-01T10:00:00' },
  ]

  const result = buildTradeAnalytics(trades, { symbol: 'BTCUSDT', currentPrice: 160 })

  assert.equal(result.tradeCount, 3)
  assert.equal(result.buyCount, 2)
  assert.equal(result.sellCount, 1)
  assert.equal(result.positionQty, 0.5)
  assert.equal(result.costBasis, 60)
  assert.equal(result.avgCost, 120)
  assert.equal(result.marketValue, 80)
  assert.equal(result.realizedPnl, 65)
  assert.equal(result.unrealizedPnl, 20)
  assert.equal(result.totalPnl, 85)
  assert.equal(result.winRate, 1)
  assert.deepEqual(result.markers.map((m) => m.side), ['buy', 'buy', 'sell'])

  const sellRow = result.rows.find((row) => row.id === 3)
  assert.equal(sellRow.realizedPnl, 65)
  assert.equal(sellRow.positionQty, 0.5)
  assert.equal(sellRow.avgCost, 120)
})

test('buildTradeAnalytics reports flat positions without inventing unrealized PnL', () => {
  const result = buildTradeAnalytics([
    { id: 1, symbol: 'BTCUSDT', side: 'buy', price: 100, amount: 2, created_at: '2026-01-01T10:00:00' },
    { id: 2, symbol: 'BTCUSDT', side: 'sell', price: 90, amount: 2, created_at: '2026-01-01T11:00:00' },
  ], { symbol: 'BTCUSDT', currentPrice: 120 })

  assert.equal(result.positionQty, 0)
  assert.equal(result.avgCost, 0)
  assert.equal(result.costBasis, 0)
  assert.equal(result.realizedPnl, -20)
  assert.equal(result.unrealizedPnl, 0)
  assert.equal(result.totalPnl, -20)
  assert.equal(result.winRate, 0)
})
