<script setup>
import {
  Database,
  Monitor,
  RefreshCw,
} from 'lucide-vue-next'
import PageHeading from '../layouts/PageHeading.vue'
import { useWorkspace } from '../stores/workspace'
import { platformName } from '../constants/platforms'
import { API_BASE_URL } from '../api'

const backendApiUrl = API_BASE_URL.startsWith('/')
  ? `${import.meta.env.DEV ? 'http://127.0.0.1:8000' : window.location.origin}${API_BASE_URL}`
  : API_BASE_URL

const {
  system,
  collectionConfig,
  dbConnected,
  browserState,
  busy,
  isActive,
  reconnectDatabase,
  openBrowser,
  closeBrowser,
} = useWorkspace()
</script>

<template>
  <div>
    <PageHeading />
    <div class="settings-grid">
      <section class="panel settings-card">
        <div class="settings-icon purple"><Database :size="25" /></div>
        <div class="settings-card-title">
          <h2>{{ system?.database?.type || 'SQLite' }} 数据库</h2>
          <span class="status-pill" :class="dbConnected ? 'completed' : 'idle'"
            ><span></span>{{ dbConnected ? '已连接' : '未连接' }}</span
          >
        </div>
        <p>
          岗位、任务与投递记录保存在本机 SQLite 文件中，无需安装数据库，关闭应用后数据仍会保留。
        </p>
        <dl>
          <div>
            <dt>后端接口</dt>
            <dd>{{ backendApiUrl }}</dd>
          </div>
          <div>
            <dt>数据库文件</dt>
            <dd>{{ system?.database?.name || '等待后端连接' }}</dd>
          </div>
          <div>
            <dt>文件位置</dt>
            <dd>{{ system?.database?.path || '等待后端连接' }}</dd>
          </div>
          <div>
            <dt>连接状态</dt>
            <dd :class="{ 'warning-text': !dbConnected }">
              {{ system?.database?.message || '等待后端连接' }}
            </dd>
          </div>
        </dl>
        <button
          class="button button-white"
          :disabled="busy.database || isActive"
          @click="reconnectDatabase"
        >
          <RefreshCw :size="15" :class="{ spin: busy.database }" />{{
            busy.database ? '正在连接' : '重新连接数据库'
          }}
        </button>
      </section>
      <section class="panel settings-card">
        <div class="settings-icon green"><Monitor :size="25" /></div>
        <div class="settings-card-title">
          <h2>采集浏览器</h2>
          <span
            class="status-pill"
            :class="browserState.logged_in ? 'completed' : 'idle'"
            ><span></span
            >{{
              browserState.logged_in
                ? '已登录'
                : browserState.open
                  ? '待登录'
                  : '未打开'
            }}</span
          >
        </div>
        <p>在工作台选择平台后打开本机专用 Chrome，扫码或手动登录，各平台登录状态分别保存在本地。</p>
        <dl>
          <div>
            <dt>采集平台</dt>
            <dd>{{ platformName(browserState.open ? browserState.platform : collectionConfig.config.platform) }}</dd>
          </div>
          <div>
            <dt>登录方式</dt>
            <dd>在浏览器中扫码 / 手动登录</dd>
          </div>
          <div>
            <dt>数据范围</dt>
            <dd>岗位详情、公司信息、投递状态</dd>
          </div>
        </dl>
        <div class="settings-actions">
          <button
            class="button button-primary"
            :disabled="busy.browser"
            @click="openBrowser"
          >
            <Monitor :size="15" />{{
              busy.browser
                ? '正在打开'
                : browserState.open
                  ? '查看采集浏览器'
                  : '打开并登录'
            }}</button
          ><button
            class="button button-white"
            :disabled="!browserState.open || isActive || busy.browser"
            @click="closeBrowser"
          >
            关闭浏览器
          </button>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.settings-icon {
  width: 43px;
  height: 43px;
  border-radius: 11px;
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.settings-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 22px;
  max-width: 1100px;
}
.settings-card {
  padding: 25px;
}
.settings-icon {
  width: 51px;
  height: 51px;
  border-radius: 13px;
  margin-bottom: 20px;
}
.settings-card-title {
  display: flex;
  align-items: center;
  gap: 15px;
  justify-content: space-between;
}
.settings-card h2 {
  font-size: 16px;
}
.settings-card > p {
  font-size: 11px;
  line-height: 1.85;
  margin-top: 12px;
  color: #919caf;
}
.settings-card dl {
  margin: 23px 0;
  border-top: 1px solid var(--line);
}
.settings-card dl > div {
  padding: 13px 0;
  border-bottom: 1px solid var(--line);
  display: flex;
  gap: 15px;
  align-items: start;
  font-size: 11px;
}
.settings-card dt {
  color: #a0a8b9;
  flex: 0 0 72px;
}
.settings-card dd {
  margin: 0;
  color: #768299;
  line-height: 1.7;
  overflow-wrap: anywhere;
}
.settings-card dd.warning-text {
  color: #b59562;
}
.settings-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
@media (max-width: 840px) {
  .settings-grid {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 600px) {
  .settings-card {
    padding: 22px;
  }
  .settings-card h2 {
    font-size: 15px;
  }
  .settings-card .button {
    font-size: 11px;
    padding-left: 11px;
    padding-right: 11px;
  }
}
</style>
