<script setup>
import { onActivated, onMounted, reactive, ref } from 'vue'
import PageHeading from '../layouts/PageHeading.vue'
import { request, post } from '../api'
import { useWorkspace } from '../stores/workspace'
import { platformNames, platformName } from '../constants/platforms'
const { notify, isActive } = useWorkspace()
const loaded = ref(false)
const loading = ref(false)
const saving = ref(false)
const mutating = ref(false)
const rules = ref([])
const editing = ref('')
const deleting = ref('')
const filter = ref('')
const profile = reactive({ introduction: '', skills: '', roles: '', cities: '', years: null, degree: '', salary_min: null })
const emptyRule = () => ({ kind: 'company', value: '', company: '', platform: '', reason: '', enabled: true })
const rule = reactive(emptyRule())
const kinds = { company: '公司名称', title: '岗位关键词', recruiter: '招聘者姓名' }
const split = value => [...new Set(value.split(/[,，、\n]/).map(s => s.trim()).filter(Boolean))]
async function load() {
  loading.value = true
  try {
    const [p, r] = await Promise.all([request('/assistant/profile'), request('/assistant/blacklist')])
    Object.assign(profile, p, { skills: p.skills.join('、'), roles: p.roles.join('、'), cities: p.cities.join('、') })
    rules.value = r
    loaded.value = true
  } catch (e) { notify(e.message, 'error') }
  finally { loading.value = false }
}
onMounted(load)
onActivated(async () => {
  if (!loaded.value || mutating.value) return
  try { rules.value = await request('/assistant/blacklist') }
  catch (e) { notify(e.message, 'error') }
})
async function saveProfile() {
  saving.value = true
  try {
    await post('/assistant/profile', { ...profile, skills: split(profile.skills), roles: split(profile.roles), cities: split(profile.cities), years: profile.years === '' ? null : profile.years, salary_min: profile.salary_min === '' ? null : profile.salary_min })
    notify('个人资料已保存，重新打开岗位匹配即可按新资料分析')
  } catch (e) { notify(e.message, 'error') }
  finally { saving.value = false }
}
function resetRule() { editing.value = ''; Object.assign(rule, emptyRule()) }
function edit(item) { editing.value = item.id; Object.assign(rule, item); document.getElementById('rule-editor')?.scrollIntoView({ behavior: 'auto', block: 'center' }) }
async function saveRule() {
  if (mutating.value || isActive.value) return
  mutating.value = true
  try {
    const saved = await post('/assistant/blacklist' + (editing.value ? `/${editing.value}` : ''), rule)
    rules.value = [saved, ...rules.value.filter(r => r.id !== saved.id)]
    resetRule()
    notify('黑名单规则已保存')
  } catch (e) { notify(e.message, 'error') }
  finally { mutating.value = false }
}
async function toggle(item) {
  mutating.value = true
  try {
    const updated = await post(`/assistant/blacklist/${item.id}`, { ...item, enabled: !item.enabled })
    rules.value = rules.value.map(r => r.id === item.id ? updated : r)
    if (editing.value === item.id) rule.enabled = updated.enabled
  } catch (e) { notify(e.message, 'error') }
  finally { mutating.value = false }
}
async function remove(item) {
  mutating.value = true
  try {
    await post(`/assistant/blacklist/${item.id}/delete`)
    rules.value = rules.value.filter(r => r.id !== item.id)
    if (editing.value === item.id) resetRule()
    deleting.value = ''
    notify('规则已删除')
  } catch (e) { notify(e.message, 'error') }
  finally { mutating.value = false }
}
</script>

