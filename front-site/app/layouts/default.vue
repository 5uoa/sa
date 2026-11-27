<script setup lang="ts">
/** 全局布局壳：页头 → 主内容 → 页脚，页面可覆盖 header / footer 插槽 */
import { siteConfig } from '~/utils/siteConfig'
</script>

<template>
  <div class="flex min-h-screen flex-col bg-default">
    <header class="border-b border-default px-4 py-3">
      <slot name="header">
        <NuxtLink to="/" class="text-sm font-semibold text-default">
          {{ siteConfig.name }}
        </NuxtLink>
      </slot>
    </header>

    <main id="main-content" class="flex-1 p-4">
      <slot />
    </main>

    <footer class="border-t border-default px-4 py-3 text-xs text-muted">
      <slot name="footer">
        <p>© {{ new Date().getFullYear() }} {{ siteConfig.name }}</p>
      </slot>
    </footer>
  </div>
</template>
