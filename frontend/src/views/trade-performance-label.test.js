import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import test from 'node:test'

const here = dirname(fileURLToPath(import.meta.url))
const tradeVue = readFileSync(join(here, 'Trade.vue'), 'utf8')

test('account performance card labels net return rate instead of win rate', () => {
  assert.match(tradeVue, /<span>收益率<\/span>/)
  assert.match(tradeVue, /fmtPct\(accountPerformance\.profitRate\)/)
  assert.doesNotMatch(tradeVue, /<span>盈利率<\/span>\s*<b>\{\{ fmtUnsignedPct\(accountPerformance\.winRate\) \}\}<\/b>/)
})
