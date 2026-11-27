<script setup lang="ts">
/** 工作台单列：标题 + 数量 + 行列表（行内容由页面通过默认插槽传入）；可横向折叠为窄条 */
import { computed, useId } from 'vue'

const props = withDefaults(
  defineProps<{
    title: string
    count: number
    /** 是否折叠：折叠后列宽由父级栅格收窄，标题按每行两字横排 */
    collapsed?: boolean
    /** 是否允许折叠（会话列不折叠） */
    collapsible?: boolean
    /** 隐藏内容区滚动条，仍保留滚动能力 */
    hideScrollbar?: boolean
  }>(),
  { collapsed: false, collapsible: true, hideScrollbar: false }
)

const emit = defineEmits<{ toggle: [] }>()

const listId = useId()
/** 折叠态窄条内不显示分隔斜杠，避免单独成行 */
const railTitle = computed(() => props.title.replace(/\//g, ''))
</script>

<template>
  <section
    class="relative flex min-h-0 min-w-0 flex-col overflow-hidden bg-default"
    :aria-label="title"
  >
    <header
      class="flex h-12 flex-none items-center gap-2.5 border-b border-default px-4"
      :class="collapsed ? 'justify-center px-0' : ''"
    >
      <h2
        class="text-sm font-semibold text-highlighted"
        :class="collapsed ? 'truncate text-center' : ''"
      >
        {{ collapsed ? railTitle : title }}
      </h2>
      <UBadge v-if="!collapsed" color="neutral" variant="subtle" size="sm">{{ count }}</UBadge>
      <div v-if="!collapsed" class="ms-auto flex flex-none items-center gap-1">
        <slot name="action" />
      </div>
    </header>

    <div
      :id="listId"
      class="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto px-2 pt-2 pb-4 max-[1359px]:flex-none max-[1359px]:overflow-visible"
      :class="[
        collapsed ? 'items-center' : '',
        hideScrollbar ? '[scrollbar-width:none] [&::-webkit-scrollbar]:hidden' : ''
      ]"
      :aria-hidden="collapsed"
    >
      <slot />
      <div v-if="count === 0" class="px-2 py-1 text-xs leading-relaxed text-dimmed">暂无内容</div>
    </div>

    <slot name="footer" />

    <button
      v-if="collapsible !== false"
      type="button"
      class="absolute bottom-2 start-2 z-10 inline-flex size-8 items-center justify-center rounded-full border border-default bg-default text-muted transition-colors hover:bg-elevated/60 hover:text-default focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary max-[1359px]:hidden"
      :aria-expanded="!collapsed"
      :aria-controls="listId"
      :aria-label="collapsed ? `展开${title}` : `收起${title}`"
      @click="emit('toggle')"
    >
      <svg
        class="size-4 transition-transform"
        :class="collapsed ? 'rotate-180' : ''"
        viewBox="0 0 16 16"
        fill="none"
        aria-hidden="true"
      >
        <path
          d="M9.5 3.5 6 8l3.5 4.5"
          stroke="currentColor"
          stroke-width="1.4"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    </button>
  </section>
</template>
