'use client'
import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  PieChart, Pie,
} from 'recharts'
import { Download } from 'lucide-react'
import { api } from '../lib/api'
import { StatCard, SegBadge, PageHeader, CardSkeleton } from '../components/UI'

// Return-risk segment colours (used by the distribution chart)
const RETURN_COLORS = {
  'No Returns': '#22c55e',
  'Low'       : '#3b82f6',
  'Medium'    : '#f59e0b',
  'High'      : '#ef4444',
}

// Axis labels for return-risk buckets (number of returns)
const RETURN_LABELS = {
  'No Returns': 'No Returns',
  'Low'       : '1-2 returns',
  'Medium'    : '3-4 returns',
  'High'      : '6+ returns',
}

// Churn-risk colours
const CHURN_COLORS = {
  'None'  : '#22c55e',
  'Low'   : '#14b8a6',
  'Medium': '#f59e0b',
  'High'  : '#ef4444',
}

// Axis labels for churn buckets (days since last purchase)
const CHURN_LABELS = {
  'None'  : '0-90 d',
  'Low'   : '91-180 d',
  'Medium': '181-365 d',
  'High'  : '365+ d',
}

// Churn-risk identification — how each level is assigned (by days since last purchase)
const CHURN_DESC = {
  'None'  : { criteria: 'Bought within last 90 days',        meaning: 'Active — healthy, low churn risk' },
  'Low'   : { criteria: 'Last purchase 91–180 days ago',     meaning: 'Cooling slightly — keep engaged' },
  'Medium': { criteria: 'Last purchase 181–365 days ago',    meaning: 'Drifting away — worth re-engaging' },
  'High'  : { criteria: 'No purchase in 365+ days',          meaning: 'Likely churned — win-back campaign' },
}

function fmt(n) {
  if (n == null) return '—'
  if (n >= 10000000) return `₹${(n / 10000000).toFixed(1)}Cr`
  if (n >= 100000)   return `₹${(n / 100000).toFixed(1)}L`
  if (n >= 1000)     return `₹${(n / 1000).toFixed(1)}K`
  return `₹${n}`
}
function fmtN(n) {
  if (n == null) return '—'
  if (n >= 10000000) return `${(n / 10000000).toFixed(1)}Cr`
  if (n >= 100000)   return `${(n / 100000).toFixed(1)}L`
  if (n >= 1000)     return `${(n / 1000).toFixed(1)}K`
  return `${n}`
}

// Return-risk hover descriptions
const RETURN_DESC = {
  'No Returns': { criteria: '0 returns on record',   meaning: 'Clean buyers — no returns yet' },
  'Low'       : { criteria: '1–2 returns',           meaning: 'Occasional returner — low concern' },
  'Medium'    : { criteria: '3–5 returns',           meaning: 'Frequent returner — watch margin impact' },
  'High'      : { criteria: '6+ returns',            meaning: 'Heavy returner — review profitability' },
}

// RFM segment assignment rules — actual number thresholds (shown inline) + plain-English meaning (hover)
const SEG_INFO = {
  'Champion'      : { criteria: 'Last 90 days · 5+ orders · ₹15,000+ spent',   meaning: 'Your best customers, active and high value.' },
  'Loyal'         : { criteria: 'Last 90 days · ₹5,000+ spent',                 meaning: 'Active and valuable but may not order as frequently as Champions.' },
  'New Customer'  : { criteria: '1 order ever · bought in last 30 days',        meaning: 'Just acquired, haven\'t repeated yet.' },
  'New This Month': { criteria: 'First-ever purchase in the selected month',    meaning: 'Just acquired, haven\'t repeated yet.' },
  'Promising'     : { criteria: 'Last 90 days · 1–2 orders',                     meaning: 'Recent but low frequency — potential to become Loyal if nurtured.' },
  'Need Attention': { criteria: '3+ orders · last purchase 91–180 days ago',    meaning: 'Were regular buyers, now slowing down.' },
  'At Risk'       : { criteria: '₹2,500+ spent · last purchase 181–365 days ago', meaning: 'Good history but drifting away.' },
  'Cannot Lose'   : { criteria: '₹5,000+ spent · silent for 180+ days',          meaning: 'High-value customers going quiet — worth aggressive re-engagement.' },
  'Lost'          : { criteria: 'No purchase in 365+ days',                      meaning: 'Likely churned — lowest priority for spend but worth a win-back campaign.' },
  'Occasional'    : { criteria: 'Seasonal',                                      meaning: 'Low frequency, moderate recency, low spend.' },
}

