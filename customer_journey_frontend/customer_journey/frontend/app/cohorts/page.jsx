'use client'
import { useState, useEffect, useMemo } from 'react'
import { XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line, ReferenceLine, PieChart, Pie, Cell } from 'recharts'
import { api } from '../../lib/api'
import { Download } from 'lucide-react'
import { PageHeader, CardSkeleton } from '../../components/UI'

function fmtN(n) {
  if (!n && n !== 0) return '—'
  if (n >= 100000) return `${(n / 100000).toFixed(1)}L`
  if (n >= 1000)   return `${(n / 1000).toFixed(1)}K`
  return `${n}`
}

// Single donut per channel — shows the 90-day retention % (centre) + customer counts
function ChannelDonut({ f }) {
  const pct  = f.pct_90d || 0
  const data = [{ value: pct }, { value: Math.max(0, 100 - pct) }]
  return (
    <div className="card" style={{ padding: '20px 22px', textAlign: 'center' }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 14,
        textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        {f.channel_journey}
      </div>
      <div style={{ position: 'relative', width: 126, height: 126, margin: '0 auto' }}>
        <PieChart width={126} height={126}>
          <Pie data={data} cx={63} cy={63} innerRadius={44} outerRadius={58}
            startAngle={90} endAngle={-270} dataKey="value" strokeWidth={0}>
            <Cell fill="var(--accent)" />
            <Cell fill="var(--border)" />
          </Pie>
        </PieChart>
        <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center', textAlign: 'center', pointerEvents: 'none' }}>
          <div style={{ fontSize: 24, fontWeight: 800, color: 'var(--accent)', lineHeight: 1 }}>{pct}%</div>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>90-day retention</div>
        </div>
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 14 }}>
        <strong style={{ color: 'var(--text-primary)' }}>{fmtN(f.customers)}</strong> customers
        &nbsp;·&nbsp;
        <strong style={{ color: 'var(--text-primary)' }}>{fmtN(f.retained_90d)}</strong> retained
      </div>
      {f.avg_days_to_2nd_purchase && (
        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6 }}>
          ⏱ Avg <strong style={{ color: 'var(--text-primary)' }}>{f.avg_days_to_2nd_purchase} days</strong> to 2nd purchase
        </div>
      )}
    </div>
  )
}

function cellColor(pct, isM0) {
  if (isM0) return { bg: 'var(--accent)', color: '#fff' }
  if (!pct || pct === 0) return { bg: 'transparent', color: 'var(--text-muted)' }
  const opacity = Math.max(0.08, Math.min(0.9, pct / 12))
  return {
    bg: `rgba(110, 130, 56, ${opacity})`,
    color: opacity > 0.45 ? '#fff' : 'var(--text-primary)',
  }
}

