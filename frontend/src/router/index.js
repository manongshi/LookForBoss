import { createRouter, createWebHistory } from 'vue-router'
import WorkspaceLayout from '../layouts/WorkspaceLayout.vue'
import { navigation } from '../constants/navigation'

const views = {
  distribution: () => import('../views/DistributionView.vue'),
  assistant: () => import('../views/AssistantView.vue'),
  interview: () => import('../views/InterviewView.vue'),
  workbench: () => import('../views/WorkbenchView.vue'),
  jobs: () => import('../views/JobsView.vue'),
  messages: () => import('../views/MessagesView.vue'),
  records: () => import('../views/RecordsView.vue'),
  settings: () => import('../views/SettingsView.vue'),
}

export default createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      component: WorkspaceLayout,
      redirect: '/workbench',
      children: navigation.map((item) => ({
        path: item.id,
        name: item.id,
        component: views[item.id],
        meta: {
          label: item.label,
          title: item.title,
          description: item.description,
        },
      })),
    },
    { path: '/:pathMatch(.*)*', redirect: '/workbench' },
  ],
  scrollBehavior: () => ({ top: 0 }),
})
