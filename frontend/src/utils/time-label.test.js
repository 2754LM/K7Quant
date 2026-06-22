import assert from 'node:assert/strict'
import test from 'node:test'

import { formatClock } from './time-label.js'

test('formatClock renders local clock time with seconds', () => {
  const date = new Date(2026, 0, 2, 3, 4, 5)
  assert.equal(formatClock(date), '03:04:05')
})

test('formatClock returns dash for empty values', () => {
  assert.equal(formatClock(null), '-')
})
