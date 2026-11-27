<script setup lang="ts">
/** 全屏文件预览：展示文件信息与预览占位，原型环境未接入真实文件内容 */
interface PreviewFile {
  title: string
  ext: string
  meta: string
}

defineProps<{ file: PreviewFile | null }>()
const open = defineModel<boolean>('open', { default: false })
</script>

<template>
  <UModal
    v-model:open="open"
    fullscreen
    title="文件预览"
    :ui="{ body: 'flex-1 overflow-y-auto bg-elevated/40 p-4 sm:p-8' }"
  >
    <template #body>
      <div v-if="file" class="flex min-h-full justify-center">
        <article class="flex w-full max-w-3xl flex-col gap-6 rounded-lg bg-default p-6 sm:p-10">
          <header class="flex items-start gap-4 border-b border-default pb-5">
            <svg
              class="mt-0.5 size-8 shrink-0 text-dimmed"
              viewBox="0 0 16 16"
              fill="none"
              aria-hidden="true"
            >
              <path
                d="M4 1.5h5.5L13 5v9.5a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-12a1 1 0 0 1 1-1Z"
                stroke="currentColor"
                stroke-width="1.2"
                stroke-linejoin="round"
              />
              <path
                d="M9.5 1.5V5H13"
                stroke="currentColor"
                stroke-width="1.2"
                stroke-linejoin="round"
              />
            </svg>
            <div class="flex min-w-0 flex-col gap-1">
              <h2 class="text-xl font-semibold break-words text-highlighted">{{ file.title }}</h2>
              <p class="text-sm text-muted">{{ file.ext }} · {{ file.meta }}</p>
            </div>
          </header>

          <div
            class="flex flex-1 flex-col items-center justify-center gap-2 rounded-md border border-dashed border-default px-6 py-20 text-center"
          >
            <p class="text-sm font-medium text-default">暂无文件内容</p>
            <p class="text-xs leading-relaxed text-muted">
              原型演示环境未接入真实文件，仅展示文件信息
            </p>
          </div>
        </article>
      </div>
    </template>
  </UModal>
</template>
