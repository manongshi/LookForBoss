<script setup>
import { computed, reactive, ref } from 'vue'
import {
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronDown,
  LoaderCircle,
  MapPin,
  Plus,
  Search,
  Settings2,
  X,
} from 'lucide-vue-next'
import { useWorkspace } from '../../stores/workspace'
import { useDialog } from '../../composables/useDialog'
import { platformName } from '../../constants/platforms'

const {
  collectionConfig,
  busy,
  browserState,
  isActive,
  dbConnected,
  notify,
  startCollection,
  openBrowser,
} = useWorkspace()
const { config, cityOptions, selectedCities, platforms, currentPlatform, filterOptions, optionsReady, addCity, loadOptions } = collectionConfig
const filterLabels = { salary: '薪资范围', experience: '工作经验', degree: '学历要求', scale: '公司规模' }
const keywordInput = ref('')
const showAdvanced = ref(false)
const showCities = ref(false)
const citySearch = ref('')
const customCity = reactive({ name: '', code: '' })
const availableCities = computed(() =>
  cityOptions.value.filter((city) => city.name.includes(citySearch.value)),
)
useDialog(showCities, closeCities, '.city-search input')
function addKeyword() {
  const incoming = keywordInput.value
    .split(/[,，;；\n]/)
    .map((item) => item.trim())
    .filter(Boolean)
  const next = [...new Set([...config.keywords, ...incoming])]
  if (next.length > 8 || next.some((item) => item.length > 80)) {
    notify('最多添加 8 个关键词，每个不超过 80 字', 'error')
    return false
  }
  config.keywords = next
  keywordInput.value = ''
  return true
}
function keywordKey(event) {
  if (!event.isComposing && ['Enter', ',', '，'].includes(event.key)) {
    event.preventDefault()
    addKeyword()
  }
}
function toggleCity(code) {
  if (config.cityCodes.includes(code))
    config.cityCodes = config.cityCodes.filter((item) => item !== code)
  else if (config.cityCodes.length < 8) config.cityCodes.push(code)
  else notify('一次任务最多选择 8 个城市', 'error')
}
function addCustomCity() {
  if (!customCity.name.trim() || !/^\d{1,9}$/.test(customCity.code)) {
    notify('请输入城市名称和当前平台的数字城市代码', 'error')
    return
  }
  if (!cityOptions.value.some((city) => city.code === customCity.code))
    addCity({
      name: customCity.name.trim(),
      code: customCity.code,
    })
  if (!config.cityCodes.includes(customCity.code)) toggleCity(customCity.code)
  customCity.name = ''
  customCity.code = ''
}
function openCities() {
  showCities.value = true
}
function closeCities() {
  showCities.value = false
}
function submitCollection() {
  if (!addKeyword()) return
  startCollection()
}
</script>

