import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import './styles/base.css'
import './styles/common.css'
import './styles/workspace.css'

createApp(App).use(router).use(ElementPlus, { locale: zhCn }).mount('#app')
