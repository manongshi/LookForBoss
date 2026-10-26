<script setup>
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { ArrowRight, Building2, ChevronLeft, ChevronRight, MapPin, RefreshCw, Search, X } from 'lucide-vue-next'
import JobDetailDrawer from './JobDetailDrawer.vue'
import DeliveryDialog from './DeliveryDialog.vue'
import { platformNames, platformName, deliveryName } from '../../constants/platforms'
import { useWorkspace } from '../../stores/workspace'
import { number } from '../../utils/format'

const props = defineProps({ list: { type: Object, required: true }, workbench: Boolean })
const { stats, dbConnected, loginPending, isActive } = useWorkspace()
const { query, jobs, total, page, pages, busy, loadJobs } = props.list
const targetPage = ref(page.value)
const selectedIds = ref([])
const deliveryJobs = ref([])
const deliveryAction = ref('resume')
const drawer = ref(null)
const panel = ref(null)
const selectedJobs = computed(() => jobs.value.filter(job => selectedIds.value.includes(job.id)))
const eligibleJobs = computed(() => jobs.value.filter(job => !job.blacklist_hits?.length))
const hasFilters = computed(() => Boolean(query.q || query.city || query.task_id || query.platform || query.keyword))
const awaitingLogin = computed(() => props.workbench && query.task_id && loginPending.value)
watch(eligibleJobs, () => {
  selectedIds.value = selectedIds.value.filter(id => eligibleJobs.value.some(job => job.id === id))
})
watch(page, value => { targetPage.value = value })
function deliveryStarted() {
  deliveryJobs.value = []
  selectedIds.value = []
  loadJobs()
}
function openDetail(job, event) { drawer.value.openDetail(job, event) }
function openDelivery(action) {
  deliveryAction.value = action
  deliveryJobs.value = [...selectedJobs.value]
}
function changePage(value) {
  if (busy.jobs || !Number.isSafeInteger(value) || value < 1 || value > pages.value) return
  targetPage.value = value
  page.value = value
  panel.value?.scrollIntoView({ block: 'start', behavior: 'auto' })
}
function jumpToPage() { changePage(Number(targetPage.value)) }
function clearFilters() { Object.assign(query, { q: '', city: '', task_id: '', platform: '', keyword: '' }) }
function summary(job) {
  return job.description?.replace(/\s+/g, ' ').trim() || (job.detail_status === 'pending'
    ? '职位描述正在补充中。'
    : '暂未获取职位描述，可打开详情查看原始职位。')
}
</script>

