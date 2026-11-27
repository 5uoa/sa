import { ensureAdminSession } from '~/composables/useAdminSession'

export default defineNuxtRouteMiddleware(async (to) => {
  if (import.meta.server) return
  const config = useRuntimeConfig()
  if (config.public.authDisabled) return
  const user = await ensureAdminSession()
  if (!user) {
    return navigateTo({ path: '/login', query: { redirect: to.fullPath } })
  }
  if (user.mustChangePassword && to.path !== '/change-password') {
    return navigateTo('/change-password')
  }
  if (!user.mustChangePassword && to.path === '/change-password') {
    return navigateTo((to.query.redirect as string) || '/admin')
  }
})
