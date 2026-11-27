<script setup lang="ts">
/** 全局错误页：404 与运行时异常的统一出口 */
import type { NuxtError } from '#app'

const props = defineProps<{ error: NuxtError }>()

const isNotFound = computed(() => props.error?.statusCode === 404)

function retry() {
  clearError({ redirect: useRoute().fullPath })
}
</script>

<template>
  <NuxtLayout>
    <div class="flex flex-col gap-3 py-10">
      <h1 class="text-2xl font-semibold text-highlighted">
        {{ isNotFound ? 'Page not found' : 'Something went wrong' }}
      </h1>
      <p class="text-sm text-muted">
        {{ isNotFound ? 'The page you requested does not exist.' : 'Please try again.' }}
      </p>
      <div class="flex gap-2">
        <UButton color="primary" @click="retry">Try again</UButton>
        <UButton to="/" color="neutral" variant="outline">Back to homepage</UButton>
      </div>
    </div>
  </NuxtLayout>
</template>