<template>
  <section class="panel config-panel collection-composer" aria-label="采集职位">
    <form @submit.prevent="submitCollection">
      <div class="collection-main-fields">
        <div class="form-section keyword-section">
          <label class="field-label" for="collection-keywords">职位关键词</label>
          <div class="keyword-field">
            <span v-for="(keyword, index) in config.keywords" :key="keyword" class="keyword-chip">
              {{ keyword }}
              <button type="button" :aria-label="`移除关键词 ${keyword}`" @click="config.keywords.splice(index, 1)">
                <X :size="14" />
              </button>
            </span>
            <input
              id="collection-keywords"
              v-model="keywordInput"
              placeholder="输入职位关键词，回车添加"
              maxlength="80"
              @keydown="keywordKey"
            />
          </div>
        </div>
        <div class="form-section">
          <label class="field-label" for="collection-platform">招聘平台</label>
          <select id="collection-platform" v-model="config.platform" :disabled="isActive || busy.start || !optionsReady">
            <option v-for="item in platforms" :key="item.id" :value="item.id">{{ item.name }}{{ item.experimental ? '（实验）' : '' }}</option>
          </select>
        </div>
        <div class="form-section">
          <label class="field-label" for="collection-cities">工作城市</label>
          <button id="collection-cities" type="button" class="city-control" @click="openCities">
            <MapPin :size="17" />
            <span>{{ selectedCities.map((city) => city.name).join('、') || '请选择城市' }}</span>
            <ChevronDown :size="15" />
          </button>
        </div>
        <button
          class="button button-primary start-button"
          type="submit"
          :disabled="busy.start || isActive || !dbConnected || !optionsReady"
        >
          <LoaderCircle v-if="busy.start" :size="17" class="spin" />
          {{ busy.start ? '正在创建' : isActive ? browserState.waiting_for_login ? '等待登录' : '正在采集' : '开始采集' }}
          <ArrowRight v-if="!isActive && !busy.start" :size="17" />
        </button>
      </div>
      <div class="collection-utilities">
        <button
          type="button"
          class="advanced-toggle"
          aria-controls="collection-advanced"
          :aria-expanded="showAdvanced"
          @click="showAdvanced = !showAdvanced"
        >
          <Settings2 :size="16" />更多设置<ChevronDown :size="14" :class="{ rotated: showAdvanced }" />
        </button>
        <div class="browser-connection">
          <span class="browser-status">{{ browserState.logged_in ? '已登录' : browserState.open ? '等待登录' : '浏览器未连接' }}</span>
          <button type="button" :disabled="busy.browser" @click="openBrowser">
            <LoaderCircle v-if="busy.browser" :size="15" class="spin" />
            {{ busy.browser ? '正在打开' : browserState.logged_in ? '打开浏览器' : `登录${platformName(config.platform)}` }}
            <ArrowUpRight v-if="!busy.browser" :size="15" />
          </button>
        </div>
      </div>
      <p v-if="!optionsReady" class="field-hint config-error">
        平台配置尚未加载。
        <button type="button" @click="loadOptions().catch(error => notify(error.message, 'error'))">重新加载</button>
      </p>
      <p v-if="currentPlatform?.experimental" class="field-hint">该平台适配仍在实验阶段，页面变动可能影响采集。</p>
      <div v-if="showAdvanced" id="collection-advanced" class="advanced-fields">
        <label for="job-limit">本次采集上限
          <div class="number-control">
            <input id="job-limit" v-model.number="config.max_jobs" type="number" min="1" max="2000" required />
            <span>条 · 最多 2,000</span>
          </div>
        </label>
        <label>任务名称<input v-model="config.name" placeholder="留空自动生成" maxlength="120" /></label>
        <div class="advanced-filters">
          <div class="form-filter-columns">
            <label v-for="(label, key) in filterLabels" :key="key">{{ label }}
              <select v-model="config[key]" :disabled="!filterOptions[key]?.length">
                <option value="">{{ filterOptions[key]?.length ? '不限' : '当前平台未提供' }}</option>
                <option v-for="option in filterOptions[key] || []" :key="option.code" :value="option.code">{{ option.name }}</option>
              </select>
            </label>
          </div>
        </div>
        <label>最大翻页 / 滚动轮数
          <input v-model.number="config.max_scrolls" type="number" min="1" max="300" required />
        </label>
        <div class="form-two-columns">
          <label>最小间隔 / 秒<input v-model.number="config.delay_min" type="number" min="5" max="120" required /></label>
          <label>最大间隔 / 秒<input v-model.number="config.delay_max" type="number" min="5" max="180" required /></label>
        </div>
      </div>
    </form>
  </section>
  <Transition name="modal"
    ><div v-if="showCities" class="modal-overlay" @click.self="closeCities">
      <section
        class="city-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="city-dialog-title"
      >
        <header>
          <div>
            <h2 id="city-dialog-title">选择采集城市</h2>
            <p>最多 8 个城市，将依次执行搜索。</p>
          </div>
          <button
            class="icon-button"
            aria-label="关闭城市选择"
            @click="closeCities"
          >
            <X :size="19" />
          </button>
        </header>
        <div class="search-field city-search">
          <Search :size="16" /><input
            v-model="citySearch"
            placeholder="搜索城市"
            aria-label="搜索采集城市"
          />
        </div>
        <div class="city-options">
          <button
            v-for="city in availableCities"
            :key="city.code"
            :class="{ selected: config.cityCodes.includes(city.code) }"
            @click="toggleCity(city.code)"
          >
            {{ city.name
            }}<Check v-if="config.cityCodes.includes(city.code)" :size="13" />
          </button>
        </div>
        <div class="custom-city">
          <span>添加其他城市</span>
          <div>
            <input
              v-model="customCity.name"
              placeholder="城市名称"
              aria-label="自定义城市名称"
              maxlength="32"
            /><input
              v-model="customCity.code"
              placeholder="当前平台城市代码"
              aria-label="自定义城市代码"
              maxlength="9"
            /><button
              class="button button-white compact"
              @click="addCustomCity"
            >
              <Plus :size="14" />添加
            </button>
          </div>
        </div>
        <footer>
          <span>已选择 {{ config.cityCodes.length }} 个城市</span
          ><button
            class="button button-primary"
            :disabled="!config.cityCodes.length"
            @click="closeCities"
          >
            完成选择<Check :size="15" />
          </button>
        </footer>
      </section></div
  ></Transition>