export default function CohortsPage() {
  const [flags,   setFlags]   = useState([])
  const [cohort,  setCohort]  = useState([])
  const [loading, setLoading] = useState(true)
  const [hovered, setHovered] = useState(null)

  // Last 24 months for the cohort multi-select
  const monthOptions = useMemo(() => {
    const opts = []
    const now = new Date()
    for (let i = 0; i < 24; i++) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
      opts.push({
        label: d.toLocaleString('en-US', { month: 'short', year: 'numeric' }),
        value: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`,
      })
    }
    return opts
  }, [])

  // Default: most recent 12 cohort months selected
  const [selectedMonths, setSelectedMonths] = useState(() => monthOptions.slice(0, 12).map(o => o.value))

  const monthsKey = selectedMonths.join(',')

  // Retention flags (channel donuts) — load once
  useEffect(() => { api.getRetentionFlags().then(f => setFlags(f || [])) }, [])

  // Cohort grid — reload whenever the selected months change
  useEffect(() => {
    setLoading(true)
    const req = selectedMonths.length
      ? api.getCohortRetentionByMonths(monthsKey)
      : api.getCohortRetention(0)
    req.then(c => setCohort(c || [])).finally(() => setLoading(false))
    setHovered(null)
  }, [monthsKey])

  const toggleMonth = (v) =>
    setSelectedMonths(prev => prev.includes(v) ? prev.filter(x => x !== v) : [...prev, v])

  const MAX_PERIODS = cohort.length > 0
    ? Math.max(...cohort.map(r => r.months_since_first)) + 1
    : 6
  const cohortList = [...new Set(cohort.map(r => r.cohort_label))]

  const getPct = (cohortLabel, period) => {
    const row = cohort.find(r => r.cohort_label === cohortLabel && r.months_since_first === period)
    return row ? parseFloat(row.retention_rate_pct) : null
  }
  const getSize = (cohortLabel) => {
    const row = cohort.find(r => r.cohort_label === cohortLabel && r.months_since_first === 0)
    return row?.cohort_size || 0
  }
  const periodTrend = (period) => cohortList.map(cl => ({
    cohort : cl,
    pct    : getPct(cl, period) || 0,
  }))

  const handleExport = () => {
    const url = selectedMonths.length
      ? api.getCohortExportUrlByMonths(monthsKey)
      : api.getCohortExportUrl(0)
    window.open(url, '_blank')
  }

  return (
    <div style={{ padding: '32px 36px', maxWidth: 1300, margin: '0 auto' }}>
      <PageHeader
        title="Cohort & Retention"
        subtitle="Track how many customers come back after their first purchase — grouped by acquisition month"
        action={
          <button className="btn-primary" onClick={handleExport}
            style={{ display: 'flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap' }}>
            <Download size={13} /> Export CSV{selectedMonths.length ? ` (${selectedMonths.length} mo)` : ''}
          </button>
        }
      />

      {/* ── Channel retention — single donut each (count + %) ── */}
      {loading && flags.length === 0 ? <CardSkeleton rows={2} /> : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 14, marginBottom: 24 }}>
          {flags.map((f, i) => <ChannelDonut key={i} f={f} />)}
        </div>
      )}

      {/* ── Cohort retention grid (multi-month selectable) ── */}
      <div className="card" style={{ padding: 24, marginBottom: 20 }}>
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>Cohort Retention Grid</div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.6 }}>
            Each row = one acquisition cohort. Each column = months after first purchase.
            Pick any set of cohort months below. Darker blue = more customers returning.
          </div>
        </div>

        {/* Month multi-select */}
        <div style={{ marginBottom: 18 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)',
              textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Cohort months {selectedMonths.length ? `(${selectedMonths.length} selected)` : '(all)'}
            </span>
            <button className="btn-ghost" style={{ fontSize: 11, padding: '3px 9px' }}
              onClick={() => setSelectedMonths(monthOptions.slice(0, 12).map(o => o.value))}>Last 12</button>
            <button className="btn-ghost" style={{ fontSize: 11, padding: '3px 9px' }}
              onClick={() => setSelectedMonths(monthOptions.map(o => o.value))}>All 24</button>
            <button className="btn-ghost" style={{ fontSize: 11, padding: '3px 9px' }}
              onClick={() => setSelectedMonths([])}>Clear</button>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {monthOptions.map(o => {
              const on = selectedMonths.includes(o.value)
              return (
                <button key={o.value} onClick={() => toggleMonth(o.value)}
                  style={{
                    fontSize: 11, fontWeight: 600, padding: '4px 10px', borderRadius: 7, cursor: 'pointer',
                    border: `1px solid ${on ? 'var(--accent)' : 'var(--border)'}`,
                    background: on ? 'var(--accent-light)' : 'transparent',
                    color: on ? 'var(--accent)' : 'var(--text-secondary)',
                    transition: 'all 0.12s',
                  }}>
                  {o.label}
                </button>
              )
            })}
          </div>
        </div>

        {loading ? <CardSkeleton rows={8} /> : cohortList.length === 0 ? (
          <div style={{ fontSize: 13, color: 'var(--text-muted)', padding: '20px 0' }}>
            No cohorts for the selected months.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ borderCollapse: 'separate', borderSpacing: '3px', fontSize: 12, width: '100%' }}>
              <thead>
                <tr>
                  <th style={{ padding: '6px 12px', textAlign: 'left', fontSize: 11, fontWeight: 600,
                    color: 'var(--text-muted)', minWidth: 110 }}>Cohort</th>
                  <th style={{ padding: '6px 10px', textAlign: 'center', fontSize: 11, fontWeight: 600,
                    color: 'var(--text-muted)', minWidth: 70 }}>New Customers</th>
                  {Array.from({ length: MAX_PERIODS }, (_, i) => (
                    <th key={i} style={{ padding: '6px 10px', textAlign: 'center', fontSize: 11,
                      fontWeight: 600, minWidth: 72,
                      color: i === 0 ? 'var(--accent)' : 'var(--text-muted)' }}>
                      {i === 0 ? 'M+0 (First)' : `M+${i}`}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {cohortList.map((cl) => {
                  const size = getSize(cl)
                  return (
                    <tr key={cl}>
                      <td style={{ padding: '6px 12px', fontWeight: 600, fontSize: 12,
                        color: 'var(--text-primary)', whiteSpace: 'nowrap' }}>{cl}</td>
                      <td style={{ padding: '6px 10px', textAlign: 'center', fontSize: 12,
                        color: 'var(--text-secondary)' }}>{fmtN(size)}</td>
                      {Array.from({ length: MAX_PERIODS }, (_, p) => {
                        const pct  = getPct(cl, p)
                        const { bg, color } = cellColor(pct, p === 0)
                        const isHov = hovered?.cohort === cl && hovered?.period === p
                        const customers = pct && size ? Math.round(size * pct / 100) : null
                        return (
                          <td key={p} style={{ padding: '4px 6px', textAlign: 'center' }}>
                            {pct !== null ? (
                              <div
                                onMouseEnter={() => setHovered({ cohort: cl, period: p, pct, customers, size })}
                                onMouseLeave={() => setHovered(null)}
                                style={{
                                  background: isHov ? 'var(--accent)' : bg,
                                  color     : isHov ? '#fff' : color,
                                  borderRadius: 6, padding: '5px 8px', fontSize: 12,
                                  fontWeight: 600, cursor: 'default', transition: 'background 0.15s', minWidth: 56,
                                }}
                              >
                                {pct}%
                              </div>
                            ) : (
                              <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: '5px 8px' }}>—</div>
                            )}
                          </td>
                        )
                      })}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        <div style={{ marginTop: 16, padding: '10px 14px', background: 'var(--bg-subtle)', borderRadius: 8,
          fontSize: 12, color: 'var(--text-secondary)', minHeight: 40, transition: 'all 0.2s' }}>
          {hovered ? (
            <span>
              <strong style={{ color: 'var(--text-primary)' }}>{hovered.cohort}</strong> cohort —
              &nbsp;{hovered.period === 0
                ? `${fmtN(hovered.size)} customers made their first purchase this month (100%)`
                : `${hovered.pct}% of the original ${fmtN(hovered.size)} customers
                   (≈ ${fmtN(hovered.customers)} people) came back ${hovered.period} month${hovered.period > 1 ? 's' : ''} after their first purchase`
              }
            </span>
          ) : (
            <span>👆 Hover any cell to see how many customers it represents</span>
          )}
        </div>
      </div>

      {/* ── M+1 retention trend across the selected cohorts ── */}
      <div className="card" style={{ padding: 24 }}>
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>M+1 Retention Trend</div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            % of each selected cohort that returned the very next month
          </div>
        </div>
        {loading ? <CardSkeleton rows={4} /> : (
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={periodTrend(1)}>
              <XAxis dataKey="cohort" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false}
                tickFormatter={v => `${v}%`} domain={[0, 'auto']} />
              <Tooltip
                contentStyle={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 8, fontSize: 12 }}
                formatter={v => [`${v}%`, 'M+1 Retention']}
              />
              <ReferenceLine y={5} stroke="var(--border-strong)" strokeDasharray="4 4"
                label={{ value: 'avg ~5%', position: 'right', fontSize: 10, fill: 'var(--text-muted)' }} />
              <Line type="monotone" dataKey="pct" stroke="var(--accent)" strokeWidth={2}
                dot={{ r: 4, fill: 'var(--accent)' }} activeDot={{ r: 6 }} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
