export const statusLabels = {
  queued: '等待开始',
  running: '采集中',
  waiting: '等待处理',
  stopping: '正在停止',
  completed: '已完成',
  partial: '部分完成',
  unknown: '结果待核对',
  stopped: '已停止',
  failed: '采集失败',
  interrupted: '已中断',
}
export const activeStatuses = ['queued', 'running', 'waiting', 'stopping']

export function taskStatus(task) {
  if (task?.config?.mode === 'delivery' && task.status === 'failed'
    && /发送结果待核对|投递结果不明|本次投递结果待核对|消息发送过程中任务中断/.test(task.message || '')) {
    return 'unknown'
  }
  if (task?.config?.mode === 'delivery' && task.status === 'completed' && task.failed > 0) {
    return task.saved > 0 ? 'partial' : 'failed'
  }
  return task?.status || ''
}

export function taskFailedCount(task) {
  return Math.max(0, (task?.failed || 0) - (task?.status === 'failed' && taskStatus(task) === 'unknown' ? 1 : 0))
}

export function taskUnconfirmed(task) {
  return taskStatus(task) === 'unknown'
    ? Math.max(1, (task?.scanned || 0) - (task?.saved || 0) - (task?.duplicates || 0) - taskFailedCount(task))
    : 0
}

export function statusName(status, mode, action) {
  if (mode === 'delivery') {
    if (action === 'message') {
      if (status === 'running') return '发送中'
      if (status === 'failed') return '消息发送失败'
      if (status === 'unknown') return '消息待核对'
    }
    if (status === 'running') return '投递中'
    if (status === 'failed') return '投递失败'
  }
  return statusLabels[status] || status
}
