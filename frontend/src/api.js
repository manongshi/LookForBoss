export const API_BASE_URL = (
  import.meta.env.PROD ? '/api' : (import.meta.env.VITE_API_BASE_URL || '/api')
).replace(/\/+$/, '')

export function apiUrl(path) {
  return `${API_BASE_URL}/${path.replace(/^\/+/, '')}`
}

export function apiHeaders(headers = {}) {
  return {
    'Content-Type': 'application/json',
    ...headers,
  }
}

export function eventUrl(path) {
  const url = new URL(apiUrl(path), window.location.origin)
  return url.toString()
}

export async function request(path, options = {}) {
  const { timeout = 45000, ...init } = options
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  try {
    const response = await fetch(apiUrl(path), {
      ...init,
      headers: apiHeaders(init.headers),
      signal: controller.signal,
    })
    const body = await response.json().catch(() => null)
    if (!response.ok) {
      let detail = body?.detail
      if (Array.isArray(detail)) detail = detail.map(item => item.msg).join('；')
      throw new Error(typeof detail === 'string' ? detail : '服务暂时不可用，请稍后重试')
    }
    return body
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('请求等待超时，请稍后刷新状态')
    if (error instanceof TypeError) throw new Error('无法连接本地服务，请重新打开应用或启动本地服务后重试')
    throw error
  } finally {
    clearTimeout(timer)
  }
}

export function post(path, body, options = {}) {
  return request(path, { ...options, method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })
}