<template>
  <section ref="panel" class="panel jobs-panel" aria-label="职位列表" :aria-busy="busy.jobs">
    <header class="jobs-panel-heading">
      <h2>{{ query.keyword ? `${query.keyword} · 职位` : query.task_id ? '本次采集' : '已采集职位' }}<span>{{ number(total) }}</span></h2>
      <button class="icon-button" aria-label="刷新职位列表" :disabled="busy.jobs || !dbConnected" @click="loadJobs"><RefreshCw :size="18" :class="{ spin: busy.jobs }" /></button>
    </header>
    <slot name="filters" />
    <div class="jobs-toolbar">
      <div class="search-field">
        <Search :size="17" /><input v-model="query.q" aria-label="搜索职位或公司" placeholder="搜索职位、公司" />
        <button v-if="query.q" aria-label="清空搜索" @click="query.q = ''"><X :size="16" /></button>
      </div>
      <select v-model="query.platform" aria-label="按招聘平台筛选">
        <option value="">全部平台</option>
        <option v-for="(name, id) in platformNames" :key="id" :value="id">{{ name }}</option>
      </select>
      <select v-model="query.city" aria-label="按城市筛选">
        <option value="">全部城市</option>
        <option v-for="city in stats?.city_options || []" :key="city" :value="city">{{ city }}</option>
      </select>
      <button v-if="query.task_id" class="clear-task-filter" @click="query.task_id = ''">全部任务<X :size="14" /></button>
    </div>
    <div v-if="jobs.length" class="list-utilities">
      <label class="select-all"><input type="checkbox" :disabled="isActive || !eligibleJobs.length" :checked="eligibleJobs.length > 0 && selectedIds.length === eligibleJobs.length" :indeterminate="selectedIds.length > 0 && selectedIds.length < eligibleJobs.length" @change="selectedIds = $event.target.checked ? eligibleJobs.map(job => job.id) : []" />选择本页</label>
      <span v-if="busy.jobs" role="status">正在更新…</span>
      <span v-else>最近采集优先</span>
    </div>
    <div v-if="selectedJobs.length" class="delivery-toolbar">
      <span>已选 {{ selectedJobs.length }} 个职位</span>
      <div><button class="cancel-selection" @click="selectedIds = []">取消选择</button><button v-if="selectedJobs.every(job => (job.source || 'boss') === 'boss')" class="button button-primary" :disabled="isActive || selectedJobs.length > 50" @click="openDelivery('message')">发送消息</button><button class="button button-white" :disabled="isActive || selectedJobs.length > 50" @click="openDelivery('resume')">投递简历</button></div>
    </div>
    <div v-if="jobs.length" class="job-list">
      <article v-for="job in jobs" :key="job.id" class="job-item" :class="{ selected: selectedIds.includes(job.id) }">
        <label class="job-selection"><input v-model="selectedIds" type="checkbox" :value="job.id" :disabled="isActive || Boolean(job.blacklist_hits?.length)" :aria-label="`选择 ${job.title}${job.blacklist_hits?.length ? '（黑名单已拦截）' : ''}`" /></label>
        <div class="job-content">
          <div class="job-headline"><h3><button class="job-title" @click="openDetail(job, $event)">{{ job.title }}</button></h3><strong class="salary-text">{{ job.salary || '薪资未标注' }}</strong></div>
          <div class="job-meta"><span class="company-line"><Building2 :size="15" />{{ job.company || '公司未标注' }}</span><span><MapPin :size="14" />{{ job.location || job.city || '地点未标注' }}</span><span>{{ job.experience || '经验不限' }}</span><span>{{ job.degree || '学历不限' }}</span></div>
          <p class="job-summary">{{ summary(job) }}</p>
          <div v-if="job.tags?.length" class="job-tags"><span v-for="tag in job.tags.slice(0, 5)" :key="tag">{{ tag }}</span></div>
          <div class="job-bottom"><div class="job-source"><span>{{ platformName(job.source) }}</span><span v-if="job.delivery_status">{{ deliveryName(job.delivery_status, job.delivery_action) }}</span><span v-if="job.blacklist_hits?.length" class="blocked-label">黑名单 · 禁止投递</span></div><button class="detail-action" @click="openDetail(job, $event)">查看详情<ArrowRight :size="15" /></button></div>
        </div>
      </article>
    </div>
    <div v-else class="empty-state" role="status">
      <h3>{{ awaitingLogin ? '登录后开始采集' : busy.jobs ? '正在读取职位' : !dbConnected ? '连接后查看职位' : hasFilters ? '没有符合条件的职位' : '从第一份职位开始' }}</h3>
      <p>{{ awaitingLogin ? '在浏览器完成登录后，点击上方“我已登录，继续采集”。' : busy.jobs ? '正在加载采集结果，请稍候。' : !dbConnected ? '请在连接设置中连接数据库。' : hasFilters ? '调整筛选条件，或查看全部已采集职位。' : workbench ? '输入上方职位关键词并开始采集，结果会显示在这里。' : '采集感兴趣的职位，在这里集中查看。' }}</p>
      <RouterLink v-if="!dbConnected" class="button button-white" :to="{ name: 'settings' }">连接设置</RouterLink>
      <button v-else-if="hasFilters && !busy.jobs && !awaitingLogin" class="button button-white" @click="clearFilters">清除筛选</button>
      <RouterLink v-else-if="!workbench && !busy.jobs" class="button button-white" :to="{ name: 'workbench' }">采集职位<ArrowRight :size="15" /></RouterLink>
    </div>
    <footer v-if="total" class="table-footer">
      <span>共 {{ number(total) }} 个职位</span>
      <div class="jobs-pagination">
        <div class="pagination"><button :disabled="page <= 1 || busy.jobs" aria-label="上一页" @click="changePage(page - 1)"><ChevronLeft :size="18" /></button><span aria-label="当前页">{{ page }}</span><button :disabled="page >= pages || busy.jobs" aria-label="下一页" @click="changePage(page + 1)"><ChevronRight :size="18" /></button></div>
        <span class="page-total">共 {{ number(pages) }} 页</span>
        <form class="page-jump" @submit.prevent="jumpToPage">
          <label>跳至<input v-model="targetPage" type="number" inputmode="numeric" min="1" :max="pages" step="1" required :disabled="busy.jobs" aria-label="跳转页码" />页</label>
          <button type="submit" :disabled="busy.jobs">跳转</button>
        </form>
      </div>
    </footer>
  </section>
  <JobDetailDrawer ref="drawer" @rules-changed="loadJobs" />
  <DeliveryDialog :jobs="deliveryJobs" :initial-action="deliveryAction" @close="deliveryJobs = []" @started="deliveryStarted" />
</template>

