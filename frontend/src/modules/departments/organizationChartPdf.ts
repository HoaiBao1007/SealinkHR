import type {
  CanvasElement,
  Content,
  ContentColumns,
  ContentStack,
  TDocumentDefinitions,
} from 'pdfmake/interfaces'

export type OrganizationChartPdfMember = {
  employee_id: number
  full_name: string
  notion_name: string | null
  position_title: string | null
  company_email: string | null
  phone_number: string | null
  company_phone_number: string | null
  department_name: string | null
}

export type OrganizationChartPdfUnit = {
  id: number
  name: string
  members: OrganizationChartPdfMember[]
}

export type OrganizationChartPdfNode = {
  id: string
  kind: 'root' | 'unit' | 'member'
  x: number
  y: number
  width: number
  height: number
  color: string
  unit?: OrganizationChartPdfUnit
  member?: OrganizationChartPdfMember
  isLeader?: boolean
}

export type OrganizationChartPdfLayout = {
  nodes: OrganizationChartPdfNode[]
  edges: { id: string; path: string }[]
  width: number
  height: number
}

export type LineSegment = {
  x1: number
  y1: number
  x2: number
  y2: number
}

const PDF_SCALE = 0.75
const PAGE_BACKGROUND = '#172033'
const CARD_BACKGROUND = '#f8fafc'
const CARD_BORDER = '#dbe4ef'
const CONNECTOR_COLOR = '#dbe4ef'
const PRIMARY_TEXT = '#172033'
const MUTED_TEXT = '#64748b'
const FALLBACK_TEXT = 'Chưa cập nhật'

const pt = (value: number) => Math.round(value * PDF_SCALE * 100) / 100

export function parseOrthogonalPath(path: string): LineSegment[] {
  const tokens = path.match(/[MVH]|-?\d+(?:\.\d+)?/g) || []
  const segments: LineSegment[] = []
  let currentX = 0
  let currentY = 0
  let index = 0

  while (index < tokens.length) {
    const command = tokens[index++]
    if (command === 'M') {
      const x = Number(tokens[index++])
      const y = Number(tokens[index++])
      if (!Number.isFinite(x) || !Number.isFinite(y)) {
        throw new Error(`Đường nối Organization Chart không hợp lệ: ${path}`)
      }
      currentX = x
      currentY = y
      continue
    }

    if (command === 'V') {
      const nextY = Number(tokens[index++])
      if (!Number.isFinite(nextY)) {
        throw new Error(`Đường nối Organization Chart không hợp lệ: ${path}`)
      }
      segments.push({ x1: currentX, y1: currentY, x2: currentX, y2: nextY })
      currentY = nextY
      continue
    }

    if (command === 'H') {
      const nextX = Number(tokens[index++])
      if (!Number.isFinite(nextX)) {
        throw new Error(`Đường nối Organization Chart không hợp lệ: ${path}`)
      }
      segments.push({ x1: currentX, y1: currentY, x2: nextX, y2: currentY })
      currentX = nextX
      continue
    }

    throw new Error(`Lệnh đường nối Organization Chart không được hỗ trợ: ${String(command)}`)
  }

  return segments
}

function textBlock(
  x: number,
  y: number,
  width: number,
  stack: Content[],
  alignment: 'left' | 'center' | 'right' = 'left',
): ContentColumns {
  const column: ContentStack & { width: number } = {
    width: pt(width),
    stack,
  }
  return {
    columns: [column],
    columnGap: 0,
    alignment,
    absolutePosition: { x: pt(x), y: pt(y) },
  }
}

function labelledLine(label: string, value: string | null | undefined): Content {
  return {
    text: [
      { text: `${label}: `, bold: true },
      { text: value?.trim() || FALLBACK_TEXT },
    ],
    fontSize: 7.25,
    lineHeight: 1.12,
    color: PRIMARY_TEXT,
    margin: [0, 0, 0, 2],
  }
}

function nodeCanvas(node: OrganizationChartPdfNode): CanvasElement[] {
  const common = {
    type: 'rect' as const,
    x: pt(node.x),
    y: pt(node.y),
    w: pt(node.width),
    h: pt(node.height),
    r: pt(node.kind === 'member' ? 14 : 12),
  }

  if (node.kind === 'root') {
    return [
      {
        ...common,
        color: CARD_BACKGROUND,
        lineColor: CARD_BORDER,
        lineWidth: 1,
      },
      {
        type: 'rect',
        x: pt(node.x),
        y: pt(node.y + node.height - 9),
        w: pt(node.width),
        h: pt(9),
        r: pt(5),
        color: node.color,
        lineColor: node.color,
      },
    ]
  }

  if (node.kind === 'unit') {
    return [
      {
        ...common,
        color: CARD_BACKGROUND,
        lineColor: node.color,
        lineWidth: node.isLeader ? 1.5 : 0.8,
      },
    ]
  }

  return [
    {
      ...common,
      color: CARD_BACKGROUND,
      lineColor: node.isLeader ? node.color : CARD_BORDER,
      lineWidth: node.isLeader ? 1.5 : 0.8,
    },
    {
      type: 'rect',
      x: pt(node.x),
      y: pt(node.y + node.height - 7),
      w: pt(node.width),
      h: pt(7),
      r: pt(4),
      color: node.color,
      lineColor: node.color,
    },
  ]
}

