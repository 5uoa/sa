// 站点框架配置：Nuxt4 + @nuxtjs/seo，默认 SSG（prerender）优先
// SITE_URL 由 .env.* 注入；仅本地开发可回退 localhost，生产构建缺失则直接失败
const siteUrl = process.env.SITE_URL || 'http://localhost:3000'
const isBuildCommand = process.argv.some((arg) => arg === 'build' || arg === 'generate')

if (isBuildCommand && !process.env.SITE_URL) {
  throw new Error('[env] 缺少 SITE_URL：请在 .env.production 或部署平台注入生产域名后再执行构建。')
}

export default defineNuxtConfig({
  compatibilityDate: '2026-11-04',

  devtools: { enabled: false },

  modules: ['@nuxt/eslint', '@nuxtjs/seo', '@nuxt/ui'],

  site: {
    url: siteUrl,
    name: 'xf',
    description: 'xf front site',
    defaultLocale: 'en'
  },

  // main.css 只引入 Tailwind 与 Nuxt UI 默认主题，并声明品牌色板
  css: ['~/assets/css/main.css'],

  app: {
    head: {
      link: [{ rel: 'icon', type: 'image/png', href: '/favicon.png' }]
    }
  },

  // 接口基址由环境变量注入，未配置时请求直接报错，不回退假数据
  runtimeConfig: {
    public: {
      apiBase: process.env.NUXT_PUBLIC_API_BASE || '',
      authDisabled: process.env.NUXT_PUBLIC_AUTH_DISABLED === 'true'
    }
  },

  routeRules: {
    '/': { prerender: true }
  },

  nitro: {
    compressPublicAssets: true,
    prerender: {
      routes: ['/'],
      crawlLinks: true,
      failOnError: true
    }
  },

  experimental: {
    ssrStreaming: false
  },

  robots: {
    allow: ['/'],
    disallow: ['/admin', '/api']
  },

  sitemap: {
    autoLastmod: true
  },

  typescript: {
    strict: true
  }
})
