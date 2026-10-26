export function number(value) {
  return value === undefined || value === null
    ? '—'
    : Number(value).toLocaleString('zh-CN')
}
export function time(value, full = false) {
  if (!value) return '—'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    ...(full ? { month: '2-digit', day: '2-digit' } : {}),
    hour: '2-digit',
    minute: '2-digit',
    ...(full ? {} : { second: '2-digit' }),
    hour12: false,
  }).format(new Date(value))
}