function nodeText(node: OrganizationChartPdfNode): Content[] {
  if (node.kind === 'root') {
    return [
      textBlock(
        node.x + 12,
        node.y + 25,
        node.width - 24,
        [{ text: 'DIRECTOR', bold: true, fontSize: 12, color: PRIMARY_TEXT }],
        'center',
      ),
    ]
  }

  if (node.kind === 'unit' && node.unit) {
    return [
      textBlock(
        node.x + 14,
        node.y + 18,
        node.width - 28,
        [
          {
            text: node.unit.name,
            bold: true,
            fontSize: 10.5,
            color: node.color,
            lineHeight: 1.05,
            margin: [0, 0, 0, 6],
          },
          {
            text: `${node.unit.members.length} nhân viên`,
            fontSize: 7.5,
            color: MUTED_TEXT,
          },
        ],
        'center',
      ),
    ]
  }

  if (node.kind === 'member' && node.member) {
    const member = node.member
    const unitName = member.department_name || node.unit?.name || FALLBACK_TEXT
    return [
      textBlock(node.x + 16, node.y + 13, node.width - 32, [
        {
          text: member.notion_name?.trim() || 'Chưa cập nhật tên tiếng Anh',
          bold: true,
          fontSize: 10,
          color: PRIMARY_TEXT,
          lineHeight: 1.05,
          margin: [0, 0, 0, 3],
        },
        {
          text: member.full_name,
          bold: true,
          fontSize: 8.5,
          color: PRIMARY_TEXT,
          lineHeight: 1.05,
          margin: [0, 0, 0, 4],
        },
        {
          text: member.position_title?.trim() || 'Chưa cập nhật chức vụ',
          bold: true,
          fontSize: 7.75,
          color: node.color,
          lineHeight: 1.05,
          margin: [0, 0, 0, 4],
        },
        labelledLine('Phòng ban', unitName),
        labelledLine('Email', member.company_email),
        labelledLine('SĐT cá nhân', member.phone_number),
        labelledLine('SĐT công ty', member.company_phone_number),
      ]),
    ]
  }

  return []
}

export function buildOrganizationChartPdfDefinition(
  layout: OrganizationChartPdfLayout,
): TDocumentDefinitions {
  const pageWidth = pt(layout.width)
  const pageHeight = pt(layout.height)
  const vectorCanvas: CanvasElement[] = [
    {
      type: 'rect',
      x: 0,
      y: 0,
      w: pageWidth,
      h: pageHeight,
      color: PAGE_BACKGROUND,
      lineColor: PAGE_BACKGROUND,
    },
  ]

  layout.edges.forEach((edge) => {
    parseOrthogonalPath(edge.path).forEach((segment) => {
      vectorCanvas.push({
        type: 'line',
        x1: pt(segment.x1),
        y1: pt(segment.y1),
        x2: pt(segment.x2),
        y2: pt(segment.y2),
        lineColor: CONNECTOR_COLOR,
        lineWidth: 1.15,
        lineCap: 'round',
      })
    })
  })
  layout.nodes.forEach((node) => vectorCanvas.push(...nodeCanvas(node)))

  const content: Content[] = [
    {
      canvas: vectorCanvas,
      absolutePosition: { x: 0, y: 0 },
    },
    {
      canvas: [
        {
          type: 'rect',
          x: pt(30),
          y: pt(28),
          w: pt(118),
          h: pt(46),
          r: pt(8),
          color: CARD_BACKGROUND,
          lineColor: CARD_BORDER,
          lineWidth: 0.8,
        },
      ],
      absolutePosition: { x: 0, y: 0 },
    },
    textBlock(
      38,
      38,
      102,
      [
        {
          text: 'SEALINK',
          bold: true,
          fontSize: 11,
          color: '#0ea5e9',
          alignment: 'center',
          lineHeight: 1,
        },
        {
          text: 'INTERNATIONAL',
          bold: true,
          fontSize: 5.5,
          characterSpacing: 1.2,
          color: PRIMARY_TEXT,
          alignment: 'center',
        },
      ],
      'center',
    ),
    textBlock(
      layout.width - 280,
      layout.height - 48,
      240,
      [
        {
          text: 'ORGANIZE CHART',
          bold: true,
          fontSize: 15,
          color: '#f8fafc',
        },
      ],
      'right',
    ),
  ]

  layout.nodes.forEach((node) => content.push(...nodeText(node)))

  return {
    pageSize: { width: pageWidth, height: pageHeight },
    pageMargins: [0, 0, 0, 0],
    content,
    defaultStyle: {
      font: 'Roboto',
      color: PRIMARY_TEXT,
    },
    info: {
      title: 'Sơ đồ tổ chức Sealink International',
      author: 'Sealink International',
      subject: 'Organization Chart',
      creator: 'Sealink Portal',
    },
    compress: true,
  }
}

async function createPdf(layout: OrganizationChartPdfLayout) {
  const [pdfMakeModule, vfsModule] = await Promise.all([
    import('pdfmake/build/pdfmake.js'),
    import('pdfmake/build/vfs_fonts.js'),
  ])
  const pdfMake = pdfMakeModule.default || pdfMakeModule
  const vfs = vfsModule.default || vfsModule
  return pdfMake.createPdf(buildOrganizationChartPdfDefinition(layout), undefined, undefined, vfs)
}

export async function createOrganizationChartPdfBuffer(
  layout: OrganizationChartPdfLayout,
): Promise<Uint8Array> {
  const pdf = await createPdf(layout)
  return new Promise((resolve) => {
    pdf.getBuffer((buffer) => resolve(new Uint8Array(buffer)))
  })
}

export async function downloadOrganizationChartVectorPdf(
  layout: OrganizationChartPdfLayout,
  fileName: string,
) {
  const pdf = await createPdf(layout)
  pdf.download(fileName)
}
