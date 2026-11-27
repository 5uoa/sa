import { expect, test } from '@playwright/test'

const COLUMNS = ['项目', '任务包', '任务', '会话', '附件']

/** 收集控制台错误与未捕获异常，验证首页运行时无报错 */
function trackErrors(page) {
  const errors = []
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })
  page.on('pageerror', (error) => errors.push(error.message))
  return errors
}

test.describe('首页 SEO 与结构', () => {
  test('服务端输出包含标题、描述、H1 与结构化数据', async ({ request }) => {
    const response = await request.get('/')
    expect(response.status()).toBe(200)
    const html = await response.text()

    expect(html).toContain('<title>项目工作台')
    expect(html).toContain('name="description"')
    expect(html).toContain('property="og:title"')
    expect(html).toContain('property="og:image"')
    expect(html).toContain('application/ld+json')

    const h1Count = (html.match(/<h1[\s>]/g) ?? []).length
    expect(h1Count).toBe(1)
    expect(html).toContain('项目工作台')
  })

  test('五栏按固定顺序渲染且内容正确', async ({ page }) => {
    const errors = trackErrors(page)
    await page.goto('/')

    await expect(page.locator('h1')).toHaveText('项目工作台')
    await expect(page.locator('.wb-column')).toHaveCount(5)
    await expect(page.locator('.wb-column__title')).toHaveText(COLUMNS)
    await expect(page.locator('.wb-column__count')).toHaveText(['3', '3', '3', '5', '3'])
    await expect(page.locator('.wb-row')).toHaveCount(12)

    expect(errors).toEqual([])
  })

  test('进入首页默认选中第一个项目及其下属首项', async ({ page }) => {
    await page.goto('/')

    const activeTitles = await page.locator('.wb-row--active .wb-row__title').allTextContents()
    expect(activeTitles).toEqual(['品牌年度内容规划', 'M2 内容策略定稿', '梳理核心信息屋'])
    await expect(page.locator('.wb-row--active')).toHaveCount(3)
  })

  test('逐级下钻：选中上级后右侧列切换为该条目的下一级内容', async ({ page }) => {
    await page.goto('/')
    await page.waitForSelector('.workbench[data-ready="true"]')

    const columnTitles = (index) =>
      page.locator('.wb-column').nth(index).locator('.wb-row__title').allTextContents()

    await page.getByRole('button', { name: /新品上市传播/ }).click()
    await expect(page.locator('.wb-column').nth(1).locator('.wb-row__title')).toHaveText([
      'M1 上市节奏确认',
      'M2 首波传播执行'
    ])
    await expect(page.locator('.wb-column').nth(2).locator('.wb-row__title')).toHaveText([
      '上市时间线锁定',
      '预热物料清单'
    ])
    await expect(page.locator('.wb-column__count')).toHaveText(['3', '2', '2', '0', '1'])

    await page.getByRole('button', { name: /M2 首波传播执行/ }).click()
    await expect(page.locator('.wb-column').nth(2).locator('.wb-row__title')).toHaveText([
      '首波通稿撰写',
      'KOL 名单对接'
    ])

    await page.getByRole('button', { name: /首波通稿撰写/ }).click()
    // 会话与任务一对一：会话列不再有会话条目，直接展示该任务的会话流（此处为空）
    expect(await columnTitles(3)).toEqual([])
    expect(await columnTitles(4)).toEqual(['通稿框架.md'])
  })

  test('会话记录底部对话框：发送后追加消息并靠右显示', async ({ page }) => {
    await page.goto('/')
    await page.waitForSelector('.workbench[data-ready="true"]')

    const sessionColumn = page.locator('.wb-column').nth(3)
    const input = page.getByPlaceholder('输入消息...')

    // 发送按钮已移除，仅保留回车发送
    await expect(page.getByRole('button', { name: '发送' })).toHaveCount(0)

    const before = await sessionColumn.locator('.wb-thread__item').count()

    await input.fill('把信息屋同步给设计组')
    await input.press('Enter')

    await expect(sessionColumn.locator('.wb-thread__item')).toHaveCount(before + 1)
    const mine = sessionColumn.locator('.wb-thread__item').last()
    await expect(mine).toHaveText('把信息屋同步给设计组')
    await expect(mine).toHaveClass(/is-me/)
    await expect(sessionColumn.locator('.wb-row')).toHaveCount(0)
    await expect(input).toHaveValue('')
  })

  test('对话框支持添加附件并在发送后追加消息', async ({ page }) => {
    await page.goto('/')
    await page.waitForSelector('.workbench[data-ready="true"]')

    const sessionColumn = page.locator('.wb-column').nth(3)

    await page.locator('.wb-composer__upload-input').setInputFiles([
      { name: '信息屋-标注版.docx', mimeType: 'application/octet-stream', buffer: Buffer.from('a') },
      { name: '评审截图.png', mimeType: 'image/png', buffer: Buffer.from('b') }
    ])
    await expect(page.locator('.wb-composer__file')).toHaveCount(2)

    await page.getByPlaceholder('输入消息...').press('Enter')

    const mine = sessionColumn.locator('.wb-thread__item').last()
    await expect(mine).toHaveText('附件：信息屋-标注版.docx')
    await expect(mine).toHaveClass(/is-me/)
    await expect(page.locator('.wb-composer__file')).toHaveCount(0)
  })

  test('对话框支持语音通话开关', async ({ page }) => {
    await page.goto('/')
    await page.waitForSelector('.workbench[data-ready="true"]')

    const call = page.getByRole('button', { name: '语音通话' })
    await expect(call).toHaveAttribute('aria-pressed', 'false')

    await call.click()
    // 输入区原地切换为通话条：波形 + 计时 + 静音/扬声器/挂断
    await expect(page.locator('.wb-call')).toBeVisible()
    await expect(page.locator('.wb-call__timer')).toHaveText('00:00')
    await expect(page.getByRole('button', { name: '静音' })).toBeVisible()
    await expect(page.getByRole('button', { name: '关闭扬声器' })).toBeVisible()

    await page.getByRole('button', { name: '结束通话' }).click()
    await expect(page.locator('.wb-call')).toHaveCount(0)
    await expect(page.getByRole('button', { name: '语音通话' })).toHaveAttribute(
      'aria-pressed',
      'false'
    )
  })

  test('对话框可设置推理强度', async ({ page }) => {
    await page.goto('/')
    await page.waitForSelector('.workbench[data-ready="true"]')

    const select = page.locator('.wb-composer__select')
    await select.click()
    await page.getByRole('option', { name: '深度' }).click()
    await expect(select).toContainText('深度')

    await page.getByPlaceholder('输入消息...').fill('核对主文案的数据来源')
    await page.getByPlaceholder('输入消息...').press('Enter')
    await expect(select).toContainText('深度')
  })

  test('会话列可显示与隐藏文档编辑器', async ({ page, viewport }) => {
    await page.goto('/')
    await page.waitForSelector('.workbench[data-ready="true"]')

    await page.getByRole('button', { name: '显示文档编辑器' }).click()
    await expect(page.locator('.wb-editor')).toBeVisible()
    await expect(page.locator('.wb-editor [data-slate-editor]')).toBeVisible()

    // 宽屏：编辑器不覆盖会话列，两者均分自适应宽度
    if ((viewport?.width ?? 0) >= 1360) {
      const session = await page.locator('.wb-column').nth(3).boundingBox()
      const editor = await page.locator('.wb-editor').boundingBox()
      expect(Math.abs(session.width - editor.width)).toBeLessThanOrEqual(1)
      expect(editor.x).toBeGreaterThanOrEqual(session.x + session.width - 1)
    }

    await page.getByRole('button', { name: '关闭文档编辑器' }).click()
    await expect(page.locator('.wb-editor')).toHaveCount(0)
  })

  test('可新增项目、任务包与任务', async ({ page }) => {
    await page.goto('/')
    await page.waitForSelector('.workbench[data-ready="true"]')

    const columns = page.locator('.wb-column')

    await columns.nth(0).getByRole('button', { name: '新增' }).click()
    await page.getByPlaceholder('项目名称').fill('客户年度直播')
    await page.getByRole('button', { name: '确定' }).click()
    await expect(columns.nth(0).locator('.wb-row__title').last()).toHaveText('客户年度直播')
    await expect(columns.nth(0).locator('.wb-row--active .wb-row__title')).toHaveText('客户年度直播')
    await expect(columns.nth(1).locator('.wb-row')).toHaveCount(0)

    await columns.nth(1).getByRole('button', { name: '新增' }).click()
    await page.getByPlaceholder('任务包名称').fill('M1 直播策略')
    await page.getByRole('button', { name: '确定' }).click()
    await expect(columns.nth(1).locator('.wb-row__title')).toHaveText(['M1 直播策略'])
    await expect(columns.nth(2).locator('.wb-row')).toHaveCount(0)

    await columns.nth(2).getByRole('button', { name: '新增' }).click()
    await page.getByPlaceholder('任务名称').fill('确认直播排期')
    await page.getByRole('button', { name: '确定' }).click()
    await expect(columns.nth(2).locator('.wb-row__title')).toHaveText(['确认直播排期'])
    // 会话与任务一对一：会话列不再有会话条目，直接展示该任务的消息流（此处为空）
    await expect(columns.nth(3).locator('.wb-row')).toHaveCount(0)
    await expect(columns.nth(3).locator('.wb-thread__item')).toHaveCount(0)
    await expect(columns.nth(4).locator('.wb-row')).toHaveCount(0)

    await expect(columns.nth(0).locator('.wb-row--active .wb-row__meta')).toHaveText(
      '进行中 · 1 个任务包 · 1 个任务'
    )
    await expect(page.locator('.wb-column__count')).toHaveText(['4', '1', '1', '0', '0'])
  })

  test('已移除对话首页与账号入口等无关内容', async ({ page }) => {
    await page.goto('/')

    await expect(page.getByPlaceholder('发消息...')).toHaveCount(0)
    await expect(page.getByRole('button', { name: '登录' })).toHaveCount(0)
    await expect(page.locator('.chat-sidebar')).toHaveCount(0)
    await expect(page.locator('.prompt-suggestions')).toHaveCount(0)
  })

  test('无横向溢出', async ({ page }) => {
    await page.goto('/')
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    )
    expect(overflow).toBeLessThanOrEqual(0)
  })
})

