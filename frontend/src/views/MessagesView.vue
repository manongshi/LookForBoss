<script setup>
import { computed, onActivated, onDeactivated, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { ArrowUpRight, ChevronLeft, ChevronRight, Copy, RefreshCw, Search, X } from 'lucide-vue-next'
import PageHeading from '../layouts/PageHeading.vue'
import { request } from '../api'
import { useWorkspace } from '../stores/workspace'
import { platformName } from '../constants/platforms'
import { number } from '../utils/format'

const route = useRoute()
const { dbConnected, system, refreshVersion, copyText } = useWorkspace()
const records = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)
const active = ref(false)
const error = ref('')
const query = reactive({ q: '', status: 'confirmed', date_from: '', date_to: '', job_id: '', task_id: '' })
const pages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
const statusLabels = {
  confirmed: '已发送', pending: '发送中', queued: '等待发送',
  unknown: '待核对', failed: '发送失败', skipped: '已跳过', not_sent: '未发送',
}
const hasFilters = computed(() => Boolean(query.q || query.date_from || query.date_to || query.job_id || query.task_id || query.status !== 'confirmed'))
const dateFormatter = new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
let version = 0
let searchTimer = null
function formatTime(value) { return value ? dateFormatter.format(new Date(value)) : '—' }
function originalUrl(value) {
  try { return new URL(value).protocol === 'https:' ? value : '' } catch { return '' }
}
async function loadRecords() {
  clearTimeout(searchTimer)
  if (!active.value || !dbConnected.value) return
  const current = ++version
  loading.value = true
  error.value = ''
  try {
    if (query.date_from && query.date_to && query.date_from > query.date_to) throw new Error('开始日期不能晚于结束日期')
    const params = new URLSearchParams(Object.entries({ ...query, page: String(page.value), page_size: String(pageSize) }).filter(([, value]) => value !== ''))
    const result = await request(`/messages?${params}`)
    if (current !== version || !active.value) return
    if (page.value > Math.max(1, Math.ceil(result.total / pageSize))) {
      page.value = Math.max(1, Math.ceil(result.total / pageSize))
      await loadRecords()
      return
    }
    records.value = result.items
    total.value = result.total
  } catch (e) {
    if (current === version) error.value = e.message
  } finally {
    if (current === version) loading.value = false
  }
}
function changePage(value) {
  if (loading.value || value < 1 || value > pages.value) return
  page.value = value
  loadRecords()
  window.scrollTo({ top: 0, behavior: 'auto' })
}
function resetFilters() {
  Object.assign(query, { q: '', status: 'confirmed', date_from: '', date_to: '', job_id: '', task_id: '' })
}
watch(query, () => {
  version++
  clearTimeout(searchTimer)
  records.value = []
  total.value = 0
  page.value = 1
  loading.value = false
  if (active.value) searchTimer = setTimeout(loadRecords, 300)
}, { deep: true })
watch(() => [route.name, route.query.job, route.query.task, route.query.status], () => {
  if (route.name !== 'messages') return
  const job = String(route.query.job || '')
  const task = String(route.query.task || '')
  const requestedStatus = String(route.query.status || '')
  if (job !== query.job_id || task !== query.task_id) {
    query.job_id = job
    query.task_id = task
    query.status = job || task ? '' : 'confirmed'
    query.q = ''
  }
  if (requestedStatus === 'all') query.status = ''
  else if (Object.hasOwn(statusLabels, requestedStatus)) query.status = requestedStatus
}, { immediate: true })
watch(dbConnected, connected => {
  if (connected) loadRecords()
  else { version++; clearTimeout(searchTimer); records.value = []; total.value = 0; loading.value = false }
})
watch(refreshVersion, loadRecords)
watch(() => system.value?.active_task_id, loadRecords)
watch(system, () => { if (system.value?.active_task_id && !loading.value) loadRecords() })
onActivated(() => { active.value = true; loadRecords() })
onDeactivated(() => { active.value = false; version++; clearTimeout(searchTimer); loading.value = false })
onBeforeUnmount(() => { version++; clearTimeout(searchTimer) })
</script>

