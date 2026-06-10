/**
 * XMind 导出工具
 *
 * XMind (.xmind) 文件本质是一个 ZIP 包，内含：
 * - content.xml: 思维导图内容
 * - META-INF/manifest.xml: 清单文件
 */
import JSZip from 'jszip'

/**
 * 生成 XMind content.xml
 * @param {Object} options
 * @param {string} options.title - 导图根节点标题
 * @param {Array<{caseId: string, scenario: string, precondition: string, steps: string, expected: string, priority: string}>} options.testCases - 测试用例数组
 * @returns {string} XML 字符串
 */
function buildContentXML({ title, testCases }) {
  const escapeXml = (str) => {
    if (!str) return ''
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&apos;')
  }

  let topicIdCounter = 0
  const nextId = () => `topic_${++topicIdCounter}`

  // 按优先级分组
  const priorityGroups = { P0: [], P1: [], P2: [], P3: [] }
  testCases.forEach((tc) => {
    const p = tc.priority || 'P2'
    if (priorityGroups[p]) {
      priorityGroups[p].push(tc)
    } else {
      priorityGroups.P2.push(tc)
    }
  })

  const priorityLabels = {
    P0: 'P0 - 最高优先级',
    P1: 'P1 - 高优先级',
    P2: 'P2 - 中优先级',
    P3: 'P3 - 低优先级'
  }

  // Build children topics XML
  let childrenXML = ''

  for (const [priority, cases] of Object.entries(priorityGroups)) {
    if (cases.length === 0) continue

    const priorityTopicId = nextId()
    childrenXML += `<topic id="${priorityTopicId}">`
    childrenXML += `<title>${escapeXml(priorityLabels[priority])} (${cases.length})</title>`
    childrenXML += '<children><topics type="attached">'

    for (const tc of cases) {
      const caseTopicId = nextId()
      const caseIdStr = tc.caseId || ''
      const scenarioStr = tc.scenario || tc.title || ''

      childrenXML += `<topic id="${caseTopicId}">`
      childrenXML += `<title>${escapeXml(caseIdStr + ' ' + scenarioStr)}</title>`
      childrenXML += '<children><topics type="attached">'

      // 前置条件
      if (tc.precondition) {
        const preId = nextId()
        childrenXML += `<topic id="${preId}">`
        childrenXML += `<title>前置条件</title>`
        childrenXML += '<children><topics type="attached">'
        const preLines = tc.precondition.split('\n').filter(Boolean)
        for (const line of preLines) {
          const lineId = nextId()
          childrenXML += `<topic id="${lineId}"><title>${escapeXml(line.trim())}</title></topic>`
        }
        childrenXML += '</topics></children>'
        childrenXML += `</topic>`
      }

      // 测试步骤
      if (tc.steps) {
        const stepsId = nextId()
        childrenXML += `<topic id="${stepsId}">`
        childrenXML += `<title>测试步骤</title>`
        childrenXML += '<children><topics type="attached">'
        const stepLines = tc.steps.split('\n').filter(Boolean)
        for (const line of stepLines) {
          const lineId = nextId()
          childrenXML += `<topic id="${lineId}"><title>${escapeXml(line.trim())}</title></topic>`
        }
        childrenXML += '</topics></children>'
        childrenXML += `</topic>`
      }

      // 预期结果
      if (tc.expected) {
        const expId = nextId()
        childrenXML += `<topic id="${expId}">`
        childrenXML += `<title>预期结果</title>`
        childrenXML += '<children><topics type="attached">'
        const expLines = tc.expected.split('\n').filter(Boolean)
        for (const line of expLines) {
          const lineId = nextId()
          childrenXML += `<topic id="${lineId}"><title>${escapeXml(line.trim())}</title></topic>`
        }
        childrenXML += '</topics></children>'
        childrenXML += `</topic>`
      }

      childrenXML += '</topics></children>'
      childrenXML += `</topic>`
    }

    childrenXML += '</topics></children>'
    childrenXML += `</topic>`
  }

  const rootId = nextId()
  const sheetId = nextId()

  return `<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<xmap-content xmlns="urn:xmind:xmap:xmlns:content:2.0" xmlns:fo="http://www.w3.org/1999/XSL/Format" xmlns:svg="http://www.w3.org/2000/svg" xmlns:xhtml="http://www.w3.org/1999/xhtml" xmlns:xlink="http://www.w3.org/1999/xlink" version="2.0">
  <sheet id="${sheetId}">
    <topic id="${rootId}" type="root">
      <title>${escapeXml(title)}</title>
      <children>
        <topics type="attached">
          ${childrenXML}
        </topics>
      </children>
    </topic>
    <title>Sheet 1</title>
  </sheet>
</xmap-content>`
}