<style scoped>
.jobs-panel { min-width: 0; scroll-margin-top: 84px; }
.jobs-panel-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 24px 24px 16px; }
.jobs-panel-heading h2 { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; overflow-wrap: anywhere; }
.jobs-panel-heading h2 > span { font-family: var(--font-body); font-size: 14px; font-weight: 400; color: var(--muted); font-variant-numeric: tabular-nums; }
.jobs-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; padding: 0 24px 20px; }
.jobs-toolbar .search-field { flex: 1; min-width: 200px; }
.jobs-toolbar .search-field input { font-size: 14px; min-height: 42px; padding: 8px 0; }
.jobs-toolbar .search-field button { display: grid; place-items: center; width: 32px; min-height: 40px; }
.jobs-toolbar > select { width: 150px; min-height: 44px; }
.clear-task-filter { display: inline-flex; align-items: center; gap: 6px; min-height: 44px; padding: 0 8px; color: var(--accent); font-size: 14px; }
.list-utilities { display: flex; align-items: center; justify-content: space-between; padding: 0 24px 8px; font-size: 12px; color: var(--muted); }
.select-all { display: inline-flex; align-items: center; min-height: 44px; gap: 10px; cursor: pointer; }
.select-all input, .job-selection input { width: 17px; height: 17px; margin: 0; cursor: pointer; }
.select-all input:disabled, .job-selection input:disabled { cursor: not-allowed; }
.delivery-toolbar { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; padding: 12px 24px; background: var(--canvas); border-top: 1px solid var(--line); font-size: 14px; }
.delivery-toolbar > div { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
.cancel-selection { min-height: 44px; color: var(--muted); font-size: 14px; }
.job-item { display: flex; align-items: flex-start; gap: 12px; padding: 24px 24px 18px 14px; border-top: 1px solid var(--line); background: var(--surface); transition: background .16s; }
.job-item.selected { background: #f3f8fd; }
.job-selection { display: grid; place-items: center; flex: 0 0 36px; min-height: 44px; margin-top: -5px; cursor: pointer; }
.job-content { min-width: 0; flex: 1; }
.job-headline { display: flex; align-items: baseline; justify-content: space-between; gap: 20px; }
.job-headline h3 { min-width: 0; font-size: 21px; font-weight: 600; line-height: 1.4; }
.job-title { display: block; padding: 0; color: var(--ink); font: inherit; letter-spacing: -.23px; text-align: left; overflow-wrap: anywhere; }
.job-title:hover { color: var(--accent); }
.salary-text { flex-shrink: 0; color: var(--accent); font-size: 21px; font-weight: 600; letter-spacing: -.3px; font-variant-numeric: tabular-nums; }
.job-meta { display: flex; flex-wrap: wrap; gap: 8px 18px; margin-top: 10px; color: var(--muted); font-size: 14px; line-height: 1.6; }
.job-meta > span { display: inline-flex; align-items: center; gap: 6px; overflow-wrap: anywhere; }
.job-meta svg { flex-shrink: 0; }
.company-line { color: #515154; }
.job-summary { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; margin-top: 16px; color: #515154; font-size: 17px; line-height: 1.7; overflow-wrap: anywhere; }
.job-tags { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
.job-tags > span { max-width: 100%; padding: 4px 10px; border-radius: 5px; background: var(--canvas); color: var(--muted); font-size: 12px; line-height: 1.5; overflow-wrap: anywhere; }
.job-bottom { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-top: 8px; }
.job-source { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; color: var(--muted); font-size: 12px; line-height: 1.6; }
.job-source .blocked-label { color: #995415; }
.detail-action { display: inline-flex; align-items: center; justify-content: flex-end; gap: 6px; flex-shrink: 0; min-height: 44px; padding: 0; color: var(--accent); font-size: 14px; }
.table-footer { flex-wrap: wrap; gap: 12px; background: var(--surface); }
.jobs-pagination { display: flex; align-items: center; justify-content: flex-end; flex-wrap: wrap; gap: 12px; max-width: 100%; margin-left: auto; }
.page-total { white-space: nowrap; font-variant-numeric: tabular-nums; }
.page-jump { display: flex; align-items: center; gap: 8px; margin: 0; }
.page-jump label { display: flex; align-items: center; gap: 8px; white-space: nowrap; }
.page-jump input[type='number'] { width: 76px; min-height: 44px; padding: 8px 10px; text-align: center; font-variant-numeric: tabular-nums; }
.page-jump button { min-height: 44px; padding: 8px 14px; border: 1px solid var(--line); border-radius: 11px; color: var(--accent); font-size: 14px; }
.page-jump button:hover:not(:disabled) { background: #eaf3fc; }
@media (max-width: 700px) {
  .jobs-pagination { flex-basis: 100%; justify-content: flex-start; margin-left: 0; }
  .jobs-panel-heading { padding: 20px 16px 16px; }
  .jobs-toolbar { gap: 10px; padding: 0 16px 12px; }
  .jobs-toolbar .search-field { flex-basis: 100%; }
  .jobs-toolbar > select { flex: 1; width: calc(50% - 5px); }
  .list-utilities { padding: 0 16px 8px; }
  .job-item { gap: 4px; padding: 20px 16px 14px 6px; }
  .job-headline { flex-direction: column; gap: 7px; }
  .job-headline h3, .salary-text { font-size: 19px; }
  .job-meta { gap: 6px 12px; }
  .job-meta .company-line { flex-basis: 100%; }
  .job-summary { font-size: 15px; margin-top: 12px; }
  .delivery-toolbar { padding: 12px 16px; }
}
</style>