// Return-risk chart tooltip with segment details (works for bar + pie)
function ReturnTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const seg   = label || payload[0].name
  const count = payload[0].value
  const pct   = payload[0].payload?.pct
  const color = RETURN_COLORS[seg] || '#94a3b8'
  const desc  = RETURN_DESC[seg]
  return (
    <div style={{
      background: 'var(--bg-card)', border: '1px solid var(--border)',
      borderRadius: 12, padding: '12px 16px', fontSize: 12,
      boxShadow: 'var(--shadow-lg)', maxWidth: 240, pointerEvents: 'none',
    }}>
      {/* Segment name */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 8 }}>
        <span style={{ width: 10, height: 10, borderRadius: '50%', background: color, flexShrink: 0 }} />
        <span style={{ fontWeight: 700, fontSize: 13, color: 'var(--text-primary)' }}>{seg}</span>
      </div>
      {/* Count + share */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 10 }}>
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 2 }}>Customers</div>
          <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--text-primary)' }}>{fmtN(count)}</div>
        </div>
        {pct != null && (
          <div>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 2 }}>Share</div>
            <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--text-primary)' }}>{pct}%</div>
          </div>
        )}
      </div>
      {/* Criteria */}
      {desc && (
        <div style={{ borderTop: '1px solid var(--border)', paddingTop: 8 }}>
          <div style={{ color: 'var(--text-muted)', fontSize: 11, marginBottom: 4 }}>{desc.criteria}</div>
          <div style={{ color: color, fontWeight: 600, fontSize: 11 }}>{desc.meaning}</div>
        </div>
      )}
    </div>
  )
}

// Churn-risk chart tooltip with identification details (works for bar + donut)
function ChurnTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const seg   = label || payload[0].name
  const count = payload[0].value
  const pct   = payload[0].payload?.pct
  const color = CHURN_COLORS[seg] || '#94a3b8'
  const desc  = CHURN_DESC[seg]
  return (
    <div style={{
      background: 'var(--bg-card)', border: '1px solid var(--border)',
      borderRadius: 12, padding: '12px 16px', fontSize: 12,
      boxShadow: 'var(--shadow-lg)', maxWidth: 240, pointerEvents: 'none',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 8 }}>
        <span style={{ width: 10, height: 10, borderRadius: '50%', background: color, flexShrink: 0 }} />
        <span style={{ fontWeight: 700, fontSize: 13, color: 'var(--text-primary)' }}>{seg}</span>
      </div>
      <div style={{ display: 'flex', gap: 12, marginBottom: desc ? 10 : 0 }}>
        <div>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 2 }}>Customers</div>
          <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--text-primary)' }}>{fmtN(count)}</div>
        </div>
        {pct != null && (
          <div>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', marginBottom: 2 }}>Share</div>
            <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--text-primary)' }}>{pct}%</div>
          </div>
        )}
      </div>
      {desc && (
        <div style={{ borderTop: '1px solid var(--border)', paddingTop: 8 }}>
          <div style={{ color: 'var(--text-muted)', fontSize: 11, marginBottom: 4 }}>{desc.criteria}</div>
          <div style={{ color: color, fontWeight: 600, fontSize: 11 }}>{desc.meaning}</div>
        </div>
      )}
    </div>
  )
}

// Bar / Donut toggle for distribution charts
function ChartToggle({ value, onChange }) {
  return (
    <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
      {[['bar', 'Bar'], ['donut', 'Donut']].map(([v, lbl]) => (
        <button
          key={v}
          onClick={() => onChange(v)}
          style={{
            fontSize: 10, fontWeight: 600, padding: '3px 9px', borderRadius: 6, cursor: 'pointer',
            border: '1px solid var(--border)',
            background: value === v ? 'var(--accent-light)' : 'transparent',
            color: value === v ? 'var(--accent)' : 'var(--text-muted)',
          }}
        >{lbl}</button>
      ))}
    </div>
  )
}

