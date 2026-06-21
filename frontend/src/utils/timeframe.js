// 时间框架工具: 把 K 线周期转成分钟数 / 人类可读时长
const TF_MIN = {
  '1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30,
  '1h': 60, '2h': 120, '4h': 240, '6h': 360, '12h': 720,
  '1d': 1440, '3d': 4320, '1w': 10080,
}

const TF_LABEL = {
  '1m': '1分钟', '3m': '3分钟', '5m': '5分钟', '15m': '15分钟', '30m': '30分钟',
  '1h': '1小时', '2h': '2小时', '4h': '4小时', '6h': '6小时', '12h': '12小时',
  '1d': '1天', '3d': '3天', '1w': '1周',
}

export function tfMinutes(tf) {
  return TF_MIN[tf] || 1
}

export function tfLabel(tf) {
  return TF_LABEL[tf] || tf
}
