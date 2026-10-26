<script setup>
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import {
  Briefcase,
  Copy,
  ExternalLink,
  FileText,
  MapPin,
  MessagesSquare,
  Users,
  X,
} from 'lucide-vue-next'
import { request, post } from '../../api'
import { platformName, deliveryName } from '../../constants/platforms'
import { useWorkspace } from '../../stores/workspace'
import { useDialog } from '../../composables/useDialog'
import { time } from '../../utils/format'
import JobAssistantPanel from './JobAssistantPanel.vue'

const emit = defineEmits(['rules-changed'])

const { notify, copyText, isActive, refreshAll } = useWorkspace()
const resolving = ref(false)
const selectedJob = ref(null)
const detailTab = ref('job')
useDialog(
  computed(() => Boolean(selectedJob.value)),
  closeDetail,
  '.drawer-close',
)
function closeDetail() {
  selectedJob.value = null
}
async function openDetail(job, event, tab = 'job') {
  selectedJob.value = job
  detailTab.value = tab
  try {
    const detail = await request(`/jobs/${job.id}`)
    if (selectedJob.value?.id === job.id) selectedJob.value = detail
  } catch (error) {
    notify(error.message, 'error')
  }
}

async function resolveDelivery(status) {
  if (resolving.value || isActive.value) return
  const job = selectedJob.value
  resolving.value = true
  try {
    const updated = await post(`/jobs/${job.id}/delivery/${job.delivery_action}/resolve`, { status })
    if (selectedJob.value?.id === job.id) selectedJob.value = updated
    await refreshAll()
    notify('已记录你核对的投递结果')
  } catch (error) { notify(error.message, 'error') }
  finally { resolving.value = false }
}

defineExpose({ openDetail })
</script>

<template>
  <Transition name="drawer">
    <div v-if="selectedJob" class="drawer-overlay" @click.self="closeDetail">
      <aside class="job-drawer" role="dialog" aria-modal="true" aria-labelledby="detail-title">
        <div class="drawer-top"><span>职位详情</span><button class="icon-button drawer-close" aria-label="关闭职位详情" @click="closeDetail"><X :size="20" /></button></div>
        <div class="drawer-content">
          <span class="source-badge">{{ platformName(selectedJob.source) }}</span>
          <h2 id="detail-title">{{ selectedJob.title }}</h2>
          <div class="drawer-salary">{{ selectedJob.salary || '薪资未标注' }}</div>
          <div class="drawer-job-meta">
            <span><MapPin :size="16" />{{ selectedJob.location || selectedJob.city || '地点未标注' }}</span>
            <span><Briefcase :size="16" />{{ selectedJob.experience || '经验不限' }}</span>
            <span><Users :size="16" />{{ selectedJob.degree || '学历不限' }}</span>
          </div>
          <div class="drawer-company">
            <span class="company-avatar">{{ selectedJob.company?.slice(0, 1) || '企' }}</span>
            <div><strong>{{ selectedJob.company || '公司未标注' }}</strong><span>{{ [selectedJob.industry, selectedJob.scale, selectedJob.stage].filter(Boolean).join(' · ') || '暂无公司附加信息' }}</span></div>
          </div>
          <div class="detail-tabs" aria-label="职位详情内容">
            <button :class="{ active: detailTab === 'job' }" :aria-pressed="detailTab === 'job'" @click="detailTab = 'job'">职位描述</button>
            <button :class="{ active: detailTab === 'company' }" :aria-pressed="detailTab === 'company'" @click="detailTab = 'company'">公司信息</button>
            <button :class="{ active: detailTab === 'assistant' }" :aria-pressed="detailTab === 'assistant'" @click="detailTab = 'assistant'">匹配 / 招呼语</button>
            <button v-if="selectedJob.delivery_status" :class="{ active: detailTab === 'delivery' }" :aria-pressed="detailTab === 'delivery'" @click="detailTab = 'delivery'">执行记录</button>
          </div>
          <template v-if="detailTab === 'job'">
            <div v-if="selectedJob.tags?.length" class="detail-tags"><span v-for="tag in selectedJob.tags" :key="tag">{{ tag }}</span></div>
            <div class="jd-content">{{ selectedJob.description || (selectedJob.detail_status === 'pending' ? '职位描述正在补充中。' : selectedJob.detail_status === 'unavailable' ? '详情暂未补全，可查看原始职位。' : '暂无职位描述，可查看原始职位。') }}</div>
            <div v-if="selectedJob.address" class="detail-address"><h3><MapPin :size="16" />工作地址</h3><p>{{ selectedJob.address }}</p></div>
            <div v-if="selectedJob.hr_name" class="hr-card"><span class="hr-avatar"><Users :size="21" /></span><div><strong>{{ selectedJob.hr_name }}<small>{{ selectedJob.hr_title }}</small></strong><span>{{ selectedJob.hr_active || '活跃状态未标注' }}</span></div></div>
          </template>
          <template v-else-if="detailTab === 'company'">
            <dl class="company-details">
              <div><dt>公司名称</dt><dd>{{ selectedJob.company || '未标注' }}</dd></div>
              <div><dt>所属行业</dt><dd>{{ selectedJob.industry || '未标注' }}</dd></div>
              <div><dt>公司规模</dt><dd>{{ selectedJob.scale || '未标注' }}</dd></div>
              <div><dt>融资阶段</dt><dd>{{ selectedJob.stage || '未标注' }}</dd></div>
            </dl>
            <h3 class="company-intro-label">公司介绍</h3><div class="jd-content">{{ selectedJob.company_description || '暂无公司介绍' }}</div>
          </template>
          <div v-else-if="detailTab === 'delivery'" class="delivery-result">
            <h3>{{ selectedJob.delivery_action === 'message' ? '发送消息' : selectedJob.delivery_action === 'contact' ? '打开沟通' : '简历投递' }} · {{ deliveryName(selectedJob.delivery_status, selectedJob.delivery_action) }}</h3>
            <p>{{ selectedJob.delivery_message }}</p>
            <template v-if="selectedJob.delivery_status === 'unknown'">
              <p>请先打开原始职位，在官网核对后选择。确认未发送后才允许重新投递。</p>
              <div class="delivery-result-actions"><button class="button button-white" :disabled="isActive || resolving" @click="resolveDelivery('confirmed')">官网确认已完成</button><button class="button button-white" :disabled="isActive || resolving" @click="resolveDelivery('not_sent')">官网确认未发送</button></div>
            </template>
          </div>
          <JobAssistantPanel v-show="detailTab === 'assistant'" :key="selectedJob.id" :job="selectedJob" @close="closeDetail" @rules-changed="emit('rules-changed')" />
          <RouterLink class="interview-job-link" :to="{ name: 'interview', query: { job: selectedJob.id } }" @click="closeDetail"><MessagesSquare :size="18" /><span><strong>针对这份职位练习面试</strong><small>将岗位要求交给 AI，生成问题并逐题对答</small></span></RouterLink>
          <RouterLink v-if="(selectedJob.source || 'boss') === 'boss'" class="message-history-link" :to="{ name: 'messages', query: { job: selectedJob.id, status: 'all' } }" @click="closeDetail">查看该职位的消息记录</RouterLink>
          <div class="detail-collected"><span>首次采集 {{ time(selectedJob.first_seen, true) }}</span><span>最近更新 {{ time(selectedJob.last_seen, true) }}</span></div>
        </div>
        <footer class="drawer-footer"><button class="button button-white" @click="copyText(selectedJob.url)"><Copy :size="16" />复制链接</button><a class="button button-primary" :href="selectedJob.url" target="_blank" rel="noopener noreferrer">查看原始职位<ExternalLink :size="16" /></a></footer>
      </aside>
    </div>
  </Transition>
