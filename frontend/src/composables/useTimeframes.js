// 统一获取 Binance 时间框架白名单 (单一来源)
// 各 Vue 组件 useTimeframes() 即可拿到 list + group, 自动 cache
import { ref, computed } from 'vue'
import { getTimeframes } from '../api'

let _cache = null
const _fetching = ref(false)
const _list = ref([])
const _error = ref(null)

async function _ensure() {
  if (_cache) return _cache
  if (_fetching.value) return _cache
  _fetching.value = true
  try {
    const r = await getTimeframes()
    _list.value = r?.data?.timeframes || []
    _cache = _list.value
    _error.value = null
  } catch (e) {
    // 兜底: 用本地 Binance 白名单
    _list.value = [
      '1s', '1m', '3m', '5m', '15m', '30m',
      '1h', '2h', '4h', '6h', '8h', '12h',
      '1d', '3d', '1w', '1M',
    ]
    _cache = _list.value
    _error.value = e
  } finally {
    _fetching.value = false
  }
  return _cache
}

// 立即启动加载 (不阻塞)
_ensure()

export function useTimeframes() {
  const list = computed(() => _list.value)
  const loading = computed(() => _fetching.value)
  const error = computed(() => _error.value)

  // 按单位分组 (按 Binance 官方分组顺序)
  const groups = computed(() => [
    { label: '秒',   unit: 's', tfs: _list.value.filter(t => t.endsWith('s')) },
    { label: '分钟', unit: 'm', tfs: _list.value.filter(t => t.endsWith('m')) },
    { label: '小时', unit: 'h', tfs: _list.value.filter(t => t.endsWith('h')) },
    { label: '天',   unit: 'd', tfs: _list.value.filter(t => t.endsWith('d')) },
    { label: '周',   unit: 'w', tfs: _list.value.filter(t => t.endsWith('w')) },
    { label: '月',   unit: 'M', tfs: _list.value.filter(t => t.endsWith('M')) },
  ].filter(g => g.tfs.length > 0))

  // 给 n-select / el-select 用的 options 格式
  const options = computed(() => _list.value.map(tf => ({
    label: tf,
    value: tf,
  })))

  // 强制刷新 (例如用户切交易所后)
  function refresh() {
    _cache = null
    return _ensure()
  }

  return { list, groups, options, loading, error, refresh }
}
