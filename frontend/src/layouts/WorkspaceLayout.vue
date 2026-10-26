<script setup>
import { computed, KeepAlive } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { AlertCircle, Briefcase, ChevronDown } from 'lucide-vue-next'
import { navigation } from '../constants/navigation'
import { useWorkspace } from '../stores/workspace'

const route = useRoute()
const router = useRouter()
const { system, apiError, busy, dbConnected, isActive, refreshAll, reconnectDatabase } = useWorkspace()
const primaryNavigation = navigation.filter(item => ['workbench', 'jobs', 'messages', 'interview'].includes(item.id))
const moreNavigation = navigation.filter(item => !['workbench', 'jobs', 'messages', 'interview'].includes(item.id))
const moreLabel = computed(() => moreNavigation.find(item => item.id === route.name)?.label || '更多')
</script>

<template>
  <div class="common-layout" :class="{ 'interview-layout': route.name === 'interview' }">
    <header class="workspace-header">
      <div class="header-inner">
        <RouterLink class="workspace-brand" :to="{ name: 'workbench' }" aria-label="FindBoss 首页">
          <Briefcase :size="23" :stroke-width="1.6" />
          <span>FindBoss</span>
        </RouterLink>
        <nav class="workspace-navigation" aria-label="主导航">
          <RouterLink v-for="item in primaryNavigation" :key="item.id" :to="{ name: item.id }" class="navigation-link" :class="{ active: route.name === item.id }" :aria-current="route.name === item.id ? 'page' : undefined">
            {{ item.label }}
          </RouterLink>
        </nav>
        <div class="header-utilities">
          <RouterLink v-if="isActive" class="running-link" :to="{ name: 'records' }"><span class="status-dot online"></span><span>任务进行中</span></RouterLink>
          <el-dropdown trigger="click" @command="name => router.push({ name })">
            <button class="more-menu" :class="{ active: moreNavigation.some(item => item.id === route.name) }">{{ moreLabel }}<ChevronDown :size="14" /></button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item v-for="item in moreNavigation" :key="item.id" :command="item.id"><component :is="item.icon" :size="16" />{{ item.label }}</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>
    </header>
    <main class="workspace-main">
      <div class="workspace-content">
        <div v-if="apiError || (system && !dbConnected)" class="connection-banner" role="alert">
          <AlertCircle :size="18" />
          <span>{{ apiError || system.database.message }}</span>
          <el-button size="small" :loading="busy.database" @click="apiError ? refreshAll() : reconnectDatabase()">重新连接</el-button>
        </div>
        <RouterView v-slot="{ Component }">
          <KeepAlive><component :is="Component" /></KeepAlive>
        </RouterView>
      </div>
    </main>
  </div>
</template>

<style scoped>
.workspace-header { position: sticky; top: 0; z-index: 20; background: rgb(0 0 0 / 88%); backdrop-filter: saturate(180%) blur(20px); color: #f5f5f7; }
.header-inner { display: flex; align-items: center; gap: 52px; max-width: 1248px; min-height: 64px; padding: 0 24px; margin: 0 auto; }
.workspace-brand { display: inline-flex; align-items: center; gap: 10px; font-family: var(--font-display); font-size: 21px; font-weight: 600; letter-spacing: -.6px; flex-shrink: 0; }
.workspace-navigation { align-self: stretch; display: flex; align-items: stretch; gap: 32px; min-width: 0; }
.navigation-link { position: relative; display: flex; align-items: center; min-height: 44px; font-size: 14px; color: #c5c5c9; white-space: nowrap; }
.navigation-link:hover, .navigation-link.active { color: #fff; }
.navigation-link.active::after { content: ''; position: absolute; right: 0; bottom: 0; left: 0; height: 2px; background: #fff; }
.header-utilities { display: flex; align-items: center; gap: 24px; margin-left: auto; }
.running-link { display: inline-flex; align-items: center; gap: 8px; font-size: 12px; color: #d2d2d7; white-space: nowrap; }
.more-menu { display: inline-flex; align-items: center; gap: 7px; min-height: 44px; padding: 0 4px; color: #c5c5c9; font-size: 14px; white-space: nowrap; }
.more-menu.active, .more-menu:hover { color: #fff; }
.workspace-main { padding: 40px 24px 64px; }
.workspace-content { max-width: 1200px; margin: 0 auto; min-width: 0; }
.connection-banner { display: flex; align-items: center; gap: 12px; padding: 14px 18px; margin-bottom: 24px; border: 1px solid #ead9b5; border-radius: 11px; background: #fffbf2; color: #82590e; font-size: 14px; line-height: 1.6; }
.connection-banner > svg { flex-shrink: 0; }
.connection-banner > span { overflow-wrap: anywhere; }
.connection-banner .el-button { margin-left: auto; flex-shrink: 0; }
.interview-layout { display: flex; flex-direction: column; height: 100vh; height: 100dvh; min-height: 0; overflow: hidden; }
.interview-layout .workspace-header { flex-shrink: 0; }
.interview-layout .workspace-main { display: flex; flex: 1; min-height: 0; overflow: hidden; padding: 24px; }
.interview-layout .workspace-content { display: flex; flex-direction: column; flex: 1; width: 100%; min-height: 0; overflow: hidden; }
.interview-layout .connection-banner { flex-shrink: 0; max-height: 20%; overflow-y: auto; }
@media (max-width: 700px) {
  .header-inner { min-height: 60px; gap: 20px; padding: 0 20px; flex-wrap: wrap; }
  .workspace-navigation { order: 3; flex-basis: 100%; justify-content: space-between; gap: 16px; overflow-x: auto; }
  .navigation-link { min-height: 44px; }
  .workspace-brand { font-size: 18px; gap: 7px; }
  .workspace-brand svg { width: 20px; }
  .workspace-navigation { gap: 22px; }
  .header-utilities { gap: 12px; }
  .running-link { display: none; }
  .workspace-main { padding: 28px 20px 40px; }
  .connection-banner { flex-wrap: wrap; padding: 12px; }
  .interview-layout .workspace-main { padding: 16px 20px; }
}
@media (max-width: 420px) {
  .header-inner { gap: 12px; padding: 0 12px; }
  .workspace-brand { font-size: 17px; }
  .workspace-brand svg { display: none; }
  .workspace-navigation { gap: 12px; }
  .navigation-link, .more-menu { font-size: 13px; }
  .workspace-main { padding: 24px 16px 32px; }
  .interview-layout .workspace-main { padding: 12px 16px; }
}
</style>
