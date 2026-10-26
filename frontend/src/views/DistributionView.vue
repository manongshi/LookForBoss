<script setup>
import { computed, onActivated, onDeactivated, reactive, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { RefreshCw, ArrowUpRight, ArrowDownUp, BarChart3 } from 'lucide-vue-next'
import PageHeading from '../layouts/PageHeading.vue'
import { request } from '../api'
import { useWorkspace } from '../stores/workspace'
import { platformName, platformNames } from '../constants/platforms'
import { number, time } from '../utils/format'
const { dbConnected } = useWorkspace()
const query = reactive({ q: '', city: '', platform: '' })
const applied = ref({ ...query })
const data = ref(null)
const cityOptions = ref([])
const loading = ref(false)
const error = ref('')
const active = ref(false)
const sortKey = ref('count')
const descending = ref(true)
let version = 0
const money = value => value == null ? '—' : `${number(value)}K`
const percent = (count, total) => total ? `${(count / total * 100).toFixed(1)}%` : '0%'
const width = (count, items) => `${count / Math.max(1, ...items.map(i => i.count)) * 100}%`
const topCities = computed(() => data.value?.cities.slice(0, 12) || [])
const sortedCities = computed(() => [...(data.value?.cities || [])].sort((a, b) => {
  const key = sortKey.value
  if (a[key] == null) return b[key] == null ? 0 : 1
  if (b[key] == null) return -1
  const comparison = key === 'name' ? a.name.localeCompare(b.name, 'zh-CN') : a[key] - b[key]
  return comparison * (descending.value ? -1 : 1)
}))
const hasFilters = computed(() => Object.values(applied.value).some(Boolean))
function sort(key) { if (sortKey.value === key) descending.value = !descending.value; else { sortKey.value = key; descending.value = key !== 'name' } }
function ariaSort(key) { return sortKey.value === key ? (descending.value ? 'descending' : 'ascending') : 'none' }
function jobsLink(city = applied.value.city) { return { name: 'jobs', query: { ...applied.value, city } } }
async function load() {
  if (!active.value) return
  const current = ++version
  const filters = { ...query, q: query.q.trim() }
  loading.value = true
  error.value = ''
  try {
    const result = await request(`/analytics/jobs?${new URLSearchParams(filters)}`)
    if (current !== version) return
    data.value = result
    applied.value = filters
    cityOptions.value = result.city_options
  } catch (e) { if (current === version) { error.value = e.message; data.value = null } }
  finally { if (current === version) loading.value = false }
}
function reset() { Object.assign(query, { q: '', city: '', platform: '' }); load() }
function filterCity(name) { if (name === '地区未标注') return; query.city = name; load() }
function filterPlatform(name) { query.platform = name; load() }
onActivated(() => { active.value = true; load() })
onDeactivated(() => { active.value = false; version++; loading.value = false })
watch(dbConnected, (connected) => { if (connected && active.value) load() })
</script>

<template>
  <div class="distribution-page">
    <PageHeading><button class="button button-white" :disabled="loading" @click="load"><RefreshCw :size="15" :class="{ spin: loading }" />刷新统计</button></PageHeading>
    <form class="panel distribution-filters" @submit.prevent="load">
      <label class="keyword-filter">岗位 / 公司<input v-model="query.q" maxlength="100" placeholder="例如：前端、Java、公司名称" /></label>
      <label>招聘平台<select v-model="query.platform"><option value="">全部平台</option><option v-for="(name, id) in platformNames" :key="id" :value="id">{{ name }}</option></select></label>
      <label>采集城市<select v-model="query.city"><option value="">全部城市</option><option v-for="city in cityOptions" :key="city" :value="city">{{ city }}</option></select></label>
      <div class="filter-actions"><button class="button button-primary" :disabled="loading">{{ loading ? '正在统计…' : '查看分布' }}</button><button type="button" class="button button-white" :disabled="loading" @click="reset">重置</button></div>
    </form>
    <p class="method-note">统计对象为已采集的岗位记录，各平台记录分别计数，尚未跨平台合并。地区按记录中的城市字段分组；薪资仅比较可识别的月薪，不含年终奖和多薪折算。</p>
    <p v-if="loading" class="loading-note" role="status">正在读取全部符合条件的岗位，更新下方统计…</p>
    <div v-if="error" class="panel state-panel" role="alert"><h2>暂时无法读取统计</h2><p>{{ error }}</p><button class="button button-white" @click="load">重新读取</button></div>
    <template v-if="data">
      <div class="scope-line"><span>当前范围：{{ applied.q || '全部岗位' }} · {{ applied.platform ? platformName(applied.platform) : '全部平台' }} · {{ applied.city || '全部城市' }}</span><span v-if="data.latest">最近采集 {{ time(data.latest, true) }}</span></div>
      <div v-if="!data.total" class="panel state-panel"><BarChart3 :size="32" /><h2>{{ hasFilters ? '这个范围还没有岗位数据' : '采集岗位后，这里会显示分布' }}</h2><p>{{ hasFilters ? '可以清空筛选条件，再查看全部已采集岗位。' : '先在工作台采集感兴趣的岗位，再比较不同地区和薪资区间。' }}</p><button v-if="hasFilters" class="button button-white" :disabled="loading" @click="reset">查看全部分布</button><RouterLink v-else class="button button-primary" to="/workbench">前往采集</RouterLink></div>
      <div v-else :aria-busy="loading" :class="{ updating: loading }">
        <div class="summary-grid">
          <article class="panel summary-card"><span>岗位记录</span><strong>{{ number(data.total) }}<small>条</small></strong><p>分布在 {{ number(data.city_count) }} 个地区分组</p></article>
          <article class="panel summary-card"><span>可比较月薪</span><strong>{{ number(data.salary_count) }}<small>条</small></strong><p>占当前岗位 {{ percent(data.salary_count, data.total) }}</p></article>
          <article class="panel summary-card"><span>薪资中点均值</span><strong>{{ money(data.mean) }}</strong><p>每条薪资区间取中点后求平均</p></article>
          <article class="panel summary-card"><span>薪资中点中位数</span><strong>{{ money(data.median) }}</strong><p>不是实际录用薪资或市场平均工资</p></article>
        </div>
        <div class="chart-grid">
          <section class="panel chart-panel" aria-labelledby="salary-heading">
            <header><div><h2 id="salary-heading">薪资分布</h2><p>月薪区间中点 · 单位 K / 月</p></div><span class="sample-label">{{ data.salary_count }} 条样本</span></header>
            <div v-if="data.salary_count" class="bar-list">
              <div v-for="bucket in data.salary_buckets" :key="bucket.name" class="bar-row"><span class="bar-label">{{ bucket.name }}</span><div class="bar-track"><span class="bar-fill salary-fill" :style="{ width: width(bucket.count, data.salary_buckets) }"></span></div><strong>{{ number(bucket.count) }}</strong><small>{{ percent(bucket.count, data.salary_count) }}</small></div>
            </div>
            <p v-else class="chart-empty">当前没有可比较的月薪记录，其他薪资口径见下方说明。</p>
            <p class="chart-footnote">例如 10–20K 按中点 15K 归入 15–20K 档；各档含下限、不含上限。</p>
          </section>
          <section class="panel chart-panel" aria-labelledby="city-heading">
            <header><div><h2 id="city-heading">地区岗位排行</h2><p>展示数量最多的 12 个地区，点击可筛选</p></div><span class="sample-label">{{ data.city_count }} 个分组</span></header>
            <div class="bar-list"><button v-for="city in topCities" :key="city.name" class="bar-row city-button" :disabled="loading || city.name === '地区未标注'" :aria-label="`${city.name}，${city.count} 条岗位，点击筛选`" @click="filterCity(city.name)"><span class="bar-label">{{ city.name }}</span><div class="bar-track"><span class="bar-fill city-fill" :style="{ width: width(city.count, topCities) }"></span></div><strong>{{ number(city.count) }}</strong><small>{{ percent(city.count, data.total) }}</small></button></div>
          </section>
          <section class="panel chart-panel" aria-labelledby="platform-heading">
            <header><div><h2 id="platform-heading">平台分布</h2><p>点击平台查看它的地区与薪资分布</p></div></header>
            <div class="bar-list"><button v-for="item in data.platforms" :key="item.name" class="bar-row city-button" :disabled="loading" @click="filterPlatform(item.name)"><span class="bar-label">{{ platformName(item.name) }}</span><div class="bar-track"><span class="bar-fill platform-fill" :style="{ width: width(item.count, data.platforms) }"></span></div><strong>{{ number(item.count) }}</strong><small>{{ percent(item.count, data.total) }}</small></button></div>
          </section>
          <section class="panel chart-panel" aria-labelledby="experience-heading">
            <header><div><h2 id="experience-heading">经验要求分布</h2><p>保留平台原始要求，展示数量前 8 项</p></div></header>
            <div class="bar-list"><div v-for="item in data.experience.slice(0, 8)" :key="item.name" class="bar-row"><span class="bar-label">{{ item.name }}</span><div class="bar-track"><span class="bar-fill experience-fill" :style="{ width: width(item.count, data.experience) }"></span></div><strong>{{ number(item.count) }}</strong><small>{{ percent(item.count, data.total) }}</small></div></div>
          </section>
        </div>
        <section class="panel regional-table">
          <header><div><h2>地区薪资明细</h2><p>点击列名排序；点击“查看岗位”打开对应地区的岗位列表。</p></div><RouterLink class="button button-white compact" :to="jobsLink()">查看当前范围全部岗位<ArrowUpRight :size="14" /></RouterLink></header>
          <div class="table-scroll"><table><thead><tr><th v-for="column in [{ key: 'name', label: '地区' }, { key: 'count', label: '岗位数量' }, { key: 'salary_count', label: '月薪样本' }, { key: 'mean', label: '中点均值' }, { key: 'median', label: '中点中位数' }]" :key="column.key" :aria-sort="ariaSort(column.key)"><button @click="sort(column.key)">{{ column.label }}<ArrowDownUp :size="13" /><span v-if="sortKey === column.key">{{ descending ? '↓' : '↑' }}</span></button></th><th>岗位占比</th><th>操作</th></tr></thead><tbody><tr v-for="city in sortedCities" :key="city.name"><td><strong>{{ city.name }}</strong></td><td>{{ number(city.count) }}</td><td>{{ number(city.salary_count) }}<small v-if="city.salary_count > 0 && city.salary_count < 5" class="small-sample">样本较少</small></td><td class="salary-cell">{{ money(city.mean) }}</td><td class="salary-cell">{{ money(city.median) }}</td><td>{{ percent(city.count, data.total) }}</td><td><RouterLink v-if="city.name !== '地区未标注'" class="detail-link" :to="jobsLink(city.name)">查看岗位<ArrowUpRight :size="14" /></RouterLink><span v-else>地区待补全</span></td></tr></tbody></table></div>
        </section>
        <section class="calculation-note"><strong>薪资统计口径</strong><p>只使用可识别的月薪数值或区间；K、千视为月薪单位，万元等口径需明确标注按月。13 薪、14 薪等不计入月薪。平均值和中位数均基于区间中点，只反映已采集样本。</p><div v-if="data.excluded.length" class="excluded-list"><span v-for="item in data.excluded" :key="item.name">{{ item.name }}：<b>{{ number(item.count) }}</b> 条未参与薪资计算</span></div><p v-else>当前全部岗位均可参与月薪统计。</p></section>
      </div>
    </template>
  </div>
</template>

<style scoped>
.distribution-page { --chart-purple: #7663d7; --chart-teal: #419c91; --chart-blue: #668fca; --chart-amber: #c99a54; --chart-ink: #35465f; --chart-muted: #76839a; color: var(--chart-ink); }
.distribution-filters { display: flex; align-items: end; flex-wrap: wrap; gap: 16px; padding: 22px; }
.distribution-filters label { display: grid; gap: 8px; min-width: 155px; flex: 1; font-size: 12px; }
.distribution-filters .keyword-filter { flex: 2; min-width: 220px; }
.distribution-filters input, .distribution-filters select { width: 100%; min-height: 42px; font-size: 13px; }
.filter-actions { display: flex; gap: 9px; }
.filter-actions .button { min-height: 42px; }
.method-note { font-size: 12px; line-height: 1.9; color: var(--chart-muted); margin: 14px 0 20px; }
.scope-line { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 9px; font-size: 12px; color: var(--chart-muted); margin: 0 0 16px; }
.summary-grid { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 18px; margin-bottom: 22px; }
.summary-card { padding: 23px; border-top: 3px solid #e0dbf5; }
.summary-card > span { font-size: 12px; color: var(--chart-muted); }
.summary-card > strong { display: block; font-size: 30px; font-weight: 600; letter-spacing: -.6px; margin: 14px 0 12px; font-variant-numeric: tabular-nums; }
.summary-card strong small { font-size: 12px; color: var(--chart-muted); font-weight: 400; margin-left: 8px; }
.summary-card p { font-size: 11px; color: var(--chart-muted); line-height: 1.7; }
.chart-grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 22px; align-items: start; }
.chart-panel { padding: 24px; }
header { display: flex; align-items: start; justify-content: space-between; gap: 16px; margin-bottom: 22px; flex-wrap: wrap; }
h2 { font-size: 16px; font-weight: 600; }
header p { font-size: 12px; color: var(--chart-muted); line-height: 1.8; margin-top: 6px; }
.sample-label { font-size: 11px; background: #f1eff9; padding: 5px 8px; border-radius: 4px; color: #7d70b0; white-space: nowrap; }
.bar-list { display: grid; gap: 17px; }
.bar-row { display: grid; grid-template-columns: 88px minmax(30px,1fr) 42px 48px; align-items: center; gap: 10px; font-size: 12px; width: 100%; text-align: left; }
.bar-label { line-height: 1.6; overflow-wrap: anywhere; }
.bar-row strong, .bar-row small { text-align: right; font-variant-numeric: tabular-nums; font-weight: 500; }
.bar-row small { color: var(--chart-muted); font-size: 10px; }
.bar-track { height: 12px; background: #f1f3f8; border-radius: 3px; overflow: hidden; }
.bar-fill { display: block; height: 100%; border-radius: 3px; }
.salary-fill { background: var(--chart-purple); }.city-fill { background: var(--chart-teal); }.platform-fill { background: var(--chart-blue); }.experience-fill { background: var(--chart-amber); }
.city-button { padding: 4px 0; border-radius: 4px; }
.city-button:hover:not(:disabled) { background: #f6f8fc; color: #5363ad; }
.city-button:disabled { opacity: 1; }
.chart-footnote { font-size: 11px; color: var(--chart-muted); line-height: 1.8; margin-top: 24px; border-top: 1px solid #edf0f5; padding-top: 13px; }
.chart-empty { font-size: 13px; color: var(--chart-muted); padding: 35px 0; line-height: 1.8; }
.regional-table { margin-top: 22px; overflow: hidden; }
.regional-table header { padding: 24px 24px 0; }
table { width: 100%; min-width: 690px; border-collapse: collapse; font-size: 13px; }
th, td { padding: 16px 22px; text-align: left; border-bottom: 1px solid #edf0f5; }
th { background: #f8f9fc; color: var(--chart-muted); font-size: 12px; font-weight: 500; }
th button { display: flex; align-items: center; gap: 6px; padding: 0; }
td { font-variant-numeric: tabular-nums; }
.small-sample { display: block; color: #9a792f; font-size: 10px; margin-top: 4px; }
.salary-cell { color: #7563bf; font-weight: 600; }
.detail-link { display: inline-flex; align-items: center; gap: 5px; color: #6d5db9; font-size: 12px; }
.calculation-note { padding: 22px 2px; font-size: 12px; color: var(--chart-muted); line-height: 1.9; }
.calculation-note > strong { color: var(--chart-ink); }
.calculation-note p { margin-top: 6px; }
.excluded-list { display: flex; flex-wrap: wrap; gap: 8px 20px; margin-top: 10px; }
.excluded-list span { background: #edf0f6; border-radius: 4px; padding: 6px 10px; }
.state-panel { padding: 45px 24px; display: flex; flex-direction: column; align-items: center; gap: 16px; text-align: center; }
.state-panel p { font-size: 13px; color: var(--chart-muted); line-height: 1.8; }
.loading-note { font-size: 13px; color: #6d5db9; padding: 12px; margin-bottom: 16px; background: #efecfa; border-radius: 6px; }
.updating { opacity: .6; pointer-events: none; }
@media(max-width: 1200px) { .summary-grid { grid-template-columns: repeat(2,minmax(0,1fr)); } .chart-grid { grid-template-columns: 1fr; } }
@media(max-width: 600px) { .distribution-filters { padding: 17px; } .distribution-filters label, .distribution-filters .keyword-filter { min-width: 100%; } .summary-grid { gap: 12px; } .summary-card { padding: 17px; } .summary-card > strong { font-size: 25px; } .chart-panel { padding: 18px; } .bar-row { grid-template-columns: 72px minmax(25px,1fr) 32px 43px; gap: 7px; } .bar-list { gap: 14px; } }
</style>