</template>

<style scoped>
.collection-composer {
  padding: 24px;
  border: 1px solid var(--line, #e0e0e0);
  border-radius: 18px;
  background: var(--surface, #fff);
  box-shadow: none;
  font-family: "SF Pro Text", -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
  color: #1d1d1f;
}
.collection-composer form { display: block; }
.collection-main-fields {
  display: grid;
  grid-template-columns: minmax(240px, 2.3fr) minmax(150px, 1fr) minmax(170px, 1.1fr) auto;
  align-items: end;
  gap: 16px;
}
.form-section { min-width: 0; padding: 0; }
.field-label {
  display: block;
  margin-bottom: 8px;
  color: var(--muted, #6e6e73);
  font-size: 14px;
  font-weight: 400;
  line-height: 1.43;
}
.collection-composer select,
.collection-composer input,
.city-control,
.city-dialog input {
  min-height: 48px;
  border: 1px solid var(--line, #e0e0e0);
  border-radius: 11px;
  background: var(--surface, #fff);
  color: #1d1d1f;
  font-size: 17px;
  font-weight: 400;
  line-height: 1.47;
  box-shadow: none;
}
.collection-composer select { padding: 10px 32px 10px 14px; }
.keyword-field {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  min-height: 48px;
  padding: 2px 8px;
  border: 1px solid var(--line, #e0e0e0);
  border-radius: 11px;
  background: var(--surface, #fff);
}
.keyword-field:focus-within {
  border-color: #0071e3;
  outline: 2px solid #0071e3;
  outline-offset: 2px;
}
.keyword-chip {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  padding-left: 10px;
  border-radius: 8px;
  background: var(--canvas, #f5f5f7);
  color: #1d1d1f;
  font-size: 14px;
  line-height: 1.43;
  overflow-wrap: anywhere;
}
.keyword-chip button {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  flex-shrink: 0;
  padding: 0;
  color: var(--muted, #6e6e73);
}
.keyword-field input {
  flex: 1 1 150px;
  width: 0;
  min-width: 110px;
  min-height: 44px;
  padding: 7px 4px;
  border: 0;
  outline: none;
  background: transparent;
  box-shadow: none;
  font-size: 17px;
}
.city-control {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 10px 14px;
}
.city-control > svg { flex-shrink: 0; color: var(--muted, #6e6e73); }
.city-control > span {
  flex: 1;
  overflow: hidden;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.start-button {
  min-height: 48px;
  min-width: 148px;
  margin: 0;
  padding: 11px 22px;
  border-radius: 999px;
  background: var(--accent, #0066cc);
  box-shadow: none;
  font-size: 17px;
  font-weight: 400;
  line-height: 1.47;
  gap: 8px;
  white-space: nowrap;
}
.collection-utilities {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0 20px;
  margin-top: 8px;
}
.advanced-toggle,
.browser-connection button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 44px;
  margin: 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--accent, #0066cc);
  font-size: 14px;
  font-weight: 400;
}
.advanced-toggle > svg:last-child { transition: transform 0.2s; }
.rotated { transform: rotate(180deg); }
.browser-connection { display: flex; align-items: center; gap: 12px; margin: 0; }
.browser-status { color: var(--muted, #6e6e73); font-size: 14px; }
.field-hint { margin: 0; color: var(--muted, #6e6e73); font-size: 14px; line-height: 1.43; }
.config-error { display: flex; align-items: center; flex-wrap: wrap; }
.config-error button { min-height: 44px; color: var(--accent, #0066cc); padding: 0 8px; }
.advanced-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px 24px;
  margin-top: 8px;
  padding: 24px 0 0;
  border-top: 1px solid var(--line, #e0e0e0);
}
.advanced-fields label { display: block; color: var(--muted, #6e6e73); font-size: 14px; line-height: 1.43; }
.advanced-fields input,
.advanced-fields select { margin-top: 8px; padding: 10px 14px; }
.advanced-fields select { padding-right: 30px; }
.advanced-filters { grid-column: 1 / -1; }
.form-filter-columns { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }
.form-two-columns { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.number-control { display: flex; align-items: center; gap: 12px; margin-top: 8px; }
.number-control input { width: 120px; margin-top: 0; font-variant-numeric: tabular-nums; }
.number-control > span { font-size: 14px; white-space: nowrap; }
.modal-overlay {
  position: fixed;
  z-index: 50;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: #00000040;
  backdrop-filter: blur(6px);
}
.city-dialog {
  width: 620px;
  max-width: 100%;
  max-height: calc(100dvh - 48px);
  overflow-y: auto;
  padding: 24px;
  border: 1px solid var(--line, #e0e0e0);
  border-radius: 18px;
  background: var(--surface, #fff);
  color: #1d1d1f;
  box-shadow: none;
}
.city-dialog header { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 20px; }
.city-dialog h2 { font-size: 24px; font-weight: 600; letter-spacing: -0.3px; }
.city-dialog header p { margin-top: 8px; color: var(--muted, #6e6e73); font-size: 14px; line-height: 1.43; }
.city-dialog .icon-button { min-width: 44px; min-height: 44px; }
.city-search { margin-bottom: 20px; min-height: 48px; border-radius: 11px; }
.city-search input { min-height: 46px; padding: 10px; border: 0; background: transparent; }
.city-options { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; }
.city-options button {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  min-height: 44px;
  padding: 8px 4px;
  border: 1px solid var(--line, #e0e0e0);
  border-radius: 11px;
  background: var(--surface, #fff);
  color: #1d1d1f;
  font-size: 14px;
}
.city-options button.selected { border-color: #0071e3; color: var(--accent, #0066cc); outline: 1px solid #0071e3; outline-offset: -2px; }
.custom-city { padding-top: 24px; }
.custom-city > span { display: block; margin-bottom: 8px; color: var(--muted, #6e6e73); font-size: 14px; }
.custom-city > div { display: flex; align-items: center; gap: 8px; }
.custom-city input { min-width: 0; font-size: 14px; padding: 10px 12px; }
.custom-city input:first-child { width: 30%; }
.custom-city input:nth-child(2) { flex: 1; }
.custom-city .button { min-height: 44px; white-space: nowrap; border-radius: 11px; }
.city-dialog footer { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-top: 24px; padding-top: 20px; border-top: 1px solid var(--line, #e0e0e0); }
.city-dialog footer > span { color: var(--muted, #6e6e73); font-size: 14px; }
.city-dialog footer .button { min-height: 44px; border-radius: 999px; box-shadow: none; }
.modal-enter-active, .modal-leave-active { transition: opacity 0.2s; }
.modal-enter-active .city-dialog, .modal-leave-active .city-dialog { transition: transform 0.2s; }
.modal-enter-from, .modal-leave-to { opacity: 0; }
.modal-enter-from .city-dialog, .modal-leave-to .city-dialog { transform: translateY(12px); }
@media (max-width: 1100px) {
  .collection-main-fields { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto; }
  .keyword-section { grid-column: 1 / -1; }
}
@media (max-width: 640px) {
  .collection-composer { padding: 20px; }
  .collection-main-fields { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px 12px; }
  .start-button { grid-column: 1 / -1; width: 100%; }
  .collection-composer select, .city-control { padding-left: 10px; font-size: 14px; }
  .city-control { gap: 5px; }
  .keyword-field input { font-size: 16px; }
  .collection-utilities { align-items: flex-start; gap: 0 12px; }
  .browser-connection { flex-wrap: wrap; gap: 0 8px; }
  .browser-status { font-size: 12px; }
  .advanced-fields { grid-template-columns: minmax(0, 1fr); }
  .form-filter-columns { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .modal-overlay { padding: 16px; }
  .city-dialog { max-height: calc(100dvh - 32px); padding: 20px; }
  .city-options { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  .custom-city > div { flex-wrap: wrap; }
  .custom-city input:first-child { width: 32%; }
  .custom-city .button { margin-left: auto; }
}
@media (prefers-reduced-motion: reduce) {
  .advanced-toggle > svg:last-child,
  .modal-enter-active, .modal-leave-active,
  .modal-enter-active .city-dialog, .modal-leave-active .city-dialog { transition: none; }
}
</style>
