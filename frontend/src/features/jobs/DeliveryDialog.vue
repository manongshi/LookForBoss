<script setup>
import { computed, ref, watch } from 'vue'
import { X, Send, LoaderCircle } from 'lucide-vue-next'
import { useWorkspace } from '../../stores/workspace'
import { useDialog } from '../../composables/useDialog'
import { platformName } from '../../constants/platforms'
import { post, request } from '../../api'
import DeliveryNotice from './DeliveryNotice.vue'

const props = defineProps({
  jobs: { type: Array, default: () => [] },
  initialAction: { type: String, default: 'resume' },
})
const emit = defineEmits(['close', 'started'])
const { startDelivery, busy, isActive, notify } = useWorkspace()
const action = ref('resume')
const confirmed = ref(false)
const messageSource = ref('custom')
const messageTemplate = ref('您好，我对贵公司的{职位}岗位很感兴趣，希望有机会进一步沟通。')
const drafts = ref({})
const loadingDrafts = ref(false)
const draftsError = ref('')
const allowRepeat = ref(false)
let draftVersion = 0
const platform = computed(() => props.jobs[0]?.source || 'boss')
const samePlatform = computed(() => props.jobs.every(job => (job.source || 'boss') === platform.value))
const blocked = computed(() => props.jobs.some(job => job.blacklist_hits?.length))
const visible = computed(() => props.jobs.length > 0)
const messages = computed(() => Object.fromEntries(props.jobs.map(job => [job.id,
  (messageSource.value !== 'custom' ? drafts.value[job.id] || '' : messageTemplate.value.replaceAll('{职位}', job.title).replaceAll('{公司}', job.company || '贵公司')).trim(),
])))
const validMessages = computed(() => Object.values(messages.value).every(value => value.length > 0 && value.length <= 1000))
const canSubmit = computed(() => confirmed.value && samePlatform.value && !blocked.value && props.jobs.length <= 50 && !busy.start && !isActive.value
  && (action.value !== 'message' || (platform.value === 'boss' && validMessages.value && !loadingDrafts.value)))
useDialog(visible, () => { if (!busy.start) emit('close') }, '.delivery-close')
watch(() => props.jobs, () => {
  draftVersion++
  confirmed.value = false
  action.value = props.initialAction === 'message' && platform.value === 'boss' ? 'message' : 'resume'
  allowRepeat.value = false
  messageSource.value = 'custom'
  drafts.value = {}
  draftsError.value = ''
  loadingDrafts.value = false
})
watch([action, messageSource, messageTemplate, allowRepeat, drafts], () => { confirmed.value = false }, { deep: true })
watch(messageSource, source => {
  if (source !== 'custom') loadDrafts()
  else { draftVersion++; loadingDrafts.value = false }
})
async function loadDrafts() {
  const current = ++draftVersion
  const jobs = [...props.jobs]
  const useAI = messageSource.value === 'ai'
  const batchSize = useAI ? 2 : 5
  loadingDrafts.value = true
  draftsError.value = ''
  drafts.value = {}
  const loaded = {}
  let failures = 0
  let firstError = ''
  for (let offset = 0; offset < jobs.length; offset += batchSize) {
    if (current !== draftVersion) return
    const batch = jobs.slice(offset, offset + batchSize)
    const results = await Promise.allSettled(batch.map(job => useAI
      ? post(`/jobs/${job.id}/greeting/generate`, undefined, { timeout: 75000 })
      : request(`/jobs/${job.id}/assistant`)))
    if (current !== draftVersion) return
    results.forEach((result, index) => {
      if (result.status === 'fulfilled') loaded[batch[index].id] = useAI ? result.value.text : result.value.draft?.text ?? result.value.generated_text ?? ''
      else { loaded[batch[index].id] = ''; failures++; firstError ||= result.reason?.message || '服务暂不可用' }
    })
    drafts.value = { ...loaded }
  }
  if (current !== draftVersion) return
  drafts.value = loaded
  loadingDrafts.value = false
  if (failures) draftsError.value = `${failures} 个职位的${useAI ? '招呼语生成失败' : '草稿未能读取'}：${firstError}。可重试或在下方手动填写。`
}
async function submit() {
  if (!canSubmit.value) return
  try {
    await startDelivery(props.jobs.map(job => job.id), action.value, action.value === 'message' ? { ...messages.value } : {}, action.value === 'message' && allowRepeat.value)
    emit('started')
  } catch (error) { notify(error.message, 'error') }
}
</script>

