<script setup>
import { ArrowUpRight, Briefcase, Building2, History } from 'lucide-vue-next'
import { useWorkspace } from '../stores/workspace'
import { number } from '../utils/format'

const { stats, isActive, browserState } = useWorkspace()
</script>

<template>
  <div class="stats-grid">
    <div class="stat-item">
      <span class="stat-icon purple"><Briefcase :size="20" /></span>
      <div>
        <span>岗位总数</span
        ><strong>{{ number(stats?.total) }}<small>条</small></strong>
      </div>
      <span class="stat-caption">去重后</span>
    </div>
    <div class="stat-item">
      <span class="stat-icon blue"><Building2 :size="20" /></span>
      <div>
        <span>覆盖公司</span
        ><strong>{{ number(stats?.companies) }}<small>家</small></strong>
      </div>
    </div>
    <div class="stat-item">
      <span class="stat-icon green"><ArrowUpRight :size="20" /></span>
      <div>
        <span>今日新增</span
        ><strong>{{ number(stats?.today) }}<small>条</small></strong>
      </div>
      <span class="stat-caption">首次采集</span>
    </div>
    <div class="stat-item">
      <span class="stat-icon amber"><History :size="20" /></span>
      <div>
        <span>采集任务</span
        ><strong>{{ number(stats?.tasks) }}<small>次</small></strong>
      </div>
      <span v-if="isActive" class="stat-live">{{
        browserState.waiting_for_login ? '等待登录' : '正在运行'
      }}</span>
    </div>
  </div>
</template>

<style scoped>
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}
.stat-item {
  position: relative;
  display: flex;
  gap: 14px;
  align-items: center;
  background: #fff;
  border: 1px solid #e8ecf3;
  border-radius: 9px;
  padding: 20px 18px;
  min-height: 105px;
  box-shadow: 0 2px 4px #26345102;
}
.stat-icon {
  width: 43px;
  height: 43px;
  border-radius: 11px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.stat-item > div > span {
  font-size: 11px;
  color: #8c97aa;
}
.stat-item strong {
  display: block;
  margin-top: 6px;
  font-size: 25px;
  font-weight: 650;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.5px;
}
.stat-item strong small {
  margin-left: 6px;
  color: #a6aebe;
  font-size: 10px;
  font-weight: 400;
  letter-spacing: 0;
}
.stat-caption {
  position: absolute;
  right: 13px;
  top: 14px;
  font-size: 9px;
  color: #a9b1bf;
}
.stat-live {
  position: absolute;
  top: 13px;
  right: 10px;
  border-radius: 4px;
  font-size: 8px;
  color: var(--green);
  background: #eef9f3;
  padding: 3px 5px;
}
@media (min-width: 1600px) {
  .stat-item {
    padding: 23px;
  }
}
@media (max-width: 1280px) {
  .stats-grid {
    gap: 12px;
  }
  .stat-item {
    padding: 20px 13px;
    gap: 10px;
  }
  .stat-icon {
    height: 37px;
    width: 37px;
    border-radius: 9px;
  }
  .stat-item strong {
    font-size: 23px;
  }
  .stat-caption {
    display: none;
  }
}
@media (max-width: 1060px) {
  .stat-icon {
    width: 33px;
    height: 33px;
  }
  .stat-item {
    padding: 16px 12px;
    min-height: 95px;
  }
  .stat-item strong {
    font-size: 22px;
  }
  .stat-live {
    font-size: 7px;
    top: 8px;
  }
}
@media (max-width: 840px) {
  .stats-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .stat-item {
    min-height: 92px;
    padding: 16px 19px;
  }
  .stat-caption {
    display: block;
  }
  .stat-icon {
    width: 39px;
    height: 39px;
  }
}
@media (max-width: 600px) {
  .stats-grid {
    gap: 10px;
    margin-bottom: 18px;
  }
  .stat-item {
    padding: 15px 12px;
    gap: 10px;
    min-height: 88px;
  }
  .stat-icon {
    width: 33px;
    height: 33px;
    border-radius: 9px;
  }
  .stat-icon svg {
    width: 18px;
  }
  .stat-item > div > span {
    font-size: 9px;
  }
  .stat-item strong {
    font-size: 21px;
    margin-top: 7px;
  }
  .stat-item strong small {
    font-size: 9px;
    margin-left: 4px;
  }
  .stat-caption {
    display: none;
  }
  .stat-live {
    top: 7px;
    right: 7px;
  }
}
</style>