// Renders a distribution as a bar chart or donut depending on `type`
function DistChart({ type, data, nameKey, colors, tooltip, labelMap }) {
  const tickFmt = labelMap ? (v) => labelMap[v] || v : undefined
  const lbl = (d) => (labelMap ? (labelMap[d[nameKey]] || d[nameKey]) : d[nameKey])
  if (type === 'donut') {
    return (
      <div>
        <ResponsiveContainer width="100%" height={170}>
          <PieChart>
            <Pie data={data} dataKey="customers" nameKey={nameKey} cx="50%" cy="50%" innerRadius={42} outerRadius={68} paddingAngle={2} strokeWidth={0}>
              {data.map((d, i) => <Cell key={i} fill={colors[d[nameKey]] || '#94a3b8'} />)}
            </Pie>
            <Tooltip content={tooltip} />
          </PieChart>
        </ResponsiveContainer>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px 14px', marginTop: 8, justifyContent: 'center' }}>
          {data.map((d, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11 }}>
              <span style={{ width: 9, height: 9, borderRadius: '50%', background: colors[d[nameKey]] || '#94a3b8', flexShrink: 0 }} />
              <span style={{ color: 'var(--text-secondary)' }}>{lbl(d)}</span>
              {d.pct != null && <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{d.pct}%</span>}
            </div>
          ))}
        </div>
      </div>
    )
  }
  return (
    <ResponsiveContainer width="100%" height={190}>
      <BarChart data={data} barCategoryGap="28%">
        <XAxis dataKey={nameKey} interval={0} tickFormatter={tickFmt} tick={{ fontSize: 10, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fontSize: 10, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} tickFormatter={fmtN} width={36} />
        <Tooltip content={tooltip} cursor={{ fill: 'var(--bg-hover)' }} />
        <Bar dataKey="customers" name="Customers" radius={[4, 4, 0, 0]}>
          {data.map((d, i) => <Cell key={i} fill={colors[d[nameKey]] || '#94a3b8'} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

const fadeUp = {
  hidden : { opacity: 0, y: 18 },
  visible: (i) => ({ opacity: 1, y: 0, transition: { delay: i * 0.07, duration: 0.35, ease: 'easeOut' } }),
}

// Calendar date helpers — the dashboard filters by the month range of the picked dates
const _pad = (n) => String(n).padStart(2, '0')
const toYMD = (d) => `${d.getFullYear()}-${_pad(d.getMonth() + 1)}-${_pad(d.getDate())}`
const TODAY_YMD = toYMD(new Date())
const monthLabelOf = (ym) =>
  ym ? new Date(ym + '-01T00:00:00').toLocaleDateString('en-IN', { month: 'short', year: 'numeric' }) : ''
const rangeLabel = (sm, em) =>
  !sm ? '' : (sm === em ? monthLabelOf(sm) : `${monthLabelOf(sm)} – ${monthLabelOf(em)}`)
// Enumerate YYYY-MM months from sm..em inclusive (for CSV export `months` param)
function monthsBetween(sm, em) {
  if (!sm) return []
  const out = []
  let [y, m] = sm.split('-').map(Number)
  const [ey, em2] = em.split('-').map(Number)
  while (y < ey || (y === ey && m <= em2)) {
    out.push(`${y}-${_pad(m)}`)
    m++; if (m > 12) { m = 1; y++ }
    if (out.length > 60) break
  }
  return out
}

// Channel filter → maps to channel_journey values in the data
const CHANNEL_OPTIONS = [
  { value: '',             label: 'All channels' },
  { value: 'Online Only',  label: 'Online' },
  { value: 'Offline Only', label: 'Offline' },
  { value: 'Both',         label: 'Both' },
]

const selectStyle = {
  padding: '7px 11px', fontSize: 12, borderRadius: 8,
  border: '1px solid var(--border)', background: 'var(--bg-card)',
  color: 'var(--text-primary)', cursor: 'pointer', fontWeight: 500,
}

export default function DashboardPage() {
  const [summary,    setSummary]    = useState(null)
  const [rfm,        setRfm]        = useState([])
  const [returnRisk, setReturnRisk] = useState([])
  const [churn,      setChurn]      = useState([])
  const [loading,    setLoading]    = useState(true)
  const [draftStart, setDraftStart] = useState('')  // calendar input (not yet applied)
  const [draftEnd,   setDraftEnd]   = useState('')
  const [startDate,  setStartDate]  = useState('')  // APPLIED from (YYYY-MM-DD); '' = All time
  const [endDate,    setEndDate]    = useState('')  // APPLIED to
  const [channel,    setChannel]    = useState('')   // '' = all channels (channel_journey value)
  const [returnType, setReturnType] = useState('bar')   // bar | donut
  const [churnType,  setChurnType]  = useState('bar')   // bar | donut

  const startMonth = startDate ? startDate.slice(0, 7) : ''   // YYYY-MM derived from the calendar
  const endMonth   = endDate   ? endDate.slice(0, 7)   : startMonth

  useEffect(() => {
    setLoading(true)
    const period = { start_month: startMonth, end_month: endMonth }
    Promise.all([
      api.getSegmentSummary({ ...period, channel_journey: channel }),
      api.getRFM({ ...period, channel_journey: channel }),
      api.getReturnRisk({ ...period, channel_journey: channel }),
      api.getChurn({ ...period, channel_journey: channel }),
    ]).then(([s, r, rr, c]) => {
      setSummary(s)
      setRfm(r.segments || [])
      const rOrder = Object.keys(RETURN_LABELS)   // No Returns → Low → Medium → High
      setReturnRisk((rr || []).slice().sort(
        (a, b) => rOrder.indexOf(a.return_risk) - rOrder.indexOf(b.return_risk)
      ))
      setChurn(c || [])
    }).finally(() => setLoading(false))
  }, [startMonth, endMonth, channel])

  const monthLabel  = rangeLabel(startMonth, endMonth)
  const chanLabel   = CHANNEL_OPTIONS.find(c => c.value === channel)?.label
  const monthsCsv   = monthsBetween(startMonth, endMonth).join(',')   // for CSV export `months`
  // Per-segment / per-channel CSV — respects the active period + channel filters
  const segExportUrl  = (seg) => api.getExportUrl({ rfm_segment: seg, channel_journey: channel, months: monthsCsv })
  const cardExportUrl = (cj)  => api.getExportUrl({ channel_journey: cj, months: monthsCsv })

  // Date range applies only on "Apply" — draft inputs vs applied filter
  const applyDates = () => { setStartDate(draftStart); setEndDate(draftEnd) }
  const resetAll   = () => { setDraftStart(''); setDraftEnd(''); setStartDate(''); setEndDate(''); setChannel('') }
  const dirty      = draftStart !== startDate || draftEnd !== endDate

  const stats = [
    { label: 'Total Customers',   value: summary ? fmtN(summary.total_customers)      : null },
    { label: 'Online Customers',  value: summary ? fmtN(summary.online_customers)     : null, csvUrl: cardExportUrl('Online Only') },
    { label: 'Offline Customers', value: summary ? fmtN(summary.offline_customers)    : null, csvUrl: cardExportUrl('Offline Only') },
    { label: 'Both Channels',     value: summary ? fmtN(summary.both_customers)       : null, csvUrl: cardExportUrl('Both') },
    { label: 'Repeat Customers',  value: summary ? fmtN(summary.repeat_customers)     : null, sub: summary ? `${summary.repeat_rate_pct}% repeat rate` : null,
      csvUrl: api.getExportUrl({ customer_type: 'Repeat', channel_journey: channel, months: monthsCsv }) },
    { label: 'New Customers',     value: summary ? fmtN(summary.new_customers)        : null,
      csvUrl: api.getExportUrl({ customer_type: 'New', channel_journey: channel, months: monthsCsv }) },
  ]

  return (
    <div className="page-content">
      <PageHeader
        title="Dashboard"
        subtitle="Customer intelligence overview across all channels"
        action={
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 600 }}>
              {startMonth ? rangeLabel(startMonth, endMonth) : 'All time'}
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 600 }}>From</span>
              <input type="date" style={selectStyle} value={draftStart} max={draftEnd || TODAY_YMD}
                onChange={e => setDraftStart(e.target.value)} title="Start date (leave empty for all time)" />
              <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 600 }}>To</span>
              <input type="date" style={selectStyle} value={draftEnd} min={draftStart} max={TODAY_YMD}
                onChange={e => setDraftEnd(e.target.value)} title="End date" />
            </div>
            <button className="btn-primary" onClick={applyDates} disabled={!dirty || loading}
              style={{ opacity: (!dirty || loading) ? 0.5 : 1 }}>
              {loading ? 'Loading…' : 'Apply'}
            </button>
            <select style={selectStyle} value={channel} onChange={e => setChannel(e.target.value)} title="Filter by channel">
              {CHANNEL_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            <button className="btn-ghost" onClick={resetAll}>
              Reset
            </button>
          </div>
        }
      />

      {/* Stat cards — one row on desktop, collapses cleanly on smaller screens */}
      <div className="stats-grid stats-grid--dash" style={{ marginBottom: 24 }}>
        {stats.map((s, i) => (
          <motion.div key={s.label} custom={i} variants={fadeUp} initial="hidden" animate="visible">
            <StatCard {...s} compact />
          </motion.div>
        ))}
      </div>

      {/* Distribution charts — Return Risk + Churn Risk side by side */}
      <div className="dist-charts" style={{ marginBottom: 20 }}>

        {/* Return Behaviour */}
        <motion.div
          className="card"
          style={{ padding: 20 }}
          initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.35, duration: 0.4 }}
          whileHover={{ boxShadow: 'var(--shadow-md)', transition: { duration: 0.2 } }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8, marginBottom: 4 }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>Return Behaviour</div>
            <ChartToggle value={returnType} onChange={setReturnType} />
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 14 }}>
            Distribution by return behaviour / Qty
            {(startMonth || channel) &&<span style={{ color: 'var(--accent)' }}> · {monthLabel}{channel ? ` · ${chanLabel}` : ''}</span>}
          </div>
          {loading ? <CardSkeleton rows={4} /> : (
            <DistChart type={returnType} data={returnRisk} nameKey="return_risk" colors={RETURN_COLORS} tooltip={<ReturnTooltip />} labelMap={RETURN_LABELS} />
          )}
        </motion.div>

        {/* Churn Risk */}
        <motion.div
          className="card"
          style={{ padding: 20 }}
          initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4, duration: 0.4 }}
          whileHover={{ boxShadow: 'var(--shadow-md)', transition: { duration: 0.2 } }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8, marginBottom: 4 }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>Churn Risk</div>
            <ChartToggle value={churnType} onChange={setChurnType} />
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 14 }}>
            Cohort distribution by purchase
            {(startMonth || channel) &&<span style={{ color: 'var(--accent)' }}> · {monthLabel}{channel ? ` · ${chanLabel}` : ''}</span>}
          </div>
          {loading ? <CardSkeleton rows={4} /> : (
            <DistChart type={churnType} data={churn} nameKey="churn_risk" colors={CHURN_COLORS} tooltip={<ChurnTooltip />} labelMap={CHURN_LABELS} />
          )}
        </motion.div>
      </div>

      {/* Segment table */}
      <motion.div
        className="card"
        style={{ padding: 24 }}
        initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.55, duration: 0.4 }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
            Customer Category
            {(startMonth || channel) &&<span style={{ fontSize: 12, color: 'var(--accent)', marginLeft: 8, fontWeight: 400 }}>— {monthLabel}{channel ? ` · ${chanLabel}` : ''}</span>}
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Download icon exports that segment's customers (selected period + channel)</div>
        </div>
        {loading ? <CardSkeleton rows={8} /> : (
          <div className="table-wrap">
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  {['Segment', 'Customers', '% Share', 'Avg LTV', 'Export'].map(h => (
                    <th key={h} style={{
                      padding: '8px 14px', textAlign: h === 'Export' ? 'right' : 'left', fontSize: 11,
                      fontWeight: 600, color: 'var(--text-muted)',
                      textTransform: 'uppercase', letterSpacing: '0.06em', whiteSpace: 'nowrap',
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rfm.map((r, i) => (
                  <motion.tr
                    key={i}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.6 + i * 0.04, duration: 0.25 }}
                    style={{ borderBottom: '1px solid var(--border)' }}
                    whileHover={{ backgroundColor: 'var(--bg-hover)' }}
                  >
                    <td style={{ padding: '10px 14px', verticalAlign: 'top' }} title={SEG_INFO[r.rfm_segment]?.meaning || ''}>
                      <SegBadge segment={r.rfm_segment} />
                      {SEG_INFO[r.rfm_segment]?.criteria && (
                        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 5, maxWidth: 340, lineHeight: 1.4 }}>
                          {SEG_INFO[r.rfm_segment].criteria}
                        </div>
                      )}
                    </td>
                    <td style={{ padding: '10px 14px', fontWeight: 600, verticalAlign: 'top' }}>{fmtN(r.customers)}</td>
                    <td style={{ padding: '10px 14px', color: 'var(--text-secondary)', verticalAlign: 'top' }}>{r.pct}%</td>
                    <td style={{ padding: '10px 14px', color: 'var(--text-secondary)', verticalAlign: 'top' }}>{fmt(r.avg_ltv)}</td>
                    <td style={{ padding: '10px 14px', textAlign: 'right', verticalAlign: 'top' }}>
                      <a
                        href={segExportUrl(r.rfm_segment)}
                        title={`Download ${r.rfm_segment} customers as CSV${channel ? ` (${chanLabel})` : ''}`}
                        className="seg-export-btn"
                        style={{
                          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                          width: 30, height: 30, borderRadius: 8,
                          color: 'var(--text-secondary)', border: '1px solid var(--border)',
                          textDecoration: 'none',
                        }}
                      >
                        <Download size={15} />
                      </a>
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </motion.div>
    </div>
  )
}
