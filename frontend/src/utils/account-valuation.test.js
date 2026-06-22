import assert from 'node:assert/strict'
import test from 'node:test'

import {
  appendAccountSnapshot,
  assetsNeedingUsdtTicker,
  buildAccountHistoryFromTrades,
  buildAccountPerformance,
  buildAccountValuation,
  priceForAsset,
} from './account-valuation.js'

test('priceForAsset values stable assets at 1 USDT and crypto assets from ticker prices', () => {
  assert.equal(priceForAsset('USDT', {}), 1)
  assert.equal(priceForAsset('USDC', {}), 1)
  assert.equal(priceForAsset('BTC', { BTCUSDT: 64000 }), 64000)
  assert.equal(priceForAsset('UNKNOWN', {}), 0)
})

test('buildAccountValuation computes total account value and selected symbol holdings from balances', () => {
  const valuation = buildAccountValuation([
    { asset: 'USDT', free: 100, locked: 5, total: 105 },
    { asset: 'USDC', free: 50, locked: 0, total: 50 },
    { asset: 'BTC', free: 0.01, locked: 0.002, total: 0.012 },
  ], { BTCUSDT: 65000 }, { symbol: 'BTCUSDT' })

  assert.equal(valuation.totalValue, 935)
  assert.equal(valuation.selectedAsset, 'BTC')
  assert.equal(valuation.selectedQty, 0.012)
  assert.equal(valuation.selectedFree, 0.01)
  assert.equal(valuation.selectedLocked, 0.002)
  assert.equal(valuation.selectedValue, 780)
  assert.deepEqual(valuation.unpricedAssets, [])
})

test('buildAccountValuation reports unpriced assets without adding them to total value', () => {
  const valuation = buildAccountValuation([
    { asset: 'FOO', free: 3, locked: 0, total: 3 },
    { asset: 'USDT', free: 10, locked: 0, total: 10 },
  ], {}, { symbol: 'FOOUSDT' })

  assert.equal(valuation.totalValue, 10)
  assert.equal(valuation.selectedQty, 3)
  assert.equal(valuation.selectedValue, 0)
  assert.deepEqual(valuation.unpricedAssets, ['FOO'])
})

test('buildAccountValuation exposes sorted position rows with account allocation', () => {
  const valuation = buildAccountValuation([
    { asset: 'USDT', free: 100, locked: 0, total: 100 },
    { asset: 'BTC', free: 0.01, locked: 0, total: 0.01 },
    { asset: 'FOO', free: 1, locked: 0, total: 1 },
  ], { BTCUSDT: 65000 }, { symbol: 'BTCUSDT' })

  assert.deepEqual(valuation.assetRows.map((row) => row.asset), ['BTC', 'USDT', 'FOO'])
  assert.equal(valuation.assetRows[0].allocation, 0.866667)
  assert.equal(valuation.assetRows[1].allocation, 0.133333)
  assert.equal(valuation.assetRows[2].allocation, 0)
})

test('appendAccountSnapshot records value changes and ignores unchanged totals', () => {
  const first = appendAccountSnapshot([], { totalValue: 100, selectedValue: 10, selectedQty: 0.1 }, 1000)
  const unchanged = appendAccountSnapshot(first, { totalValue: 100, selectedValue: 11, selectedQty: 0.1 }, 2000)
  const changed = appendAccountSnapshot(unchanged, { totalValue: 101, selectedValue: 12, selectedQty: 0.1 }, 3000)

  assert.equal(first.length, 1)
  assert.equal(unchanged.length, 1)
  assert.equal(changed.length, 2)
  assert.deepEqual(changed[1], { time: 3000, totalValue: 101, selectedValue: 12, selectedQty: 0.1 })
})

test('appendAccountSnapshot can force a refresh point even when total value is unchanged', () => {
  const first = appendAccountSnapshot([], { totalValue: 100, selectedValue: 10, selectedQty: 0.1 }, 1000)
  const forced = appendAccountSnapshot(first, { totalValue: 100, selectedValue: 10, selectedQty: 0.1 }, 2000, { force: true })

  assert.equal(forced.length, 2)
  assert.equal(forced[1].time, 2000)
  assert.equal(forced[1].totalValue, 100)
})

