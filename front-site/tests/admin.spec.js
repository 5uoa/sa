import { expect, test } from '@playwright/test'

const API = 'http://127.0.0.1:8100'
const stamp = Date.now().toString(36)

/**
 * 后台接口直连工具：用于清理 E2E 产生的临时数据
 * 页面所有操作仍走 UI，这里只做兜底清理
 */
async function apiPost(request, path, body = {}) {
  const response = await request.post(`${API}${path}`, { data: body })
  return (await response.json()).data
}

async function removeByName(request, kind, name) {
  const items = (await apiPost(request, `/front/admin/${kind}/list`)).items
  const target = items.find((item) => item.name === name)
  if (target) await apiPost(request, `/front/admin/${kind}/delete`, { id: target.id })
}

/** 等待 Nuxt 水合完成，避免首屏 SSR 元素上的点击早于事件绑定 */
async function gotoAdmin(page) {
  await page.goto('/admin')
  await page.waitForFunction(() => {
    const root = document.querySelector('#__nuxt')
    return Boolean(root && root.__vue_app__)
  })
}

async function openSection(page, name) {
  await gotoAdmin(page)
  await page.getByRole('navigation', { name: '管理后台模块' }).getByRole('button', { name }).click()
}

test.describe.configure({ mode: 'serial' })

