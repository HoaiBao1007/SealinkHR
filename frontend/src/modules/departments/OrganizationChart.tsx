import { useEffect, useMemo, useRef, useState } from 'react'
import logoSealink from '../../assets/LOGO SEALINK.jpg'
import './OrganizationChart.css'

type ApiRequest = (path: string, init?: RequestInit) => Promise<Response>

type ChartMember = {
  assignment_id: number | null
  employee_id: number
  full_name: string
  notion_name: string | null
  employee_code: string | null
  position_title: string | null
  company_email: string | null
  phone_number: string | null
  company_phone_number: string | null
  department_name: string | null
  reports_to_employee_id: number | null
  display_order: number
  source: string
}

type ChartUnit = {
  id: number
  code: string
  name: string
  unit_type: string
  parent_id: number | null
  linked_department_id: number | null
  leader_employee_id: number | null
  color: string | null
  sort_order: number
  members: ChartMember[]
}

type ChartPayload = {
  generated_at: string
  units: ChartUnit[]
  employee_count: number
}

type PositionedNode = {
  id: string
  kind: 'root' | 'unit' | 'member'
  x: number
  y: number
  width: number
  height: number
  color: string
  unit?: ChartUnit
  member?: ChartMember
  isLeader?: boolean
}

type ChartEdge = {
  id: string
  path: string
}

type ChartLayout = {
  nodes: PositionedNode[]
  edges: ChartEdge[]
  width: number
  height: number
}

const CARD_WIDTH = 320
const CARD_HEIGHT = 190
const UNIT_WIDTH = 260
const UNIT_HEIGHT = 82
const LANE_WIDTH = 348
const HORIZONTAL_GAP = 30
const VERTICAL_GAP = 28
const CANVAS_PADDING = 72

