import { marked, type Tokens } from 'marked'

const HTML_ESCAPES: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;'
}

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (char) => HTML_ESCAPES[char] ?? char)
}

/** 只放行 http(s)、mailto、锚点与相对路径，其余协议（javascript:、data: 等）在渲染前清空 */
function isSafeUrl(href: string): boolean {
  return /^(https?:|mailto:|#|\/|\.{1,2}\/)/i.test(href.trim())
}

/**
 * Markdown 渲染：同步输出，SSR 与客户端结果一致。
 * 文档可由用户直接编辑，因此原始 HTML 一律按文本输出，不安全协议链接在渲染前清空。
 */
marked.use({
  renderer: {
    html(token: Tokens.HTML | Tokens.Tag) {
      return escapeHtml(token.text)
    }
  },
  walkTokens(token) {
    if ((token.type === 'link' || token.type === 'image') && !isSafeUrl(token.href)) {
      token.href = ''
    }
  }
})

marked.setOptions({ gfm: true, breaks: false })

export function renderMarkdown(source: string): string {
  return marked.parse(source, { async: false })
}

/**
 * 把用户输入安全地嵌入 Markdown 文档：
 * 先转义 HTML 实体，再转义 Markdown 结构字符，避免用户文本改写文档结构或注入标签。
 */
export function escapeMarkdown(text: string): string {
  return escapeHtml(text).replace(/[\\`*_{}[\]()#+\-.!|~]/g, (char) => `\\${char}`)
}
