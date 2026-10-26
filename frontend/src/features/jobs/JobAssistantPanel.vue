<script setup>
import { ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { request, post } from '../../api'
import { useWorkspace } from '../../stores/workspace'
import { time } from '../../utils/format'
const props = defineProps({ job: { type: Object, required: true } })
const emit = defineEmits(['close', 'rules-changed'])
const { notify, copyText, isActive } = useWorkspace()
const data = ref(null)
const loading = ref(false)
const saving = ref(false)
const generating = ref(false)
const generatedModel = ref('')
const blocking = ref(false)
const text = ref('')
const savedText = ref('')
const errorText = ref('')
const labels = { match: '符合', partial: '部分符合', gap: '存在差异', unknown: '待确认' }
let version = 0
async function load() {
  const current = ++version
  const id = props.job.id
  loading.value = true
  data.value = null
  text.value = ''
  savedText.value = ''
  errorText.value = ''
  generating.value = false
  generatedModel.value = ''
  try {
    const result = await request(`/jobs/${id}/assistant`)
    if (current !== version) return
    data.value = result
    text.value = result.draft?.text ?? result.generated_text
    savedText.value = result.draft?.text ?? ''
  } catch (e) { if (current === version) errorText.value = e.message }
  finally { if (current === version) loading.value = false }
}
watch(() => props.job.id, load, { immediate: true })
async function generate() {
  if (generating.value || saving.value) return
  const current = version
  const id = props.job.id
  generating.value = true
  try {
    const result = await post(`/jobs/${id}/greeting/generate`, undefined, { timeout: 75000 })
    if (current !== version || !data.value) return
    text.value = result.text
    data.value.generated_text = result.text
    generatedModel.value = result.model
    notify('AI 招呼语已生成，请预览并核对内容')
  } catch (error) { if (current === version) notify(error.message, 'error') }
  finally { if (current === version) generating.value = false }
}
async function save() {
  if (saving.value || generating.value) return
  const id = props.job.id
  const current = version
  saving.value = true
  try {
    const draft = await post(`/jobs/${id}/greeting`, { text: text.value })
    if (current === version && data.value) { data.value.draft = draft; savedText.value = draft.text; text.value = draft.text }
    notify('招呼语草稿已保存，尚未发送')
  } catch (e) { notify(e.message, 'error') }
  finally { saving.value = false }
}
async function blockCompany() {
  if (blocking.value || isActive.value) return
  const job = props.job
  const current = version
  blocking.value = true
  try {
    const rule = await post('/assistant/blacklist', { kind: 'company', value: job.company, company: '', platform: '', enabled: true, reason: `从岗位「${job.title}」手动加入` .slice(0, 500) })
    if (current === version && data.value) data.value.blacklist_hits.push(rule)
    emit('rules-changed')
    notify('公司已加入全部平台黑名单，后续投递会拦截')
  } catch (e) { notify(e.message, 'error') }
  finally { blocking.value = false }
}
</script>

<template>
  <section class="job-assistant" aria-label="岗位匹配与打招呼语">
    <p v-if="loading" role="status">正在读取匹配依据与草稿…</p>
    <div v-else-if="errorText" role="alert"><p>{{ errorText }}</p><button class="button button-white" @click="load">重新读取</button></div>
    <template v-else-if="data">
      <div class="match-header"><div><span class="eyebrow">岗位匹配 · 规则分析</span><h3>{{ data.analysis.score === null ? '资料不足' : `${data.analysis.score} 分` }}<small v-if="data.analysis.score !== null">参考分</small></h3></div><RouterLink to="/assistant" @click="emit('close')">编辑求职资料 →</RouterLink></div>
      <p class="explanation">{{ data.analysis.notice }}</p>
      <div class="coverage"><span>可判断条件的权重覆盖度</span><strong>{{ data.analysis.coverage }}%</strong><progress :value="data.analysis.coverage" max="100" aria-label="匹配信息覆盖度" /></div>
      <div v-for="item in data.analysis.items" :key="item.label" class="evidence-row">
        <div class="evidence-title"><strong>{{ item.label }}</strong><span :class="['match-state', item.status]">{{ labels[item.status] }}</span></div>
        <blockquote>{{ item.evidence }}</blockquote><p>{{ item.explanation }}</p><small>权重 {{ item.weight }}%{{ item.status === 'unknown' ? ' · 本项不计分' : '' }}</small>
      </div>
      <div class="greeting-editor">
        <h3>打招呼语预览</h3><p>AI 生成会将职位信息和已填写的求职资料交给 MiniMax 撰写招呼语。请核对真实情况后使用；生成、保存和复制均不会发送到招聘平台。发送请在职位列表选择“发送消息”。</p>
        <p v-if="generating" role="status">{{ data.ai?.model || 'MiniMax-M3' }} 正在生成招呼语…</p>
        <p v-else-if="generatedModel">本次内容由 {{ generatedModel }} 生成，可继续编辑。</p>
        <label for="greeting-draft">可编辑草稿</label><textarea id="greeting-draft" v-model="text" maxlength="1000" rows="7" :disabled="saving || generating" />
        <div class="draft-meta"><span>{{ text.length }}/1000 字</span><span>{{ text === savedText && savedText ? '已保存' : '尚未保存当前内容' }}</span></div>
        <small v-if="data.draft">上次保存 {{ time(data.draft.updated_at, true) }}；已存草稿不会随资料变化自动覆盖。</small>
        <div class="actions"><button class="button button-primary" :disabled="saving || generating || !data.ai?.configured" @click="generate">{{ generating ? 'AI 正在生成…' : 'AI 生成招呼语' }}</button><button class="button button-white" :disabled="saving || generating || !text.trim()" @click="save">{{ saving ? '正在保存…' : '保存草稿' }}</button><button class="button button-white" :disabled="!text.trim() || generating" @click="copyText(text)">复制招呼语</button><button class="button button-white" :disabled="saving || generating" @click="text = data.generated_text">恢复本次生成内容</button></div>
        <p v-if="!data.ai?.configured">后端配置 MiniMax 密钥并重启后，可使用 AI 生成功能。</p>
      </div>
      <div class="blacklist-section">
        <h3>投递黑名单</h3>
        <div v-if="data.blacklist_hits.length" class="blocked-notice" role="status"><strong>已拦截投递</strong><p v-for="rule in data.blacklist_hits" :key="rule.id">命中「{{ rule.value }}」{{ rule.reason ? `：${rule.reason}` : '' }}</p></div>
        <p v-else>当前未命中黑名单。添加公司规则后，各平台同名公司的岗位都会拦截投递，已有岗位数据会保留。</p>
        <div class="actions"><button class="button button-white" :disabled="!job.company || job.company.length > 200 || blocking || isActive || data.blacklist_hits.some(r => r.kind === 'company' && !r.platform)" @click="blockCompany">{{ blocking ? '正在添加…' : '将公司加入黑名单' }}</button><RouterLink class="button button-white" to="/assistant" @click="emit('close')">管理全部规则</RouterLink></div>
        <p v-if="isActive">任务执行期间不能修改黑名单。</p>
      </div>
    </template>
  </section>
</template>

<style scoped>
.job-assistant { padding-top: 22px; color: #46566f; }
.match-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.eyebrow { color: #76839a; font-size: 12px; }
.match-header h3 { font-size: 32px; margin-top: 7px; font-variant-numeric: tabular-nums; color: #6655be; }
.match-header small { font-size: 12px; margin-left: 10px; color: #7a8497; font-weight: 400; }
a { color: #6d5ac1; font-size: 12px; }
p { font-size: 12px; line-height: 1.9; margin: 10px 0; color: #728098; }
.coverage { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 9px; font-size: 12px; margin: 20px 0; }
progress { width: 100%; height: 6px; accent-color: #7663d7; }
.evidence-row { padding: 17px 0; border-top: 1px solid #e8ebf3; }
.evidence-title { display: flex; justify-content: space-between; align-items: center; font-size: 13px; }
.match-state { padding: 4px 8px; border-radius: 4px; font-size: 11px; background: #f0f2f6; color: #68778f; }
.match-state.match { background: #eaf5ef; color: #307052; }
.match-state.partial { background: #fff5dc; color: #8b6322; }
.match-state.gap { background: #fcefed; color: #ad5147; }
blockquote { margin: 12px 0 0; border-left: 3px solid #dcd6f3; padding: 8px 12px; background: #faf9fd; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 12px; line-height: 1.8; }
small { color: #7b889d; font-size: 11px; line-height: 1.8; }
.greeting-editor, .blacklist-section { border-top: 2px solid #e7e3f4; margin-top: 20px; padding-top: 22px; }
h3 { font-size: 16px; }
label { display: block; font-size: 12px; margin: 14px 0 8px; }
textarea { width: 100%; border: 1px solid #ded9ef; border-radius: 7px; resize: vertical; padding: 12px; font: inherit; font-size: 13px; line-height: 1.9; }
.draft-meta { display: flex; justify-content: space-between; margin: 8px 0; color: #7b889d; font-size: 11px; }
.actions { display: flex; flex-wrap: wrap; gap: 9px; margin-top: 16px; }
.actions .button { font-size: 12px; min-height: 40px; }
.blocked-notice { background: #fff3e4; border-left: 3px solid #d59231; padding: 12px; margin-top: 14px; font-size: 13px; }
</style>