<template>
  <div v-if="visible" class="delivery-overlay" @click.self="!busy.start && emit('close')">
    <section class="delivery-dialog" role="dialog" aria-modal="true" aria-labelledby="delivery-title">
      <header><h2 id="delivery-title">{{ action === 'message' ? '确认发送消息' : '确认投递职位' }}</h2><button class="icon-button delivery-close" aria-label="关闭" :disabled="busy.start" @click="emit('close')"><X :size="20" /></button></header>
      <p>{{ platformName(platform) }} · 已选 {{ jobs.length }} 个职位</p>
      <p v-if="!samePlatform" class="warning" role="alert">请选择同一平台的职位。</p>
      <p v-if="blocked" class="warning" role="alert">所选职位命中黑名单，请取消勾选后重试。</p>
      <p v-if="jobs.length > 50" class="warning" role="alert">一次最多选择 50 个职位。</p>
      <label class="action-label">执行操作
        <select v-model="action" :disabled="busy.start">
          <option value="resume">投递 / 发送平台简历</option>
          <option v-if="['boss', 'liepin'].includes(platform)" value="contact">仅打开沟通</option>
          <option v-if="platform === 'boss'" value="message">发送消息 / 招呼语</option>
        </select>
      </label>
      <template v-if="action === 'message'">
        <label class="action-label">消息来源
          <select v-model="messageSource" :disabled="busy.start">
            <option value="custom">统一消息模板</option>
            <option value="draft">职位招呼语草稿</option>
            <option value="ai">AI 生成（MiniMax-M3）</option>
          </select>
        </label>
        <label v-if="messageSource === 'custom'" class="action-label">消息内容
          <textarea v-model="messageTemplate" :disabled="busy.start" maxlength="1000" rows="4" placeholder="输入要发送的消息，可使用 {职位}、{公司}" />
          <span class="field-help">{职位}、{公司} 会替换为对应内容，逐条发送的最终文本显示在下方。</span>
        </label>
        <p v-else-if="messageSource === 'ai'">将职位信息和已填写的求职资料交给 MiniMax-M3 生成招呼语。请在下方逐条核对真实内容，编辑后再确认发送。</p>
        <p v-else>优先使用已保存草稿，未保存时使用匹配页生成的招呼语。请在下方逐条核对，也可以直接编辑。</p>
        <p v-if="loadingDrafts" role="status">{{ messageSource === 'ai' ? 'MiniMax-M3 正在生成招呼语' : '正在读取招呼语' }}（{{ Object.keys(drafts).length }}/{{ jobs.length }}）…</p>
        <p v-if="draftsError" class="warning" role="alert">{{ draftsError }}<button :disabled="loadingDrafts" @click="loadDrafts">重新读取</button></p>
      </template>
      <ul class="recipient-list">
        <li v-for="job in jobs" :key="job.id">
          <strong>{{ job.title }}</strong><span>{{ job.company }} · {{ job.city }} · {{ job.salary || '薪资未标注' }}</span>
          <template v-if="action === 'message'">
            <textarea v-if="messageSource !== 'custom'" v-model="drafts[job.id]" :aria-label="`${job.company} ${job.title} 的消息内容`" :disabled="busy.start || loadingDrafts" maxlength="1000" rows="4" placeholder="填写发给该职位招聘者的消息" />
            <p v-else class="message-preview">{{ messages[job.id] || '请填写消息内容' }}</p>
            <span class="message-length" :class="{ warning: !messages[job.id] || messages[job.id].length > 1000 }">{{ messages[job.id]?.length || 0 }}/1000 字</span>
          </template>
        </li>
      </ul>
      <template v-if="action === 'message'">
        <label class="consent"><input v-model="allowRepeat" type="checkbox" :disabled="busy.start" /><span>向已经发送过消息的职位再次发送。结果待核对的记录仍须先在官网核对。</span></label>
        <p>程序会进入对应会话、填入上方文本并点击发送，确认新消息出现在本人聊天记录后才记为发送完成。</p>
      </template>
      <template v-else>
        <DeliveryNotice compact />
        <p v-if="action === 'resume'">使用该账号的默认简历。请先在官网核对；若网站要求选择简历或对方同意，请在浏览器完成。</p>
        <p v-else>仅点击官网沟通入口，可能触发平台默认招呼语。需要发文字请选择“发送消息 / 招呼语”。</p>
      </template>
      <label class="consent"><input v-model="confirmed" type="checkbox" :disabled="busy.start || loadingDrafts" /><span>{{ action === 'message' ? '我已核对接收职位、公司、登录账号和逐条消息内容，确认发送。' : '我已核对所选职位、登录账号及执行操作，确认继续。' }}</span></label>
      <footer><button class="button button-white" :disabled="busy.start" @click="emit('close')">取消</button><button class="button button-primary" :disabled="!canSubmit" @click="submit"><LoaderCircle v-if="busy.start" :size="16" class="spin" /><Send v-else :size="16" />{{ busy.start ? '正在创建任务' : action === 'message' ? '确认消息并创建任务' : '确认并创建任务' }}</button></footer>
    </section>
  </div>