<template>
  <div class="assistant-page">
    <PageHeading />
    <div class="assistant-intro"><strong>先填写真实经历，再看岗位是否适合。</strong><p>匹配依据与打招呼语在「岗位数据库 → 匹配 / 招呼语」中查看。资料用于岗位匹配分析，预览内容不会自动发送。</p></div>
    <div v-if="!loaded" class="panel assistant-card" role="status">{{ loading ? '正在读取个人资料和黑名单…' : '读取失败，请重试后再编辑。' }}<button v-if="!loading" class="button button-white" @click="load">重新读取</button></div>
    <template v-else>
      <section class="panel assistant-card">
        <header><div><h2>我的求职资料</h2><p>未填写的条件标记为待确认，不计入匹配参考分。</p></div></header>
        <form class="profile-form" @submit.prevent="saveProfile">
          <label class="wide">个人简介<textarea v-model="profile.introduction" maxlength="2000" rows="4" placeholder="填写可核实的经历或优势，生成招呼语时会直接引用。不要填写身份证号等无关信息。" /></label>
          <label class="wide">已有技能<input v-model="profile.skills" placeholder="例如：Java、Spring Boot、MySQL；多项用顿号或逗号分隔" /></label>
          <label>目标岗位<input v-model="profile.roles" placeholder="例如：Java开发、后端开发" /></label>
          <label>意向城市<input v-model="profile.cities" placeholder="例如：昆明、成都" /></label>
          <label>工作年限<input v-model.number="profile.years" type="number" min="0" max="60" step="0.5" placeholder="未填写" /></label>
          <label>最高学历<select v-model="profile.degree"><option value="">未填写</option><option v-for="d in ['高中','中专','大专','本科','硕士','博士']" :key="d">{{ d }}</option></select></label>
          <label>税前月薪底线（K）<input v-model.number="profile.salary_min" type="number" min="0.1" max="1000" step="0.1" placeholder="例如 15，即 15000 元 / 月" /></label>
          <div class="form-footer wide"><span>技能比对按关键词进行，无法完整理解语义；参考分不代表录用概率。</span><button class="button button-primary" :disabled="saving">{{ saving ? '正在保存…' : '保存求职资料' }}</button></div>
        </form>
      </section>
      <section class="panel assistant-card">
        <header><div><h2>手动管理黑名单 <small>{{ rules.length }} 条</small></h2><p>命中规则的岗位保留在数据库，但会拦截投递。公司按完整名称匹配，岗位按关键词匹配，招聘者按姓名和所属公司共同匹配。</p></div></header>
        <p v-if="isActive" class="attention" role="status">任务执行期间暂停修改黑名单，请先停止当前任务。</p>
        <form id="rule-editor" class="rule-form" @submit.prevent="saveRule">
          <fieldset :disabled="isActive || mutating">
            <legend>{{ editing ? '编辑规则' : '新增规则' }}</legend>
            <div class="rule-fields">
              <label>规则类型<select v-model="rule.kind"><option v-for="(name, value) in kinds" :key="value" :value="value">{{ name }}</option></select></label>
              <label>适用平台<select v-model="rule.platform"><option value="">全部平台</option><option v-for="(name, id) in platformNames" :key="id" :value="id">{{ name }}</option></select></label>
              <label>{{ kinds[rule.kind] }}<input v-model="rule.value" required maxlength="200" :placeholder="rule.kind === 'company' ? '填写采集记录中的完整公司名称' : '输入匹配内容'" /></label>
              <label v-if="rule.kind === 'recruiter'">所属公司<input v-model="rule.company" required maxlength="200" placeholder="完整公司名称，避免误拦同名招聘者" /></label>
              <label class="wide">备注<input v-model="rule.reason" maxlength="500" placeholder="例如：已沟通过，暂不考虑" /></label>
            </div>
            <div class="form-footer"><label class="check"><input v-model="rule.enabled" type="checkbox" />启用规则</label><div class="actions"><button v-if="editing" type="button" class="button button-white" @click="resetRule">取消编辑</button><button class="button button-primary">{{ mutating ? '正在保存…' : editing ? '保存修改' : '添加规则' }}</button></div></div>
          </fieldset>
        </form>
        <label class="filter-label">查找规则<input v-model="filter" placeholder="搜索名称或备注" /></label>
        <p v-if="!rules.length" class="empty-copy">还没有黑名单。可以在这里新增，也可以从岗位详情将公司加入黑名单。</p>
        <div v-for="item in rules.filter(r => (r.value + r.company + r.reason).toLowerCase().includes(filter.toLowerCase()))" :key="item.id" class="rule-row">
          <div><span class="rule-type">{{ kinds[item.kind] }} · {{ item.platform ? platformName(item.platform) : '全部平台' }} · {{ item.enabled ? '已启用' : '已停用' }}</span><h3>{{ item.value }}</h3><p v-if="item.kind === 'recruiter'">所属公司：{{ item.company }}</p><p>{{ item.reason || '未填写备注' }}</p></div>
          <div class="actions"><button class="button button-white compact" :disabled="isActive || mutating" @click="edit(item)">编辑</button><button class="button button-white compact" :disabled="isActive || mutating" @click="toggle(item)">{{ item.enabled ? '停用' : '启用' }}</button><button class="button button-white compact" :disabled="isActive || mutating" @click="deleting = item.id">删除</button></div>
          <div v-if="deleting === item.id" class="delete-confirm" role="alert">删除「{{ item.value }}」规则？<button class="button button-white compact" :disabled="mutating || isActive" @click="remove(item)">确认删除</button><button class="button button-white compact" @click="deleting = ''">取消</button></div>
        </div>
        <p v-if="rules.length && !rules.some(r => (r.value + r.company + r.reason).toLowerCase().includes(filter.toLowerCase()))" class="empty-copy">没有匹配的规则，试试其他关键词。</p>
      </section>
    </template>
  </div>
