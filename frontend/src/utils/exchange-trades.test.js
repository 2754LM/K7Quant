import assert from 'node:assert/strict'
import test from 'node:test'

import { groupExchangeTradesByOrder } from './exchange-trades.js'

test('groupExchangeTradesByOrder folds fills with the same orderId into one weighted summary', () => {
  const rows = groupExchangeTradesByOrder([
    {
      id: 11,
      orderId: 9001,
      time: 2000,
      isBuyer: false,
      price: '64065.2100',
      qty: '0.000960',
      quoteQty: '61.5026016',
      commission: '0.06150260',
      commissionAsset: 'USDT',
      isMaker: false,
    },
    {
      id: 12,
      orderId: 9001,
      time: 2001,
      isBuyer: false,
      price: '64066.0000',
      qty: '0.020200',
      quoteQty: '1294.1332',
      commission: '1.29413320',
      commissionAsset: 'USDT',
      isMaker: false,
    },
    {
      id: 9,
      orderId: 42,
      time: 1000,
      isBuyer: true,
      price: '63000',
      qty: '0.001',
      quoteQty: '63',
      commission: '0.000001',
      commissionAsset: 'BTC',
      isMaker: true,
    },
  ])

  assert.equal(rows.length, 2)
  assert.equal(rows[0].orderId, 9001)
  assert.equal(rows[0].fillCount, 2)
  assert.equal(rows[0].side, 'sell')
  assert.equal(rows[0].qty, 0.02116)
  assert.equal(rows[0].quoteQty, 1355.6358016)
  assert.equal(rows[0].price, rows[0].quoteQty / rows[0].qty)
  assert.equal(rows[0].commissionText, '1.35563580 USDT')
  assert.equal(rows[0].liquidity, 'Taker')
  assert.deepEqual(rows[0].fills.map((fill) => fill.id), [12, 11])
})

test('groupExchangeTradesByOrder keeps single-fill orders expandable data and reports mixed fees', () => {
  const rows = groupExchangeTradesByOrder([
    {
      id: 1,
      orderId: 100,
      time: 1000,
      isBuyer: true,
      price: '100',
      qty: '1',
      quoteQty: '100',
      commission: '0.01',
      commissionAsset: 'USDT',
      isMaker: true,
    },
    {
      id: 2,
      orderId: 100,
      time: 1001,
      isBuyer: true,
      price: '101',
      qty: '1',
      quoteQty: '101',
      commission: '0.0001',
      commissionAsset: 'BTC',
      isMaker: false,
    },
  ])

  assert.equal(rows.length, 1)
  assert.equal(rows[0].commissionText, '0.00010000 BTC + 0.01000000 USDT')
  assert.equal(rows[0].liquidity, 'Mixed')
  assert.equal(rows[0].fills.length, 2)
})