/**
 * 生成 META-INF/manifest.xml
 */
function buildManifestXML() {
  return `<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<manifest xmlns="urn:xmind:xmap:xmlns:manifest:2.0">
  <file-entry full-path="content.xml" media-type="text/xml"/>
</manifest>`
}

/**
 * 导出 XMind 文件 (.xmind)
 *
 * @param {Object} options
 * @param {string} options.fileName - 导出的文件名 (无需 .xmind 后缀)
 * @param {string} options.title - 导图根节点标题
 * @param {Array} options.testCases - 测试用例数组，每项包含 { caseId, scenario, precondition, steps, expected, priority }
 */
export async function exportToXMind({ fileName, title, testCases }) {
  const zip = new JSZip()

  // 添加 content.xml
  zip.file('content.xml', buildContentXML({ title, testCases }))

  // 添加 META-INF/manifest.xml
  const metaFolder = zip.folder('META-INF')
  metaFolder.file('manifest.xml', buildManifestXML())

  // 生成 ZIP 并下载
  const blob = await zip.generateAsync({ type: 'blob' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${fileName}.xmind`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

/**
 * 从 Markdown 表格内容解析测试用例（用于 RequirementAnalysisView）
 *
 * @param {string} content - 生成的测试用例文本内容
 * @returns {Array} 测试用例对象数组
 */
export function parseTestCasesFromContent(content) {
  if (!content) return []

  // 去除 markdown 加粗标记
  const cleanContent = content.replace(/\*\*([^*]+)\*\*/g, '$1')
  const lines = cleanContent.split('\n')

  // 尝试表格格式解析
  const tableRows = []
  for (const line of lines) {
    const trimmed = line.trim()
    if (trimmed.includes('|') && !trimmed.includes('---')) {
      const cells = trimmed.split('|').map((c) => c.trim()).filter((c) => c)
      if (cells.length >= 2) {
        tableRows.push(cells)
      }
    }
  }

  if (tableRows.length >= 2) {
    // 表格格式
    const headers = tableRows[0].map((h) => h.toLowerCase())
    const result = []
    for (let i = 1; i < tableRows.length; i++) {
      const row = tableRows[i]
      const tc = { caseId: '', scenario: '', precondition: '', steps: '', expected: '', priority: 'P2' }
      headers.forEach((header, idx) => {
        const val = (row[idx] || '').replace(/<br\s*\/?>/gi, '\n')
        if (header.includes('id') || header.includes('编号')) tc.caseId = val
        else if (header.includes('目标') || header.includes('场景') || header.includes('标题')) tc.scenario = val
        else if (header.includes('前置') || header.includes('前提')) tc.precondition = val
        else if ((header.includes('步骤') || header.includes('操作')) && !header.includes('预期')) tc.steps = val
        else if (header.includes('预期') || header.includes('结果')) tc.expected = val
        else if (header.includes('优先')) tc.priority = val
      })
      if (tc.scenario || tc.caseId) result.push(tc)
    }
    return result
  }

  // 结构化文本格式
  const result = []
  let current = null
  let caseNum = 0

  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed) continue

    if (trimmed.match(/^(测试用例|Test Case|\d+[\.、\)])/) ||
        trimmed.match(/^(TC|TEST)[-_]?\d+/i)) {
      if (current) {
        result.push(current)
        caseNum++
      }
      current = {
        caseId: `TC${String(caseNum + 1).padStart(3, '0')}`,
        scenario: trimmed.replace(/^(测试用例\d*[:：]?\s*|Test Case\s*\d*[:：]?\s*|\d+[\.、\)]\s*)/i, ''),
        precondition: '',
        steps: '',
        expected: '',
        priority: 'P2'
      }
    } else if (current) {
      if (trimmed.includes('前置条件') || trimmed.includes('前提')) {
        current.precondition = trimmed.replace(/.*?[:：]\s*/, '')
      } else if ((trimmed.includes('测试步骤') || trimmed.includes('操作步骤')) && !trimmed.includes('预期')) {
        current.steps = trimmed.replace(/.*?[:：]\s*/, '')
      } else if (trimmed.includes('预期结果') || trimmed.includes('预期')) {
        current.expected = trimmed.replace(/.*?[:：]\s*/, '')
      } else if (trimmed.includes('优先级')) {
        current.priority = trimmed.replace(/.*?[:：]\s*/, '')
      }
    }
  }
  if (current) result.push(current)

  return result
}
