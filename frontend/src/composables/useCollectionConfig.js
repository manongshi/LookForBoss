import { computed, onMounted, reactive, ref, watch } from 'vue'
import { request } from '../api'
import { platformNames } from '../constants/platforms'

export function useCollectionConfig() {
  const platforms = ref([])
  const optionsReady = ref(false)
  const config = reactive({
    platform: 'boss', name: '', keywords: ['Python开发'], cityCodes: [],
    max_jobs: 200, max_scrolls: 100, delay_min: 8, delay_max: 15,
    salary: '', experience: '', degree: '', scale: '',
  })
  const customCities = ref({})
  const currentPlatform = computed(() => platforms.value.find(item => item.id === config.platform))
  const cityOptions = computed(() => [
    ...(currentPlatform.value?.cities || []),
    ...(customCities.value[config.platform] || []).filter(city =>
      !currentPlatform.value?.cities.some(item => item.code === city.code)),
  ])
  const filterOptions = computed(() => currentPlatform.value?.filters || {})
  const selectedCities = computed(() => config.cityCodes.map(code => cityOptions.value.find(city => city.code === code)).filter(Boolean))
  try {
    const saved = JSON.parse(localStorage.getItem('findboss-config') || 'null')
    if (saved && Array.isArray(saved.keywords) && Array.isArray(saved.cityCodes)) {
      for (const key of Object.keys(config)) if (Object.hasOwn(saved, key)) config[key] = saved[key]
      if (!platformNames[config.platform]) config.platform = 'boss'
    }
    const savedCities = JSON.parse(localStorage.getItem('findboss-platform-cities') || '{}')
    if (savedCities && typeof savedCities === 'object' && !Array.isArray(savedCities)) customCities.value = savedCities
    const legacy = JSON.parse(localStorage.getItem('findboss-cities') || '[]')
    if (!customCities.value.boss && Array.isArray(legacy)) customCities.value.boss = legacy.filter(city => /^\d{9}$/.test(city?.code))
  } catch { /* 保留默认配置。 */ }

  function defaultCity() {
    const shanghai = cityOptions.value.find(city => city.name === '上海')
    config.cityCodes = shanghai ? [shanghai.code] : cityOptions.value.slice(0, 1).map(city => city.code)
  }
  watch(() => config.platform, () => {
    for (const field of ['salary', 'experience', 'degree', 'scale']) config[field] = ''
    defaultCity()
  }, { flush: 'sync' })
  watch(config, value => {
    try { localStorage.setItem('findboss-config', JSON.stringify(value)) } catch { /* 本地存储可能被禁用。 */ }
  }, { deep: true })
  watch(customCities, value => {
    try { localStorage.setItem('findboss-platform-cities', JSON.stringify(value)) } catch { /* 本地存储可能被禁用。 */ }
  }, { deep: true })

  async function loadOptions() {
    const supplied = await request('/platforms')
    platforms.value = supplied
    optionsReady.value = true
    config.cityCodes = config.cityCodes.filter(code => cityOptions.value.some(city => city.code === code))
    if (!config.cityCodes.length) defaultCity()
    for (const field of ['salary', 'experience', 'degree', 'scale']) {
      if (config[field] && !filterOptions.value[field]?.some(item => item.code === config[field])) config[field] = ''
    }
  }
  onMounted(() => loadOptions().catch(() => { optionsReady.value = false }))
  function addCity(city) {
    const list = customCities.value[config.platform] ||= []
    if (!cityOptions.value.some(item => item.code === city.code)) list.push(city)
  }
  function reuseConfig(saved) {
    config.platform = saved.platform || 'boss'
    for (const city of saved.cities || []) addCity(city)
    for (const key of Object.keys(config)) {
      if (Object.hasOwn(saved, key)) config[key] = saved[key]
    }
    config.cityCodes = (saved.cities || []).map(city => city.code)
    config.name = ''
  }
  return { config, platforms, optionsReady, currentPlatform, filterOptions, cityOptions, selectedCities, addCity, reuseConfig, loadOptions }
}