test('buildAccountPerformance computes return, win rate, payoff ratio and expectancy from account history', () => {
  const metrics = buildAccountPerformance([
    { time: 1000, totalValue: 1000 },
    { time: 2000, totalValue: 1010 },
    { time: 3000, totalValue: 1005 },
    { time: 4000, totalValue: 1025 },
  ])

  assert.equal(metrics.tradeCount, 3)
  assert.equal(metrics.profitAmount, 25)
  assert.equal(metrics.profitRate, 0.025)
  assert.equal(metrics.winRate, 2 / 3)
  assert.equal(metrics.payoffRatio, 3)
  assert.equal(metrics.expectancy, 8.3333333333)
  assert.equal(metrics.avgWin, 15)
  assert.equal(metrics.avgLoss, -5)
})

test('buildAccountPerformance returns empty metrics when there is not enough history', () => {
  const metrics = buildAccountPerformance([{ time: 1000, totalValue: 1000 }])

  assert.equal(metrics.tradeCount, 0)
  assert.equal(metrics.profitAmount, 0)
  assert.equal(metrics.winRate, 0)
  assert.equal(metrics.payoffRatio, 0)
  assert.equal(metrics.expectancy, 0)
})

test('assetsNeedingUsdtTicker returns non-stable non-zero balance assets with available USDT symbols', () => {
  assert.deepEqual(
    assetsNeedingUsdtTicker([
      { asset: 'USDT', total: 100 },
      { asset: 'BTC', total: 0.1 },
      { asset: 'ETH', total: 0 },
      { asset: 'FOO', total: 1 },
    ], ['BTCUSDT']),
    ['BTC']
  )
})

test('buildAccountHistoryFromTrades reconstructs account value from the first trade using current balances', () => {
  const history = buildAccountHistoryFromTrades([
    { asset: 'USDT', total: 943.956 },
    { asset: 'BTC', total: 0.00599 },
  ], [
    {
      id: 2,
      time: 2000,
      isBuyer: false,
      price: '11000',
      qty: '0.004',
      quoteQty: '44',
      commission: '0.044',
      commissionAsset: 'USDT',
    },
    {
      id: 1,
      time: 1000,
      isBuyer: true,
      price: '10000',
      qty: '0.01',
      quoteQty: '100',
      commission: '0.00001',
      commissionAsset: 'BTC',
    },
  ], {
    symbol: 'BTCUSDT',
    prices: { BTCUSDT: 12000 },
    now: 3000,
  })

  assert.equal(history.length, 3)
  assert.deepEqual(history.map((point) => point.time), [1000, 2000, 3000])
  assert.equal(history[0].selectedQty, 0.00999)
  assert.equal(history[0].totalValue, 999.9)
  assert.equal(history[1].selectedQty, 0.00599)
  assert.equal(history[1].totalValue, 1009.846)
  assert.equal(history[2].totalValue, 1015.836)
})

test('buildAccountHistoryFromTrades reconstructs one account timeline across multiple traded symbols', () => {
  const history = buildAccountHistoryFromTrades([
    { asset: 'USDT', total: 899 },
    { asset: 'BTC', total: 0.00999 },
    { asset: 'ETH', total: 0.5 },
  ], [
    {
      id: 1,
      symbol: 'BTCUSDT',
      time: 1000,
      isBuyer: true,
      price: '10000',
      qty: '0.01',
      quoteQty: '100',
      commission: '0.00001',
      commissionAsset: 'BTC',
    },
    {
      id: 2,
      symbol: 'ETHUSDT',
      time: 2000,
      isBuyer: true,
      price: '2000',
      qty: '0.5',
      quoteQty: '1000',
      commission: '1',
      commissionAsset: 'USDT',
    },
  ], {
    symbol: 'BTCUSDT',
    prices: { BTCUSDT: 12000, ETHUSDT: 2100 },
    now: 3000,
  })

  assert.equal(history.length, 3)
  assert.deepEqual(history.map((point) => point.time), [1000, 2000, 3000])
  assert.equal(history[0].totalValue, 1999.9)
  assert.equal(history[1].totalValue, 1998.9)
  assert.equal(history[2].totalValue, 2068.88)
  assert.equal(history[2].selectedQty, 0.00999)
  assert.equal(history[2].selectedValue, 119.88)
})
