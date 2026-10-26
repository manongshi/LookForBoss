<script setup>
import { AlertTriangle } from 'lucide-vue-next'

defineProps({ compact: Boolean })
</script>

<template>
  <aside class="delivery-notice" :class="{ compact }" aria-label="投递限制与注意事项">
    <div class="notice-heading">
      <AlertTriangle :size="24" aria-hidden="true" />
      <div>
        <h2>投递限制 · 开始前请确认</h2>
        <p>单次最多 50 个岗位不代表平台的每日投递额度，实际可投数量以官网提示为准。</p>
      </div>
    </div>
    <ul class="notice-rules">
      <li><strong>同平台、单任务</strong><span>每次最多选择 50 个同平台岗位；采集与投递不能同时运行。</span></li>
      <li><strong>默认简历、逐条执行</strong><span>先在官网设置并核对默认简历；正常投递后随机等待 10–20 秒，再处理下一条。</span></li>
      <li><strong>遇到限制会停止</strong><span>出现登录验证、频繁操作或额度上限提示时停止投递，请先在官网处理。</span></li>
      <li><strong>结果不明不自动重投</strong><span>成功记录会跳过；待核对记录需在岗位详情确认。“仅打开沟通”不代表消息或简历已发送。</span></li>
    </ul>
  </aside>
</template>

<style scoped>
.delivery-notice {
  padding: 22px 24px;
  border: 1px solid #edbd78;
  border-left: 5px solid #d97706;
  border-radius: 12px;
  background: #fff7e8;
  color: #71420d;
}
.notice-heading { display: flex; align-items: flex-start; gap: 12px; }
.notice-heading > svg { flex-shrink: 0; color: #b85d04; margin-top: 1px; }
.notice-heading h2 { font-size: 17px; font-weight: 700; line-height: 1.5; color: #85430b; }
.notice-heading p { margin-top: 5px; font-size: 13px; line-height: 1.7; color: #855e2d; }
.notice-rules { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px 28px; margin: 18px 0 0; padding: 17px 0 0; list-style: none; border-top: 1px solid #efd4ae; }
.notice-rules li { display: grid; gap: 5px; font-size: 13px; line-height: 1.8; }
.notice-rules strong { font-weight: 650; color: #71420d; }
.notice-rules span { color: #805f36; }
.delivery-notice.compact { padding: 16px; }
.compact .notice-rules { grid-template-columns: minmax(0, 1fr); gap: 12px; }
@media (max-width: 600px) {
  .delivery-notice { padding: 18px 16px; }
  .notice-heading h2 { font-size: 16px; }
  .notice-rules { grid-template-columns: minmax(0, 1fr); gap: 13px; }
}
</style>
