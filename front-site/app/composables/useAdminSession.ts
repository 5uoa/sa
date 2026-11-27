export interface AdminUser {
  id: string
  name: string
  email: string
  role: string
  mustChangePassword: boolean
}

interface ApiEnvelope<T> {
  code: number
  message: string
  data: T
}

const TOKEN_KEY = 'xf_admin_token'
const USER_KEY = 'xf_admin_user'

export function getAdminToken() {
  return import.meta.client ? localStorage.getItem(TOKEN_KEY) || '' : ''
}

function saveAdminUser(user: AdminUser | null) {
  if (!import.meta.client) return
  if (user) localStorage.setItem(USER_KEY, JSON.stringify(user))
  else localStorage.removeItem(USER_KEY)
}

function readAdminUser(): AdminUser | null {
  if (!import.meta.client) return null
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || 'null') as AdminUser | null
  } catch {
    return null
  }
}

export async function refreshAdminSession(): Promise<AdminUser | null> {
  const token = getAdminToken()
  if (!token) return null
  const config = useRuntimeConfig()
  try {
    const response = await $fetch<ApiEnvelope<AdminUser>>('/front/admin/auth/me', {
      baseURL: config.public.apiBase as string,
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` }
    })
    if (response.code !== 200) throw new Error(response.message)
    saveAdminUser(response.data)
    return response.data
  } catch {
    clearAdminSession()
    return null
  }
}

export async function developmentAdminLogin(): Promise<AdminUser | null> {
  const config = useRuntimeConfig()
  try {
    const response = await $fetch<{
      code: number
      message: string
      data: { token: string; user: AdminUser }
    }>('/front/admin/auth/dev-login', {
      baseURL: config.public.apiBase as string,
      method: 'POST'
    })
    if (response.code !== 200) throw new Error(response.message)
    persistAdminSession(response.data.token, response.data.user)
    return response.data.user
  } catch {
    return null
  }
}

export async function ensureAdminSession(): Promise<AdminUser | null> {
  return (await refreshAdminSession()) || (await developmentAdminLogin())
}

export function persistAdminSession(token: string, user: AdminUser) {
  if (!import.meta.client) return
  localStorage.setItem(TOKEN_KEY, token)
  saveAdminUser(user)
}

export function clearAdminSession() {
  if (!import.meta.client) return
  localStorage.removeItem(TOKEN_KEY)
  saveAdminUser(null)
}

export function useAdminSession() {
  const user = useState<AdminUser | null>('admin-user', () => readAdminUser())
  return {
    user,
    refresh: async () => {
      user.value = await ensureAdminSession()
      return user.value
    },
    logout: () => {
      clearAdminSession()
      user.value = null
    }
  }
}
