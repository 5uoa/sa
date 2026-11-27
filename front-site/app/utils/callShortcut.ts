/** 通话设置中的停止播音快捷键识别规则。 */
export function normalizeCallShortcutKey(value: string | undefined) {
  const key = (value || 'Escape').trim()
  const lowered = key.toLowerCase()
  if (lowered === 'esc' || lowered === 'escape') return 'Escape'
  if (lowered === 'fn' || lowered === 'globe') return 'Fn'
  if (key === ' ') return 'Space'
  return key
}

export function callShortcutKeyLabel(value: string | undefined) {
  const labels: Record<string, string> = {
    Escape: 'Esc',
    Space: '空格',
    Fn: 'Fn',
    F2: 'F2',
    F8: 'F8',
    KeyV: 'V',
    KeyQ: 'Q'
  }
  const key = normalizeCallShortcutKey(value)
  return labels[key] || key
}

function hasFnModifier(event: KeyboardEvent) {
  for (const modifier of ['Fn', 'FnLock', 'Globe', 'GlobeLock']) {
    try {
      if (event.getModifierState?.(modifier) === true) return true
    } catch {
      // 部分浏览器对未知 modifier 会抛异常，忽略即可。
    }
  }
  return false
}

export function isFnKeyEvent(event: KeyboardEvent) {
  return (
    event.code === 'Fn' ||
    event.code === 'FnLock' ||
    event.code === 'Globe' ||
    event.code === 'GlobeLock' ||
    event.key === 'Fn' ||
    event.key === 'FnLock' ||
    event.key === 'Globe' ||
    event.key === 'GlobeLock' ||
    event.keyCode === 63 ||
    event.which === 63 ||
    hasFnModifier(event)
  )
}

export function isCallShortcutKeyEvent(event: KeyboardEvent, value: string | undefined) {
  const configured = normalizeCallShortcutKey(value)
  if (configured === 'Fn') return isFnKeyEvent(event)
  return (
    event.code === configured ||
    event.key === configured ||
    (configured === 'Space' && event.key === ' ')
  )
}