</template>

<style scoped>
.delivery-overlay { position: fixed; inset: 0; z-index: 70; background: rgb(0 0 0 / 25%); backdrop-filter: blur(5px); display: grid; place-items: center; padding: 24px; }
.delivery-dialog { background: var(--surface); border: 1px solid var(--line); border-radius: 18px; width: min(640px, 100%); max-height: calc(100dvh - 48px); overflow: auto; padding: 28px; }
header, footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
h2 { color: var(--ink); font-size: 24px; font-weight: 600; }
p { font-size: 14px; line-height: 1.7; color: var(--muted); margin: 16px 0; }
.action-label { display: grid; gap: 10px; font-size: 14px; color: var(--ink); margin-top: 20px; }
.action-label select { min-height: 44px; }
.field-help, .message-length { font-size: 12px; color: var(--muted); line-height: 1.7; }
.recipient-list { list-style: none; padding: 0; margin: 24px 0; border-top: 1px solid var(--line); }
.recipient-list li { padding: 18px 0; border-bottom: 1px solid var(--line); }
.recipient-list li > strong { display: block; font-size: 17px; line-height: 1.6; font-weight: 600; color: var(--ink); }
.recipient-list li > span { display: block; font-size: 14px; line-height: 1.7; color: var(--muted); }
.recipient-list textarea { margin-top: 12px; }
textarea { resize: vertical; min-height: 112px; line-height: 1.7; }
.message-preview { padding: 14px 16px; background: var(--canvas); border-radius: 11px; color: var(--ink); white-space: pre-wrap; overflow-wrap: anywhere; }
.consent { display: flex; gap: 10px; font-size: 14px; line-height: 1.7; margin: 20px 0; align-items: flex-start; cursor: pointer; }
.consent input { width: 17px; height: 17px; margin: 3px 0 0; flex-shrink: 0; }
footer { justify-content: flex-end; margin-top: 24px; }
.warning, .recipient-list li > .warning { color: #b42318; }
.warning button { min-height: 44px; margin-left: 8px; color: var(--accent); font-size: 14px; }
@media (max-width: 640px) {
  .delivery-overlay { padding: 16px; }
  .delivery-dialog { padding: 20px; max-height: calc(100dvh - 32px); }
  h2 { font-size: 21px; }
  footer { flex-wrap: wrap; }
}
</style>
