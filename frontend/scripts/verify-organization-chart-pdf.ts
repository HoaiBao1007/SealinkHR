import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import {
  buildOrganizationChartPdfDefinition,
  createOrganizationChartPdfBuffer,
  parseOrthogonalPath,
  type OrganizationChartPdfLayout,
} from '../src/modules/departments/organizationChartPdf.ts'

const segments = parseOrthogonalPath('M 100 120 V 180 H 320 V 240')
assert.deepEqual(segments, [
  { x1: 100, y1: 120, x2: 100, y2: 180 },
  { x1: 100, y1: 180, x2: 320, y2: 180 },
  { x1: 320, y1: 180, x2: 320, y2: 240 },
])

const layout: OrganizationChartPdfLayout = {
  width: 1_200,
  height: 840,
  edges: [
    { id: 'root-unit', path: 'M 600 120 V 180 H 600 V 235' },
    { id: 'unit-member', path: 'M 600 317 V 370' },
    { id: 'member-member', path: 'M 600 560 V 590' },
  ],
  nodes: [
    {
      id: 'root',
      kind: 'root',
      x: 492,
      y: 42,
      width: 216,
      height: 78,
      color: '#f97316',
    },
    {
      id: 'unit',
      kind: 'unit',
      x: 470,
      y: 235,
      width: 260,
      height: 82,
      color: '#0ea5e9',
      unit: {
        id: 1,
        name: 'IT & ADMIN TEAM',
        members: [],
      },
    },
    {
      id: 'member-1',
      kind: 'member',
      x: 440,
      y: 370,
      width: 320,
      height: 190,
      color: '#0ea5e9',
      isLeader: true,
      unit: {
        id: 1,
        name: 'IT & ADMIN TEAM',
        members: [],
      },
      member: {
        employee_id: 1,
        notion_name: 'TOMMY DAT',
        full_name: 'Nguyễn Thành Đạt',
        position_title: 'IT Executive',
        department_name: 'IT & Admin',
        company_email: 'dat.nguyen@sea-link.com',
        phone_number: '0901 234 567',
        company_phone_number: '0287 307 5768',
      },
    },
    {
      id: 'member-2',
      kind: 'member',
      x: 440,
      y: 590,
      width: 320,
      height: 190,
      color: '#0ea5e9',
      unit: {
        id: 1,
        name: 'IT & ADMIN TEAM',
        members: [],
      },
      member: {
        employee_id: 2,
        notion_name: 'BARON',
        full_name: 'Đặng Hoài Bảo',
        position_title: 'IT Support - Intern',
        department_name: 'IT & Admin',
        company_email: 'baron.hoai@sea-link.com',
        phone_number: '0908 765 432',
        company_phone_number: null,
      },
    },
  ],
}

const definition = buildOrganizationChartPdfDefinition(layout)
assert.deepEqual(definition.pageMargins, [0, 0, 0, 0])
assert.equal(definition.defaultStyle?.font, 'Roboto')
assert.equal(definition.info?.title, 'Sơ đồ tổ chức Sealink International')

const outputDirectory = resolve(process.cwd(), '..', 'output', 'pdf')
await mkdir(outputDirectory, { recursive: true })
const outputPath = resolve(outputDirectory, 'organization-chart-vector-sample.pdf')
const buffer = await createOrganizationChartPdfBuffer(layout)
assert.ok(buffer.byteLength > 10_000, 'PDF vector phải có dữ liệu font và nội dung.')
const pdfSource = Buffer.from(buffer).toString('latin1')
assert.ok(!pdfSource.includes('/Subtype /Image'), 'PDF vector không được chứa ảnh raster.')
await writeFile(outputPath, buffer)

process.stdout.write(`${outputPath}\n`)