test.describe('管理后台', () => {
  test.skip(({ viewport }) => (viewport?.width ?? 0) < 1200, '管理后台仅桌面端验证')

  test('用户与角色：邀请、改角色、启停、搜索、移除均持久化', async ({ page }) => {
    await gotoAdmin(page)

    const rows = page.locator('table tbody tr')
    await expect(rows.first()).toBeVisible()
    await expect.poll(() => rows.count(), { timeout: 15000 }).toBeGreaterThanOrEqual(6)

    const memberName = `e2e-${stamp}`
    const email = `${memberName}@xf.cn`

    await page.getByRole('button', { name: '邀请成员' }).click()
    await page.getByLabel('邮箱', { exact: true }).fill(email)
    await page.getByLabel('角色', { exact: true }).click()
    await page.getByRole('option', { name: '访客' }).click()
    await page.getByRole('button', { name: '发送邀请' }).click()

    const row = page.locator('table tbody tr', { hasText: email })
    await expect(row).toBeVisible()
    await expect(row).toContainText('访客')

    // 角色修改落库：刷新后仍为管理员
    await page.getByLabel(`${memberName} 的角色`).click()
    await page.getByRole('option', { name: '管理员' }).click()
    await page.reload()
    await expect(page.locator('table tbody tr', { hasText: email })).toContainText('管理员')

    // 停用落库：刷新后仍为停用
    await page
      .locator('table tbody tr', { hasText: email })
      .getByRole('button', { name: '停用' })
      .click()
    await expect(page.locator('table tbody tr', { hasText: email })).toContainText('停用')
    await page.reload()
    await expect(page.locator('table tbody tr', { hasText: email })).toContainText('停用')

    // 搜索过滤
    await page.getByLabel('搜索用户或邮箱').fill(memberName)
    await expect(page.locator('table tbody tr')).toHaveCount(1)
    await page.getByLabel('搜索用户或邮箱').fill('')

    // 移除
    await page
      .locator('table tbody tr', { hasText: email })
      .getByRole('button', { name: '移除' })
      .click()
    await expect(page.locator('table tbody tr', { hasText: email })).toHaveCount(0)
  })

  test('模型：API Key 掩码入库、真实测试提示、编辑占位与删除', async ({ page, request }) => {
    const name = `e2e-model-${stamp}`
    try {
      await openSection(page, '模型')
      await page.getByRole('button', { name: '新增' }).click()
      await page.getByLabel('名称').fill(name)
      await page.getByLabel('描述').fill('E2E 临时模型')
      await page.getByLabel('API 地址').fill('https://api.deepseek.com')
      await page.getByLabel('上下文').fill('E2E 上下文')
      await page.getByLabel('API Key').fill('sk-e2e-invalid-0001')
      await page.getByRole('button', { name: '保存' }).click()

      const card = page.locator('li', { hasText: name })
      await expect(card).toBeVisible()
      await expect(card).toContainText('API Key：sk-e****0001')
      await expect(card).toContainText('未测试')

      // 真实请求供应商：无效 Key 必然返回失败
      await card.getByRole('button', { name: '测试' }).click()
      await expect(page.locator('[role="status"]', { hasText: name })).toContainText('测试失败')
      await expect(card).toContainText('异常')

      await card.getByRole('button', { name: '编辑' }).click()
      await expect(page.getByLabel('API Key')).toHaveAttribute(
        'placeholder',
        /已保存 sk-e\*\*\*\*0001/
      )
      await page.getByRole('button', { name: '取消' }).click()

      await card.getByRole('button', { name: '删除' }).click()
      await expect(card).toHaveCount(0)
    } finally {
      await removeByName(request, 'models', name)
    }
  })

  test('MCP：新增、真实端点探测可用、删除', async ({ page, request }) => {
    const name = `e2e-mcp-${stamp}`
    try {
      await openSection(page, 'MCP')
      await page.getByRole('button', { name: '新增' }).click()
      await page.getByLabel('名称').fill(name)
      await page.getByLabel('描述').fill('E2E 临时 MCP')
      await page.getByLabel('启动命令或 URL').fill('http://127.0.0.1:8100/health')
      await page.getByRole('button', { name: '保存' }).click()

      const card = page.locator('li', { hasText: name })
      await expect(card).toBeVisible()

      await card.getByRole('button', { name: '测试' }).click()
      await expect(page.locator('[role="status"]', { hasText: name })).toContainText('测试通过')
      await expect(card).toContainText('可用')

      await card.getByRole('button', { name: '删除' }).click()
      await expect(card).toHaveCount(0)
    } finally {
      await removeByName(request, 'mcp', name)
    }
  })

  test('SKILL：新增、完整性测试可用、删除', async ({ page, request }) => {
    const name = `e2e-skill-${stamp}`
    try {
      await openSection(page, 'SKILL')
      await page.getByRole('button', { name: '新增' }).click()
      await page.getByLabel('名称').fill(name)
      await page.getByLabel('描述').fill('E2E 临时 SKILL')
      await page.getByRole('button', { name: '保存' }).click()

      const card = page.locator('li', { hasText: name })
      await expect(card).toBeVisible()

      await card.getByRole('button', { name: '测试' }).click()
      await expect(page.locator('[role="status"]', { hasText: name })).toContainText('测试通过')
      await expect(card).toContainText('可用')

      await card.getByRole('button', { name: '删除' }).click()
      await expect(card).toHaveCount(0)
    } finally {
      await removeByName(request, 'skills', name)
    }
  })

  test('专家：新增、保存并测试真实返回、刷新持久、删除', async ({ page, request }) => {
    const name = `e2e-expert-${stamp}`
    try {
      await openSection(page, '专家')
      await page.getByRole('button', { name: '新增' }).click()
      await page.getByLabel('名称').fill(name)
      await page.getByLabel('职责').fill('E2E 临时专家')
      await page.getByRole('button', { name: '创建' }).click()

      await expect(page.getByText('配置专家')).toBeVisible()
      await page.getByRole('button', { name: '保存并测试' }).click()
      await expect(page.locator('[role="status"]', { hasText: '测试未通过' })).toBeVisible()
      await page.getByRole('button', { name: '取消' }).click()

      await openSection(page, '专家')
      const card = page.locator('li', { hasText: name })
      await expect(card).toBeVisible()

      await card.getByRole('button', { name: '删除' }).click()
      await expect(card).toHaveCount(0)
    } finally {
      await removeByName(request, 'experts', name)
    }
  })

  test('额度总览：摘要卡、本月用量与按项目分配均来自接口', async ({ page }) => {
    await openSection(page, '额度总览')

    for (const label of ['团队总额度', '本月已用', '剩余额度', '下次重置']) {
      await expect(page.getByText(label, { exact: true })).toBeVisible()
    }

    await expect(page.getByText('本月用量')).toBeVisible()
    await expect(page.getByText(/¥[\d,]+ \/ ¥[\d,]+/).first()).toBeVisible()
    await expect(page.getByText('按项目分配')).toBeVisible()
    await expect(page.locator('ul li')).toHaveCount(4)
  })

  test('操作日志：展示字段、条数与刷新，且包含成员变更记录', async ({ page }) => {
    await openSection(page, '操作日志')

    const rows = page.locator('table tbody tr')
    await expect(rows.first()).toBeVisible()
    expect(await rows.count()).toBeGreaterThan(0)

    await expect(page.getByText(/最近 \d+ 条/)).toBeVisible()
    await expect(page.locator('table thead')).toContainText('时间')
    await expect(page.locator('table thead')).toContainText('操作人')
    await expect(page.locator('table thead')).toContainText('操作')
    await expect(page.locator('table thead')).toContainText('对象')

    await expect(page.locator('table tbody')).toContainText('修改成员')

    await page.getByRole('button', { name: '刷新' }).click()
    await expect(rows.first()).toBeVisible()
  })
})
