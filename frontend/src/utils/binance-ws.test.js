import assert from 'node:assert/strict'
import test from 'node:test'

import { closeAllStreams, subscribeTicker } from './binance-ws.js'

const sockets = []

class MockWebSocket {
  constructor(url) {
    this.url = url
    this.closed = false
    sockets.push(this)
  }

  close() {
    this.closed = true
  }

  sendMessage(payload) {
    this.onmessage?.({ data: JSON.stringify(payload) })
  }
}

test('subscribeTicker opens a Binance ticker stream and normalizes the latest price', () => {
  const originalWebSocket = globalThis.WebSocket
  globalThis.WebSocket = MockWebSocket
  sockets.length = 0

  try {
    let received = null
    const unsubscribe = subscribeTicker('BTCUSDT', (ticker) => {
      received = ticker
    })

    assert.equal(sockets.length, 1)
    assert.equal(sockets[0].url, 'wss://stream.binance.com:9443/ws/btcusdt@ticker')

    sockets[0].sendMessage({
      e: '24hrTicker',
      E: 1710000000000,
      s: 'BTCUSDT',
      c: '65000.50',
      p: '120.25',
      P: '1.23',
      o: '64880.25',
      h: '66000.00',
      l: '63000.00',
      v: '10.5',
      q: '680000.75',
    })

    assert.deepEqual(received, {
      symbol: 'BTCUSDT',
      eventTime: 1710000000000,
      price: 65000.5,
      priceChange: 120.25,
      priceChangePercent: 1.23,
      open: 64880.25,
      high: 66000,
      low: 63000,
      volume: 10.5,
      quoteVolume: 680000.75,
    })

    unsubscribe()
    assert.equal(sockets[0].closed, true)
  } finally {
    closeAllStreams()
    globalThis.WebSocket = originalWebSocket
  }
})