const normalize = (value: string | null | undefined) =>
  (value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase('vi')
    .trim()

function orthogonalPath(
  fromX: number,
  fromY: number,
  toX: number,
  toY: number,
  middleY = fromY + (toY - fromY) / 2,
) {
  return `M ${fromX} ${fromY} V ${middleY} H ${toX} V ${toY}`
}

function buildChartLayout(units: ChartUnit[], collapsedCodes: Set<string>): ChartLayout {
  const activeUnits = units.filter((unit) => unit.code !== 'UNASSIGNED')
  const childrenByParent = new Map<number, ChartUnit[]>()

  activeUnits.forEach((unit) => {
    if (unit.parent_id == null) return
    const siblings = childrenByParent.get(unit.parent_id) || []
    siblings.push(unit)
    childrenByParent.set(unit.parent_id, siblings)
  })
  childrenByParent.forEach((children) => children.sort((a, b) => a.sort_order - b.sort_order))

  const company = activeUnits.find((unit) => unit.code === 'COMPANY')
  const executive = activeUnits.find((unit) => unit.code === 'EXECUTIVE')
  const companyChildren = company ? childrenByParent.get(company.id) || [] : []
  const mainUnits = companyChildren.filter(
    (unit) => unit.code !== 'EXECUTIVE' && unit.code !== 'UNASSIGNED',
  )
  const fallbackMainUnits = activeUnits.filter(
    (unit) =>
      unit.parent_id == null &&
      unit.code !== 'COMPANY' &&
      unit.code !== 'EXECUTIVE' &&
      unit.code !== 'UNASSIGNED',
  )
  const roots = (mainUnits.length ? mainUnits : fallbackMainUnits).sort(
    (a, b) => a.sort_order - b.sort_order,
  )

  const branchSpan = (unit: ChartUnit): number => {
    if (collapsedCodes.has(unit.code)) return LANE_WIDTH
    const children = childrenByParent.get(unit.id) || []
    if (!children.length) return LANE_WIDTH
    return Math.max(
      LANE_WIDTH,
      children.reduce((sum, child) => sum + branchSpan(child), 0) +
        HORIZONTAL_GAP * Math.max(0, children.length - 1),
    )
  }

  const totalRootSpan = roots.reduce((sum, unit) => sum + branchSpan(unit), 0)
  const rootsGap = HORIZONTAL_GAP * Math.max(0, roots.length - 1)
  const width = Math.max(1_760, totalRootSpan + rootsGap + CANVAS_PADDING * 2)
  const centerX = width / 2
  const nodes: PositionedNode[] = []
  const edges: ChartEdge[] = []
  let maxBottom = 0

  const addNode = (node: PositionedNode) => {
    nodes.push(node)
    maxBottom = Math.max(maxBottom, node.y + node.height)
  }

  const addBranchEdges = (
    edgePrefix: string,
    sourceX: number,
    sourceY: number,
    targets: { x: number; y: number; id: string }[],
  ) => {
    if (!targets.length) return
    const branchY = sourceY + Math.max(34, (Math.min(...targets.map((target) => target.y)) - sourceY) / 2)
    targets.forEach((target) => {
      edges.push({
        id: `${edgePrefix}-${target.id}`,
        path: orthogonalPath(sourceX, sourceY, target.x, target.y, branchY),
      })
    })
  }

  addNode({
    id: 'root-director',
    kind: 'root',
    x: centerX - 108,
    y: 42,
    width: 216,
    height: 78,
    color: '#f97316',
  })

  const executiveMembers = executive?.members || []
  const executiveTop = 168
  const executiveTotalWidth =
    executiveMembers.length * CARD_WIDTH +
    Math.max(0, executiveMembers.length - 1) * HORIZONTAL_GAP
  const executiveLeft = centerX - executiveTotalWidth / 2

  executiveMembers.forEach((member, index) => {
    const x = executiveLeft + index * (CARD_WIDTH + HORIZONTAL_GAP)
    addNode({
      id: `member-${member.employee_id}`,
      kind: 'member',
      x,
      y: executiveTop,
      width: CARD_WIDTH,
      height: CARD_HEIGHT,
      color: executive?.color || '#f97316',
      unit: executive,
      member,
      isLeader: member.employee_id === executive?.leader_employee_id,
    })
  })

  if (executiveMembers.length) {
    addBranchEdges(
      'director-executive',
      centerX,
      120,
      executiveMembers.map((member, index) => ({
        id: String(member.employee_id),
        x: executiveLeft + index * (CARD_WIDTH + HORIZONTAL_GAP) + CARD_WIDTH / 2,
        y: executiveTop,
      })),
    )
  }

  const mainTop = executiveMembers.length ? executiveTop + CARD_HEIGHT + 100 : 242
  const mainSourceY = executiveMembers.length ? executiveTop + CARD_HEIGHT + 36 : 120

  const placeUnit = (unit: ChartUnit, left: number, top: number, span: number): number => {
    const unitCenterX = left + span / 2
    const unitColor = unit.color || '#1d4ed8'
    addNode({
      id: `unit-${unit.id}`,
      kind: 'unit',
      x: unitCenterX - UNIT_WIDTH / 2,
      y: top,
      width: UNIT_WIDTH,
      height: UNIT_HEIGHT,
      color: unitColor,
      unit,
    })

    if (collapsedCodes.has(unit.code)) return top + UNIT_HEIGHT

    let anchorY = top + UNIT_HEIGHT
    let previousNodeBottom = anchorY
    unit.members.forEach((member, index) => {
      const y = top + UNIT_HEIGHT + 54 + index * (CARD_HEIGHT + VERTICAL_GAP)
      addNode({
        id: `member-${member.employee_id}`,
        kind: 'member',
        x: unitCenterX - CARD_WIDTH / 2,
        y,
        width: CARD_WIDTH,
        height: CARD_HEIGHT,
        color: unitColor,
        unit,
        member,
        isLeader: member.employee_id === unit.leader_employee_id,
      })
      edges.push({
        id: `unit-member-${unit.id}-${member.employee_id}`,
        path: `M ${unitCenterX} ${previousNodeBottom} V ${y}`,
      })
      previousNodeBottom = y + CARD_HEIGHT
      anchorY = previousNodeBottom
    })

    const children = childrenByParent.get(unit.id) || []
    if (!children.length) return anchorY

    const childrenTop = anchorY + 92
    let childLeft = left
    const targets: { x: number; y: number; id: string }[] = []
    children.forEach((child) => {
      const childSpan = branchSpan(child)
      targets.push({
        id: child.code,
        x: childLeft + childSpan / 2,
        y: childrenTop,
      })
      childLeft += childSpan + HORIZONTAL_GAP
    })
    addBranchEdges(`unit-children-${unit.id}`, unitCenterX, anchorY, targets)

    childLeft = left
    children.forEach((child) => {
      const childSpan = branchSpan(child)
      placeUnit(child, childLeft, childrenTop, childSpan)
      childLeft += childSpan + HORIZONTAL_GAP
    })
    return maxBottom
  }

  let rootLeft = CANVAS_PADDING
  const rootTargets: { x: number; y: number; id: string }[] = []
  roots.forEach((unit) => {
    const span = branchSpan(unit)
    rootTargets.push({ id: unit.code, x: rootLeft + span / 2, y: mainTop })
    rootLeft += span + HORIZONTAL_GAP
  })
  addBranchEdges('main-branches', centerX, mainSourceY, rootTargets)

  rootLeft = CANVAS_PADDING
  roots.forEach((unit) => {
    const span = branchSpan(unit)
    placeUnit(unit, rootLeft, mainTop, span)
    rootLeft += span + HORIZONTAL_GAP
  })

  return {
    nodes,
    edges,
    width,
    height: Math.max(980, maxBottom + 110),
  }
}

function MobileUnitTree({
  unit,
  childrenByParent,
  collapsedCodes,
  onToggle,
  onOpenEmployee,
}: {
  unit: ChartUnit
  childrenByParent: Map<number, ChartUnit[]>
  collapsedCodes: Set<string>
  onToggle: (code: string) => void
  onOpenEmployee?: (employeeId: number) => void
}) {
  const children = childrenByParent.get(unit.id) || []
  const isCollapsed = collapsedCodes.has(unit.code)
  return (
    <section className="org-mobile-unit" style={{ '--unit-color': unit.color || '#2563eb' } as React.CSSProperties}>
      <button className="org-mobile-unit__heading" onClick={() => onToggle(unit.code)} type="button">
        <span>
          <strong>{unit.name}</strong>
          <small>{unit.members.length} nhân viên</small>
        </span>
        <span aria-hidden="true">{isCollapsed ? '+' : '−'}</span>
      </button>
      {!isCollapsed && (
        <div className="org-mobile-unit__body">
          {unit.members.map((member) => (
            <button
              className="org-mobile-member"
              key={member.employee_id}
              onClick={() => onOpenEmployee?.(member.employee_id)}
              type="button"
            >
              <span className="org-mobile-member__row org-mobile-member__row--english">
                <b>Tên tiếng Anh:</b>
                <span>{member.notion_name || 'Chưa cập nhật tên tiếng Anh'}</span>
              </span>
              <span className="org-mobile-member__row org-mobile-member__row--vietnamese">
                <b>Tên tiếng Việt:</b>
                <span>{member.full_name}</span>
              </span>
              <span className="org-mobile-member__row org-mobile-member__row--position">
                <b>Chức vụ:</b>
                <span>{member.position_title || 'Chưa cập nhật chức vụ'}</span>
              </span>
              <span className="org-mobile-member__row">
                <b>Phòng ban:</b>
                <span>{member.department_name || unit.name}</span>
              </span>
              <span className="org-mobile-member__row">
                <b>Email:</b>
                <span>{member.company_email || 'Chưa cập nhật'}</span>
              </span>
              <span className="org-mobile-member__row">
                <b>SĐT cá nhân:</b>
                <span>{member.phone_number || 'Chưa cập nhật'}</span>
              </span>
              <span className="org-mobile-member__row">
                <b>SĐT công ty:</b>
                <span>{member.company_phone_number || 'Chưa cập nhật'}</span>
              </span>
            </button>
          ))}
          {children.map((child) => (
            <MobileUnitTree
              key={child.id}
              unit={child}
              childrenByParent={childrenByParent}
              collapsedCodes={collapsedCodes}
              onToggle={onToggle}
              onOpenEmployee={onOpenEmployee}
            />
          ))}
        </div>
      )}
    </section>
  )
}

export function OrganizationChart({
  apiRequest,
  token,
  onOpenEmployee,
  refreshKey,
}: {
  apiRequest: ApiRequest
  token: string
  onOpenEmployee?: (employeeId: number) => void
  refreshKey?: string
}) {
  const [payload, setPayload] = useState<ChartPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [collapsedCodes, setCollapsedCodes] = useState<Set<string>>(new Set())
  const [scale, setScale] = useState(0.72)
  const [exporting, setExporting] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const shellRef = useRef<HTMLElement>(null)
  const viewportRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<{ x: number; y: number; left: number; top: number } | null>(null)

  const loadChart = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await apiRequest('/api/organization/chart')
      if (!response.ok) {
        const detail = await response.json().catch(() => null)
        throw new Error(detail?.detail || 'Không thể tải dữ liệu sơ đồ tổ chức.')
      }
      setPayload(await response.json())
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Không thể tải dữ liệu sơ đồ tổ chức.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadChart()
  }, [token, refreshKey])

  const units = payload?.units || []
  const layout = useMemo(
    () => buildChartLayout(units, collapsedCodes),
    [units, collapsedCodes],
  )
  const normalizedQuery = normalize(query)
  const matchingMemberIds = useMemo(() => {
    if (!normalizedQuery) return new Set<number>()
    const ids = new Set<number>()
    units.forEach((unit) => {
      unit.members.forEach((member) => {
        const haystack = normalize(
          [
            member.full_name,
            member.notion_name,
            member.employee_code,
            member.position_title,
            member.company_email,
            member.phone_number,
            member.company_phone_number,
            member.department_name,
            unit.name,
          ]
            .filter(Boolean)
            .join(' '),
        )
        if (haystack.includes(normalizedQuery)) ids.add(member.employee_id)
      })
    })
    return ids
  }, [normalizedQuery, units])

  const childrenByParent = useMemo(() => {
    const map = new Map<number, ChartUnit[]>()
    units.forEach((unit) => {
      if (unit.parent_id == null) return
      const children = map.get(unit.parent_id) || []
      children.push(unit)
      map.set(unit.parent_id, children)
    })
    map.forEach((children) => children.sort((a, b) => a.sort_order - b.sort_order))
    return map
  }, [units])
  const company = units.find((unit) => unit.code === 'COMPANY')
  const unassignedCount =
    units.find((unit) => unit.code === 'UNASSIGNED')?.members.length || 0
  const visibleEmployeeCount = Math.max(
    0,
    (payload?.employee_count || 0) - unassignedCount,
  )
  const mobileRoots = (company ? childrenByParent.get(company.id) || [] : units.filter((unit) => unit.parent_id == null))
    .filter((unit) => unit.code !== 'UNASSIGNED')

  const toggleUnit = (code: string) => {
    setCollapsedCodes((current) => {
      const next = new Set(current)
      if (next.has(code)) next.delete(code)
      else next.add(code)
      return next
    })
  }

  const fitChart = () => {
    const viewport = viewportRef.current
    if (!viewport) return
    const widthScale = (viewport.clientWidth - 36) / layout.width
    const shellIsFullscreen = document.fullscreenElement === shellRef.current
    const maximumScale = shellIsFullscreen ? 2 : 0.92
    const nextScale = Math.max(0.4, Math.min(maximumScale, widthScale))
    setScale(nextScale)
    window.setTimeout(() => {
      viewport.scrollTo({ left: 0, top: 0, behavior: 'smooth' })
    }, 0)
  }

  useEffect(() => {
    if (!payload) return
    const timer = window.setTimeout(fitChart, 40)
    return () => window.clearTimeout(timer)
  }, [payload])

  useEffect(() => {
    const syncFullscreenState = () => {
      const active = document.fullscreenElement === shellRef.current
      setIsFullscreen(active)
      window.setTimeout(fitChart, 80)
    }
    document.addEventListener('fullscreenchange', syncFullscreenState)
    return () => document.removeEventListener('fullscreenchange', syncFullscreenState)
  }, [layout.height, layout.width])

  const toggleFullscreen = async () => {
    const shell = shellRef.current
    if (!shell) return
    try {
      if (document.fullscreenElement === shell) {
        await document.exitFullscreen()
        return
      }
      if (document.fullscreenElement) {
        await document.exitFullscreen()
      }
      await shell.requestFullscreen()
    } catch (reason) {
      setError(
        reason instanceof Error
          ? `Không thể mở toàn màn hình: ${reason.message}`
          : 'Trình duyệt không hỗ trợ mở sơ đồ toàn màn hình.',
      )
    }
  }

  const focusFirstMatch = () => {
    const viewport = viewportRef.current
    const firstMatchId = matchingMemberIds.values().next().value as number | undefined
    if (firstMatchId == null || !viewport) return

    const scrollToEmployee = () => {
      const currentViewport = viewportRef.current
      const node = buildChartLayout(units, new Set()).nodes.find(
        (item) => item.member?.employee_id === firstMatchId,
      )
      if (!currentViewport || !node) return
      currentViewport.scrollTo({
        left: Math.max(0, node.x * scale - currentViewport.clientWidth / 2 + node.width * scale / 2),
        top: Math.max(0, node.y * scale - currentViewport.clientHeight / 2),
        behavior: 'smooth',
      })
    }

    const firstMatch = layout.nodes.find(
      (node) => node.member?.employee_id === firstMatchId,
    )
    if (!firstMatch) {
      setCollapsedCodes(new Set())
      window.setTimeout(scrollToEmployee, 60)
      return
    }
    viewport.scrollTo({
      left: Math.max(0, firstMatch.x * scale - viewport.clientWidth / 2 + firstMatch.width * scale / 2),
      top: Math.max(0, firstMatch.y * scale - viewport.clientHeight / 2),
      behavior: 'smooth',
    })
  }

  const exportPdf = async () => {
    setExporting(true)
    setError(null)
    try {
      const { downloadOrganizationChartVectorPdf } = await import('./organizationChartPdf')
      await downloadOrganizationChartVectorPdf(
        layout,
        `So-do-to-chuc-${new Date().toISOString().slice(0, 10)}.pdf`,
      )
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Không thể xuất PDF sơ đồ tổ chức.')
    } finally {
      setExporting(false)
    }
  }

  if (loading) {
    return <div className="org-chart-state">Đang dựng sơ đồ tổ chức...</div>
  }
  if (error && !payload) {
    return (
      <div className="org-chart-state org-chart-state--error">
        <p>{error}</p>
        <button type="button" onClick={loadChart}>Thử lại</button>
      </div>
    )
  }

  return (
    <section className="org-chart-shell" ref={shellRef}>
      <div className="org-chart-toolbar">
        <div className="org-chart-toolbar__summary">
          <span className="org-chart-eyebrow">ORGANIZATION MAP</span>
          <strong>{visibleEmployeeCount} nhân viên đang hiển thị</strong>
          <span>
            Dữ liệu cập nhật trực tiếp từ phòng ban và hồ sơ nhân sự.
            {unassignedCount > 0 ? ` Còn ${unassignedCount} hồ sơ chưa gán phòng.` : ''}
          </span>
        </div>
        <div className="org-chart-search">
          <label htmlFor="organization-chart-search">Tìm nhân viên hoặc phòng ban</label>
          <div>
            <input
              id="organization-chart-search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') focusFirstMatch()
              }}
              placeholder="Tên Việt, tên Notion, chức vụ, email..."
            />
            <button type="button" onClick={focusFirstMatch} disabled={!matchingMemberIds.size}>
              Tìm ({matchingMemberIds.size})
            </button>
          </div>
        </div>
        <div className="org-chart-actions" aria-label="Điều khiển sơ đồ">
          <button
            className={`org-chart-icon-button ${isFullscreen ? 'is-active' : ''}`}
            type="button"
            onClick={toggleFullscreen}
            aria-label={isFullscreen ? 'Thoát toàn màn hình' : 'Mở sơ đồ toàn màn hình'}
            aria-pressed={isFullscreen}
            title={isFullscreen ? 'Thoát toàn màn hình (Esc)' : 'Mở toàn màn hình'}
          >
            <span aria-hidden="true">⛶</span>
          </button>
          <div className="org-chart-zoom" aria-label="Mức phóng sơ đồ">
            <button
              type="button"
              onClick={() => setScale((value) => Math.max(0.4, value - 0.1))}
              aria-label="Thu nhỏ"
              title="Thu nhỏ"
            >
              −
            </button>
            <output aria-live="polite">{Math.round(scale * 100)}%</output>
            <button
              type="button"
              onClick={() => setScale((value) => Math.min(1.3, value + 0.1))}
              aria-label="Phóng to"
              title="Phóng to"
            >
              +
            </button>
          </div>
          <button className="org-chart-action-button org-chart-action-button--fit" type="button" onClick={fitChart}>
            Vừa màn hình
          </button>
          <button className="org-chart-action-button" type="button" onClick={loadChart}>
            Làm mới
          </button>
          <button className="org-chart-action-button" type="button" onClick={exportPdf} disabled={exporting}>
            {exporting ? 'Đang xuất...' : 'Xuất PDF'}
          </button>
        </div>
      </div>

      {error && <div className="org-chart-inline-error">{error}</div>}

      <div
        className="org-chart-viewport"
        ref={viewportRef}
        onPointerDown={(event) => {
          if ((event.target as HTMLElement).closest('button')) return
          const viewport = viewportRef.current
          if (!viewport) return
          dragRef.current = {
            x: event.clientX,
            y: event.clientY,
            left: viewport.scrollLeft,
            top: viewport.scrollTop,
          }
          viewport.setPointerCapture(event.pointerId)
          viewport.classList.add('is-dragging')
        }}
        onPointerMove={(event) => {
          const drag = dragRef.current
          const viewport = viewportRef.current
          if (!drag || !viewport) return
          viewport.scrollLeft = drag.left - (event.clientX - drag.x)
          viewport.scrollTop = drag.top - (event.clientY - drag.y)
        }}
        onPointerUp={(event) => {
          dragRef.current = null
          const viewport = viewportRef.current
          if (viewport?.hasPointerCapture(event.pointerId)) {
            viewport.releasePointerCapture(event.pointerId)
          }
          viewport?.classList.remove('is-dragging')
        }}
        onPointerCancel={(event) => {
          dragRef.current = null
          const viewport = viewportRef.current
          if (viewport?.hasPointerCapture(event.pointerId)) {
            viewport.releasePointerCapture(event.pointerId)
          }
          viewport?.classList.remove('is-dragging')
        }}
      >
        <div
          className="org-chart-scaled-area"
          style={{ width: layout.width * scale, height: layout.height * scale }}
        >
          <div
            className="org-chart-stage"
            style={{
              width: layout.width,
              height: layout.height,
              transform: `scale(${scale})`,
            }}
          >
            <div className="org-chart-stage__brand">
              <img src={logoSealink} alt="Sealink International" />
              <span>SEALINK INTERNATIONAL</span>
            </div>
            <div className="org-chart-stage__title">ORGANIZE CHART</div>
            <svg
              className="org-chart-connectors"
              width={layout.width}
              height={layout.height}
              aria-hidden="true"
            >
              {layout.edges.map((edge) => (
                <path d={edge.path} key={edge.id} />
              ))}
            </svg>

            {layout.nodes.map((node) => {
              const style = {
                left: node.x,
                top: node.y,
                width: node.width,
                height: node.height,
                '--node-color': node.color,
              } as React.CSSProperties

              if (node.kind === 'root') {
                return (
                  <div className="org-chart-root" key={node.id} style={style}>
                    <strong>DIRECTOR</strong>
                  </div>
                )
              }
              if (node.kind === 'unit' && node.unit) {
                const descendantCount = node.unit.members.length
                return (
                  <button
                    className="org-chart-unit"
                    key={node.id}
                    style={style}
                    type="button"
                    onClick={() => toggleUnit(node.unit!.code)}
                    title={collapsedCodes.has(node.unit.code) ? 'Mở rộng nhánh' : 'Thu gọn nhánh'}
                  >
                    <strong>{node.unit.name}</strong>
                    <span>{descendantCount} nhân viên · {collapsedCodes.has(node.unit.code) ? 'Mở rộng' : 'Thu gọn'}</span>
                  </button>
                )
              }
              if (node.kind === 'member' && node.member) {
                const isMatch = normalizedQuery && matchingMemberIds.has(node.member.employee_id)
                return (
                  <button
                    className={`org-chart-member ${node.isLeader ? 'is-leader' : ''} ${isMatch ? 'is-match' : ''}`}
                    key={node.id}
                    style={style}
                    type="button"
                    onClick={() => onOpenEmployee?.(node.member!.employee_id)}
                    title="Mở hồ sơ nhân viên"
                  >
                    <span className="org-chart-member__row org-chart-member__row--english">
                      <b>Tên tiếng Anh:</b>
                      <span>{node.member.notion_name || 'Chưa cập nhật tên tiếng Anh'}</span>
                    </span>
                    <span className="org-chart-member__row org-chart-member__row--vietnamese">
                      <b>Tên tiếng Việt:</b>
                      <span>{node.member.full_name}</span>
                    </span>
                    <span className="org-chart-member__row org-chart-member__row--position">
                      <b>Chức vụ:</b>
                      <span>{node.member.position_title || 'Chưa cập nhật chức vụ'}</span>
                    </span>
                    <span className="org-chart-member__row">
                      <b>Phòng ban:</b>
                      <span>{node.member.department_name || node.unit?.name || 'Chưa cập nhật'}</span>
                    </span>
                    <span className="org-chart-member__row">
                      <b>Email:</b>
                      <span>{node.member.company_email || 'Chưa cập nhật'}</span>
                    </span>
                    <span className="org-chart-member__row">
                      <b>SĐT cá nhân:</b>
                      <span>{node.member.phone_number || 'Chưa cập nhật'}</span>
                    </span>
                    <span className="org-chart-member__row">
                      <b>SĐT công ty:</b>
                      <span>{node.member.company_phone_number || 'Chưa cập nhật'}</span>
                    </span>
                  </button>
                )
              }
              return null
            })}
          </div>
        </div>
      </div>

      <div className="org-chart-mobile">
        {mobileRoots.map((unit) => (
          <MobileUnitTree
            key={unit.id}
            unit={unit}
            childrenByParent={childrenByParent}
            collapsedCodes={collapsedCodes}
            onToggle={toggleUnit}
            onOpenEmployee={onOpenEmployee}
          />
        ))}
      </div>
    </section>
  )
}