</template>

<style scoped>
.assistant-page { --ink: #354660; --muted: #728097; --lavender: #7663d7; --line-soft: #e7eaf2; color: var(--ink); }
.assistant-intro { border-left: 4px solid var(--lavender); padding: 8px 20px; margin-bottom: 24px; }
.assistant-intro strong { font-size: 20px; font-weight: 600; }
.assistant-intro p, header p { margin-top: 8px; color: var(--muted); line-height: 1.8; font-size: 13px; }
.assistant-card { padding: 28px; margin-bottom: 24px; }
header { margin-bottom: 24px; }
h2 { font-size: 18px; } h2 small { color: var(--muted); font-size: 13px; font-weight: 400; margin-left: 10px; }
.profile-form, .rule-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }
label { display: grid; gap: 9px; font-size: 13px; line-height: 1.6; }
input, select, textarea { width: 100%; min-height: 42px; font-size: 13px; }
textarea { resize: vertical; padding: 12px; border: 1px solid var(--line-soft); border-radius: 6px; font: inherit; line-height: 1.8; }
.wide { grid-column: 1 / -1; }
.form-footer { display: flex; align-items: center; justify-content: space-between; gap: 18px; flex-wrap: wrap; }
.form-footer > span { font-size: 12px; color: var(--muted); }
.actions { display: flex; flex-wrap: wrap; gap: 8px; }
.rule-form { padding: 20px; background: #f8f9fd; border: 1px solid var(--line-soft); border-radius: 10px; }
fieldset { border: 0; margin: 0; padding: 0; min-width: 0; }
legend { font-weight: 600; margin-bottom: 20px; }
.rule-form .form-footer { margin-top: 20px; }
.check { display: flex; align-items: center; gap: 8px; }
.check input { width: 17px; min-height: 17px; }
.filter-label { max-width: 400px; margin: 24px 0 8px; }
.rule-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 20px 0; border-bottom: 1px solid var(--line-soft); flex-wrap: wrap; }
.rule-row > div:first-child { flex: 1; min-width: 180px; overflow-wrap: anywhere; }
.rule-type { font-size: 11px; color: var(--muted); }
h3 { font-size: 15px; margin-top: 6px; }
.rule-row p, .empty-copy { font-size: 13px; color: var(--muted); line-height: 1.8; margin-top: 8px; }
.attention, .delete-confirm { background: #fff6e5; color: #88591b; padding: 14px; border-radius: 6px; font-size: 13px; margin-bottom: 16px; }
.delete-confirm { width: 100%; display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
@media(max-width: 650px) { .profile-form, .rule-fields { grid-template-columns: 1fr; } .assistant-card { padding: 20px; } .assistant-intro strong { font-size: 17px; } .form-footer .button { min-height: 44px; } }
</style>