test.describe('宽屏五栏并排', () => {
  test.skip(({ viewport }) => (viewport?.width ?? 0) < 1360, '仅宽屏用例')

  test('四栏固定 280px，会话记录列自适应填满剩余宽度', async ({ page }) => {
    await page.goto('/')
    const boxes = await page.locator('.wb-column').evaluateAll((nodes) =>
      nodes.map((node) => {
        const rect = node.getBoundingClientRect()
        return { x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width) }
      })
    )

    expect(boxes).toHaveLength(5)
    const tops = new Set(boxes.map((box) => box.y))
    expect(tops.size).toBe(1)

    const [project, milestone, task, session, attachment] = boxes.map((box) => box.width)
    for (const width of [project, milestone, task, attachment]) {
      expect(Math.abs(width - 280)).toBeLessThanOrEqual(1)
    }

    const board = await page.locator('.workbench__board').boundingBox()
    const { paddingLeft, paddingRight, columnGap } = await page
      .locator('.workbench__board')
      .evaluate((node) => {
        const style = getComputedStyle(node)
        return {
          paddingLeft: parseFloat(style.paddingLeft),
          paddingRight: parseFloat(style.paddingRight),
          columnGap: parseFloat(style.columnGap)
        }
      })
    const expectedSession = board.width - paddingLeft - paddingRight - columnGap * 4 - 280 * 4
    expect(Math.abs(session - expectedSession)).toBeLessThanOrEqual(1)
    expect(session).toBeGreaterThan(150)
  })
})

test.describe('窄屏单栏堆叠', () => {
  test.skip(({ viewport }) => (viewport?.width ?? 0) >= 768, '仅移动端用例')

  test('五栏纵向堆叠且占满宽度', async ({ page }) => {
    await page.goto('/')
    const boxes = await page.locator('.wb-column').evaluateAll((nodes) =>
      nodes.map((node) => {
        const rect = node.getBoundingClientRect()
        return { x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width) }
      })
    )

    expect(new Set(boxes.map((box) => box.x)).size).toBe(1)
    expect(boxes.every((box, index) => index === 0 || box.y > boxes[index - 1].y)).toBe(true)
    expect(boxes.every((box) => box.width === boxes[0].width)).toBe(true)
  })
})

test.describe('平板两栏换行', () => {
  test.skip(({ viewport }) => {
    const width = viewport?.width ?? 0
    return width < 768 || width >= 1200
  }, '仅平板用例')

  test('两列布局中五栏会换行排列', async ({ page }) => {
    await page.goto('/')
    const tops = await page.locator('.wb-column').evaluateAll((nodes) =>
      nodes.map((node) => Math.round(node.getBoundingClientRect().y))
    )

    expect(tops.filter((top) => top === tops[0])).toHaveLength(2)
  })
})