<template>
  <div class="messages-page">
    <PageHeading><button class="button button-white" :disabled="loading || !dbConnected" @click="loadRecords"><RefreshCw :size="16" :class="{ spin: loading }" />刷新记录</button></PageHeading>
    <section class="panel messages-panel" aria-label="消息发送记录" :aria-busy="loading">
      <div class="message-filters">
        <div class="search-field"><Search :size="17" /><input v-model="query.q" maxlength="100" aria-label="搜索消息、职位或公司" placeholder="搜索消息内容、职位、公司" /><button v-if="query.q" aria-label="清空搜索" @click="query.q = ''"><X :size="16" /></button></div>
        <select v-model="query.status" aria-label="按发送结果筛选"><option value="">全部结果</option><option v-for="(label, value) in statusLabels" :key="value" :value="value">{{ label }}</option></select>
        <div class="date-range"><input v-model="query.date_from" type="date" :max="query.date_to || undefined" aria-label="开始日期" /><span>至</span><input v-model="query.date_to" type="date" :min="query.date_from || undefined" aria-label="结束日期" /></div>
      </div>
      <div class="message-list-caption"><span>{{ query.status === 'confirmed' ? '已发送的消息' : '消息记录' }} <strong>{{ number(total) }}</strong></span><button v-if="hasFilters" class="text-action" @click="resetFilters">清除筛选</button></div>
      <div v-if="query.job_id || query.task_id" class="scope-notice"><span>{{ query.job_id ? '正在查看所选职位的消息' : '正在查看所选任务的消息' }}</span><button class="text-action" @click="query.job_id = ''; query.task_id = ''">查看全部职位</button></div>
      <div v-if="error" class="load-error" role="alert"><span>{{ error }}</span><button class="text-action" :disabled="loading" @click="loadRecords">重新加载</button></div>
      <div v-if="records.length" class="message-records">
        <article v-for="record in records" :key="record.id" class="message-record">
          <header class="record-header">
            <div class="recipient"><span class="company-letter" aria-hidden="true">{{ record.company?.slice(0, 1) || '企' }}</span><div><h2>{{ record.job_title }}</h2><p>{{ record.company || '公司未标注' }}<span v-if="record.recruiter"> · {{ record.recruiter }}</span><span> · {{ platformName(record.platform) }}</span></p></div></div>
            <span class="message-status" :class="record.status"><span></span>{{ statusLabels[record.status] || record.status }}</span>
          </header>
          <p class="message-content">{{ record.content }}</p>
          <p v-if="record.status !== 'confirmed' && record.result_message" class="result-message">{{ record.result_message }}</p>
          <footer class="record-footer">
            <div class="record-meta"><time :datetime="record.sent_at || record.updated_at || record.created_at">{{ record.sent_at ? '确认发送于' : '更新于' }} {{ formatTime(record.sent_at || record.updated_at || record.created_at) }}</time><span v-if="record.task_name">{{ record.task_name }}</span></div>
            <div class="record-actions"><button @click="copyText(record.content)"><Copy :size="15" />复制消息</button><a v-if="originalUrl(record.job_url)" :href="originalUrl(record.job_url)" target="_blank" rel="noopener noreferrer">原始职位<ArrowUpRight :size="15" /></a></div>
          </footer>
        </article>
      </div>
      <div v-else-if="!error" class="empty-state" role="status">
        <h3>{{ loading ? '正在读取消息记录' : !dbConnected ? '连接后查看消息记录' : hasFilters ? '没有符合条件的消息' : '还没有已发送的消息' }}</h3>
        <p>{{ loading ? '正在加载发送内容和结果。' : !dbConnected ? '请先连接数据库，再查看已保存的记录。' : hasFilters ? '试试调整搜索、日期或发送结果。' : '在职位列表勾选职位并发送消息后，可以在这里查看。' }}</p>
        <RouterLink v-if="!dbConnected" class="button button-white" :to="{ name: 'settings' }">连接设置</RouterLink>
        <button v-else-if="!loading && hasFilters" class="button button-white" @click="resetFilters">清除筛选</button>
        <RouterLink v-else-if="!loading" class="button button-primary" :to="{ name: 'jobs' }">查看我的职位</RouterLink>
      </div>
      <footer v-if="total" class="table-footer"><span>共 {{ number(total) }} 条 · 第 {{ page }} / {{ pages }} 页</span><div class="pagination"><button :disabled="page <= 1 || loading" aria-label="上一页" @click="changePage(page - 1)"><ChevronLeft :size="18" /></button><span>{{ page }}</span><button :disabled="page >= pages || loading" aria-label="下一页" @click="changePage(page + 1)"><ChevronRight :size="18" /></button></div></footer>
    </section>
  </div>