</template>

<style scoped>
.interview-job-link { display: flex; align-items: center; gap: 13px; margin-top: 28px; padding: 18px; background: #eaf3fc; border: 1px solid #cce0f5; border-radius: 12px; color: var(--accent); }
.interview-job-link span { display: grid; gap: 6px; }
.interview-job-link strong { font-size: 15px; font-weight: 600; }
.interview-job-link small { font-size: 12px; line-height: 1.7; color: var(--muted); }
.drawer-overlay { position: fixed; z-index: 50; inset: 0; display: flex; justify-content: flex-end; background: rgb(0 0 0 / 22%); backdrop-filter: blur(5px); }
.job-drawer { display: flex; flex-direction: column; width: 720px; max-width: 100%; height: 100dvh; background: var(--surface); border-left: 1px solid var(--line); }
.drawer-top { display: flex; align-items: center; justify-content: space-between; min-height: 72px; padding: 12px 32px; border-bottom: 1px solid var(--line); color: var(--muted); font-size: 14px; flex-shrink: 0; }
.drawer-content { flex: 1; min-height: 0; overflow-y: auto; overscroll-behavior: contain; padding: 32px; }
.source-badge { display: inline-block; color: var(--muted); font-size: 14px; line-height: 1.5; }
#detail-title { margin-top: 12px; font-family: var(--font-display); color: var(--ink); font-size: 34px; font-weight: 600; letter-spacing: -.374px; line-height: 1.3; overflow-wrap: anywhere; }
.drawer-salary { margin-top: 14px; color: var(--accent); font-size: 28px; font-weight: 600; line-height: 1.4; letter-spacing: -.3px; font-variant-numeric: tabular-nums; }
.drawer-job-meta { display: flex; flex-wrap: wrap; gap: 12px 20px; margin-top: 18px; color: var(--muted); font-size: 14px; line-height: 1.6; }
.drawer-job-meta > span { display: inline-flex; align-items: center; gap: 7px; }
.drawer-job-meta svg { flex-shrink: 0; }
.drawer-company { display: flex; align-items: center; gap: 14px; margin: 28px 0; padding: 20px; background: var(--canvas); border-radius: 18px; }
.company-avatar, .hr-avatar { display: grid; place-items: center; width: 44px; height: 44px; flex-shrink: 0; border-radius: 11px; background: var(--surface); color: var(--ink); font-size: 21px; font-weight: 600; }
.drawer-company > div { min-width: 0; }
.drawer-company strong { color: var(--ink); font-size: 17px; font-weight: 600; line-height: 1.5; overflow-wrap: anywhere; }
.drawer-company div > span { display: block; margin-top: 6px; color: var(--muted); font-size: 14px; line-height: 1.7; }
.detail-tabs { display: flex; gap: 24px; overflow-x: auto; border-bottom: 1px solid var(--line); margin-bottom: 24px; }
.detail-tabs button { position: relative; min-height: 48px; flex-shrink: 0; padding: 8px 0 14px; color: var(--muted); font-size: 14px; white-space: nowrap; }
.detail-tabs button.active { color: var(--ink); }
.detail-tabs button.active::after { content: ''; position: absolute; bottom: 0; right: 0; left: 0; height: 2px; background: var(--accent); }
.detail-tags { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 24px; }
.detail-tags span { max-width: 100%; padding: 6px 12px; border-radius: 8px; background: var(--canvas); color: var(--muted); font-size: 14px; line-height: 1.5; overflow-wrap: anywhere; }
.jd-content { color: var(--ink); font-size: 17px; font-weight: 400; line-height: 1.8; white-space: pre-wrap; overflow-wrap: anywhere; }
.detail-address { margin-top: 32px; padding-top: 24px; border-top: 1px solid var(--line); }
.detail-address h3, .company-intro-label, .delivery-result h3 { color: var(--ink); font-size: 17px; font-weight: 600; line-height: 1.5; }
.detail-address h3 { display: flex; align-items: center; gap: 8px; }
.detail-address p { margin-top: 12px; color: #515154; font-size: 17px; line-height: 1.7; }
.hr-card { display: flex; align-items: center; gap: 14px; margin-top: 24px; padding: 18px; border-radius: 18px; background: var(--canvas); }
.hr-card strong { font-size: 17px; font-weight: 600; }
.hr-card small { margin-left: 10px; font-size: 14px; font-weight: 400; color: var(--muted); }
.hr-card div > span { display: block; margin-top: 6px; font-size: 14px; color: var(--muted); }
.company-details { display: flex; flex-direction: column; gap: 16px; margin: 0 0 32px; font-size: 17px; line-height: 1.6; }
.company-details > div { display: flex; gap: 20px; }
.company-details dt { flex: 0 0 84px; color: var(--muted); }
.company-details dd { margin: 0; color: var(--ink); overflow-wrap: anywhere; }
.company-intro-label { margin-bottom: 16px; }
.delivery-result { padding: 20px; border-radius: 18px; background: var(--canvas); }
.delivery-result p { margin-top: 12px; font-size: 17px; line-height: 1.7; color: #515154; overflow-wrap: anywhere; }
.delivery-result-actions { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 20px; }
.detail-collected { display: flex; flex-wrap: wrap; gap: 8px 20px; margin-top: 32px; padding-top: 24px; border-top: 1px solid var(--line); color: var(--muted); font-size: 12px; line-height: 1.7; }
.message-history-link { display: inline-flex; align-items: center; min-height: 44px; margin-top: 24px; color: var(--accent); font-size: 14px; }
.drawer-footer { display: flex; justify-content: flex-end; gap: 12px; flex-shrink: 0; border-top: 1px solid var(--line); padding: 20px 32px max(20px, env(safe-area-inset-bottom)); background: var(--surface); }
.drawer-enter-active, .drawer-leave-active { transition: opacity .2s; }
.drawer-enter-active .job-drawer, .drawer-leave-active .job-drawer { transition: transform .2s; }
.drawer-enter-from, .drawer-leave-to { opacity: 0; }
.drawer-enter-from .job-drawer, .drawer-leave-to .job-drawer { transform: translateX(100%); }
@media (max-width: 640px) {
  .drawer-top { min-height: 64px; padding: 10px 20px; }
  .drawer-content { padding: 24px 20px; }
  #detail-title { font-size: 28px; }
  .drawer-salary { font-size: 24px; }
  .drawer-company { padding: 16px; }
  .detail-tabs { gap: 22px; }
  .drawer-footer { padding: 16px 20px max(16px, env(safe-area-inset-bottom)); }
  .drawer-footer .button { flex: 1; padding: 10px 14px; }
}
</style>
