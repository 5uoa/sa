<script setup lang="ts">
/** 控制台页面布局：仅顶栏（返回工作台 / 标题 / 用户菜单），个人设置、管理后台、额度管理各自独立 */
const route = useRoute()

const title = computed(() => (route.meta.title as string | undefined) ?? '控制台')
</script>

<template>
  <div class="flex h-screen flex-col bg-elevated/40">
    <header
      class="flex h-14 flex-none items-center justify-between gap-3 border-b border-default bg-default px-4 max-[767px]:px-3"
    >
      <div class="flex min-w-0 items-center gap-3">
        <UButton to="/" color="neutral" variant="ghost">返回工作台</UButton>
        <USeparator orientation="vertical" class="h-5" />
        <h1 class="truncate text-lg font-semibold text-highlighted">{{ title }}</h1>
      </div>

      <AppUserMenu />
    </header>

    <main class="min-w-0 flex-1 overflow-y-auto p-6 max-[767px]:p-4">
      <slot />
    </main>
  </div>
</template>