</template>

<style scoped>
.messages-page { min-width: 0; }
.message-filters { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; padding: 24px 24px 12px; }
.message-filters .search-field { flex: 1; min-width: 220px; }
.message-filters .search-field input { min-height: 42px; padding: 8px 0; }
.message-filters .search-field button { display: grid; place-items: center; min-width: 32px; min-height: 40px; padding: 0; }
.message-filters > select { width: 140px; min-height: 44px; }
.date-range { display: flex; align-items: center; gap: 8px; color: var(--muted); font-size: 14px; }
.date-range input { width: 155px; min-height: 44px; padding: 9px 10px; }
.message-list-caption { display: flex; justify-content: space-between; align-items: center; gap: 12px; min-height: 56px; padding: 0 24px 8px; color: var(--muted); font-size: 14px; }
.message-list-caption strong { margin-left: 8px; color: var(--ink); font-weight: 600; font-variant-numeric: tabular-nums; }
.text-action { display: inline-flex; align-items: center; min-height: 44px; padding: 0; color: var(--accent); font-size: 14px; }
.scope-notice, .load-error { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px 20px; margin: 0 24px 16px; padding: 4px 14px; border-radius: 11px; background: var(--canvas); color: var(--muted); font-size: 14px; line-height: 1.7; }
.load-error { color: #b42318; background: #fff4f2; }
.message-record { border-top: 1px solid var(--line); padding: 24px; }
.record-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; }
.recipient { display: flex; align-items: flex-start; min-width: 0; gap: 14px; }
.company-letter { display: grid; place-items: center; width: 44px; height: 44px; flex-shrink: 0; border-radius: 11px; background: var(--canvas); color: var(--muted); font-size: 21px; }
.recipient h2 { margin-bottom: 6px; overflow-wrap: anywhere; line-height: 1.4; }
.recipient p { color: var(--muted); font-size: 14px; line-height: 1.7; overflow-wrap: anywhere; }
.message-status { display: inline-flex; align-items: center; flex-shrink: 0; gap: 6px; min-height: 28px; border-radius: 999px; padding: 4px 10px; color: var(--muted); background: var(--canvas); font-size: 12px; white-space: nowrap; }
.message-status > span { width: 5px; height: 5px; border-radius: 50%; background: currentColor; }
.message-status.confirmed { color: #237a45; background: #eef7f0; }
.message-status.pending, .message-status.queued { color: var(--accent); background: #eaf3fc; }
.message-status.unknown { color: #95631b; background: #fff6e7; }
.message-status.failed { color: #b42318; background: #fff0ed; }
.message-content { margin-top: 20px; padding: 20px; border-radius: 11px; background: var(--canvas); color: var(--ink); font-size: 17px; line-height: 1.8; white-space: pre-wrap; overflow-wrap: anywhere; }
.result-message { margin-top: 12px; font-size: 14px; color: var(--muted); line-height: 1.7; overflow-wrap: anywhere; }
.record-footer { display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: 8px 24px; margin-top: 16px; }
.record-meta { display: flex; flex-direction: column; gap: 4px; min-width: 0; color: var(--muted); font-size: 12px; line-height: 1.7; }
.record-meta time { font-variant-numeric: tabular-nums; }
.record-meta > span { overflow-wrap: anywhere; }
.record-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 20px; }
.record-actions button, .record-actions a { display: inline-flex; align-items: center; min-height: 44px; gap: 6px; padding: 0; color: var(--accent); font-size: 14px; }
@media (max-width: 900px) {
  .date-range { flex-basis: 100%; }
}
@media (max-width: 640px) {
  .message-filters { padding: 20px 16px 12px; }
  .message-filters .search-field { flex-basis: 100%; }
  .message-filters > select { width: 100%; }
  .date-range { width: 100%; }
  .date-range input { flex: 1; min-width: 0; width: auto; }
  .message-list-caption { padding-right: 16px; padding-left: 16px; }
  .scope-notice, .load-error { margin-right: 16px; margin-left: 16px; }
  .message-record { padding: 20px 16px; }
  .record-header { flex-wrap: wrap; gap: 12px; }
  .message-status { margin-left: 58px; }
  .message-content { padding: 16px; font-size: 15px; }
}
</style>
