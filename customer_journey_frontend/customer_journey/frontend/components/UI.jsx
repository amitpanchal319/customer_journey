'use client'
import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { TrendingUp, TrendingDown, Download } from 'lucide-react'

// ── Shared animation variants ─────────────────────────────────────────────────
const fadeUp = {
  hidden:  { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: 'easeOut' } },
}

const staggerList = {
  hidden:  {},
  visible: { transition: { staggerChildren: 0.04 } },
}

const rowVariant = {
  hidden:  { opacity: 0, x: -8 },
  visible: { opacity: 1, x: 0, transition: { duration: 0.25, ease: 'easeOut' } },
}

// ── Stat Card ─────────────────────────────────────────────────────────────────
export function StatCard({ label, value, sub, period, color = 'blue', trend, index = 0, csvUrl, compact = false }) {
  const download = (e) => { e?.stopPropagation?.(); if (csvUrl) window.location.href = csvUrl }
  const sz = compact
    ? { pad: '16px 18px', minH: 110, label: 10, value: 25, meta: 10, mb: 12, skelW: 64, skelH: 25 }
    : { pad: '20px 22px', minH: 116, label: 11, value: 32, meta: 11, mb: 14, skelW: 90, skelH: 32 }
  return (
    <motion.div
      className="card"
      style={{ padding: sz.pad, minHeight: sz.minH, display: 'flex', flexDirection: 'column', justifyContent: 'space-between', position: 'relative' }}
      variants={fadeUp}
      initial="hidden"
      animate="visible"
      transition={{ delay: index * 0.06 }}
      whileHover={{
        y: -4,
        boxShadow: '0 12px 32px rgba(28,26,14,0.12)',
        transition: { duration: 0.18, ease: 'easeOut' },
      }}
    >
      {/* Row 1: label + optional CSV button (top-right) */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: sz.mb, gap: 8 }}>
        <div style={{ fontSize: sz.label, color: 'var(--text-muted)', fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {label}
        </div>
        {csvUrl && (
          <button
            onClick={download}
            className="seg-export-btn"
            title={`Download ${label} as CSV`}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: 'var(--text-secondary)', background: 'var(--bg-hover)',
              border: '1px solid var(--border)', borderRadius: 7,
              width: 28, height: 28, padding: 0, cursor: 'pointer', flexShrink: 0,
            }}
          >
            <Download size={14} />
          </button>
        )}
      </div>

      {/* Row 2: value + sub + period — inline, always same line */}
      <div style={{ lineHeight: 1.1 }}>
        <span style={{
          fontSize: sz.value, fontWeight: 800, fontFamily: 'var(--font-display)',
          letterSpacing: '-0.02em', color: 'var(--text-primary)',
          verticalAlign: 'baseline', whiteSpace: 'nowrap',
        }}>
          {value ?? <span className="skeleton" style={{ display: 'inline-block', width: sz.skelW, height: sz.skelH, borderRadius: 6 }} />}
        </span>
        {sub && (
          <span style={{ fontSize: sz.meta, color: 'var(--text-secondary)', fontWeight: 500, marginLeft: 8, verticalAlign: 'baseline' }}>
            {sub}
          </span>
        )}
        {period && (
          <span style={{ fontSize: sz.meta, color: 'var(--text-muted)', fontWeight: 500, marginLeft: sub ? 4 : 8, verticalAlign: 'baseline' }}>
            {period}
          </span>
        )}
      </div>

      {/* Row 3: trend only */}
      {trend != null && (
        <div style={{ marginTop: 8 }}>
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }}
            style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: trend >= 0 ? 'var(--green)' : 'var(--red)', fontWeight: 600 }}
          >
            {trend >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
            {Math.abs(trend)}% vs last month
          </motion.div>
        </div>
      )}
    </motion.div>
  )
}

// ── RFM Badge ─────────────────────────────────────────────────────────────────
const SEG_MAP = {
  'Champion'      : 'champion',
  'Loyal'         : 'loyal',
  'New Customer'  : 'new',
  'Promising'     : 'promising',
  'Need Attention': 'need',
  'At Risk'       : 'risk',
  'Cannot Lose'   : 'cannot',
  'Lost'          : 'lost',
  'Occasional'    : 'occasional',
  'New This Month': 'new',
}

export function SegBadge({ segment }) {
  const cls = SEG_MAP[segment] || 'occasional'
  return (
    <motion.span
      className={`badge seg-${cls}`}
      whileHover={{ scale: 1.08 }}
      transition={{ duration: 0.15 }}
    >
      {segment || '—'}
    </motion.span>
  )
}

// ── Churn Badge ───────────────────────────────────────────────────────────────
export function ChurnBadge({ risk }) {
  const map = { High: 'red', Medium: 'amber', Low: 'teal', None: 'green' }
  const color = map[risk] || 'blue'
  return (
    <motion.span
      className="badge"
      style={{ background: `var(--${color}-light)`, color: `var(--${color})` }}
      whileHover={{ scale: 1.08 }}
      transition={{ duration: 0.15 }}
    >
      {risk || '—'}
    </motion.span>
  )
}

// ── Channel Badge ─────────────────────────────────────────────────────────────
export function ChannelBadge({ channel }) {
  const map = {
    'Online Only' : { bg: 'var(--accent-light)',  c: 'var(--accent)' },
    'Offline Only': { bg: 'var(--amber-light)',   c: 'var(--amber)' },
    'Both'        : { bg: 'var(--purple-light)',  c: 'var(--purple)' },
    'Omnichannel' : { bg: 'var(--purple-light)',  c: 'var(--purple)' },
  }
  const style = map[channel] || { bg: 'var(--bg-subtle)', c: 'var(--text-secondary)' }
  return (
    <motion.span
      className="badge"
      style={{ background: style.bg, color: style.c }}
      whileHover={{ scale: 1.08 }}
      transition={{ duration: 0.15 }}
    >
      {channel || '—'}
    </motion.span>
  )
}

// ── Skeleton loader ───────────────────────────────────────────────────────────
export function Skeleton({ w = '100%', h = 16, mb = 8 }) {
  return <div className="skeleton" style={{ width: w, height: h, marginBottom: mb }} />
}

export function CardSkeleton({ rows = 4 }) {
  return (
    <div className="card" style={{ padding: 20 }}>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} h={i === 0 ? 20 : 14} w={i === 0 ? '60%' : `${70 + (i * 7) % 25}%`} mb={10} />
      ))}
    </div>
  )
}

// ── Page header ───────────────────────────────────────────────────────────────
export function PageHeader({ title, subtitle, action }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 28, flexWrap: 'wrap', gap: 12 }}
    >
      <div>
        <h1 style={{
          fontFamily: 'var(--font-display)', fontSize: 'clamp(20px, 4vw, 24px)',
          fontWeight: 800, letterSpacing: '-0.02em', color: 'var(--text-primary)',
        }}>
          {title}
        </h1>
        {subtitle && <p style={{ fontSize: 14, color: 'var(--text-secondary)', marginTop: 4 }}>{subtitle}</p>}
      </div>
      {action && <div style={{ flexShrink: 0 }}>{action}</div>}
    </motion.div>
  )
}

// ── Table with staggered rows ─────────────────────────────────────────────────
export function Table({ columns, rows, onRowClick }) {
  return (
    <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: '1px solid var(--border)' }}>
            {columns.map(col => (
              <th key={col.key} style={{
                padding: '10px 14px', textAlign: 'left', fontSize: 11,
                fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase',
                letterSpacing: '0.06em', whiteSpace: 'nowrap',
              }}>{col.label}</th>
            ))}
          </tr>
        </thead>
        <motion.tbody variants={staggerList} initial="hidden" animate="visible">
          {rows.map((row, i) => (
            <motion.tr
              key={i}
              variants={rowVariant}
              onClick={() => onRowClick?.(row)}
              style={{
                borderBottom: '1px solid var(--border)',
                cursor: onRowClick ? 'pointer' : 'default',
              }}
              whileHover={onRowClick ? { backgroundColor: 'var(--bg-hover)' } : {}}
              transition={{ duration: 0.1 }}
            >
              {columns.map(col => (
                <td key={col.key} style={{ padding: '11px 14px', color: 'var(--text-primary)', whiteSpace: 'nowrap' }}>
                  {col.render ? col.render(row[col.key], row) : (row[col.key] ?? '—')}
                </td>
              ))}
            </motion.tr>
          ))}
        </motion.tbody>
      </table>

      <AnimatePresence>
        {rows.length === 0 && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)', fontSize: 14 }}
          >
            No data found
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Metric row ────────────────────────────────────────────────────────────────
export function MetricRow({ label, value, highlight }) {
  return (
    <motion.div
      whileHover={{ x: 2 }}
      transition={{ duration: 0.15 }}
      style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '9px 0', borderBottom: '1px solid var(--border)',
      }}
    >
      <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{label}</span>
      <span style={{ fontSize: 13, fontWeight: 600, color: highlight ? 'var(--accent)' : 'var(--text-primary)' }}>
        {value ?? '—'}
      </span>
    </motion.div>
  )
}

// ── Empty state ───────────────────────────────────────────────────────────────
export function Empty({ icon: Icon, title, sub }) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
      style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-muted)' }}
    >
      {Icon && (
        <motion.div
          animate={{ y: [0, -6, 0] }}
          transition={{ repeat: Infinity, duration: 3, ease: 'easeInOut' }}
        >
          <Icon size={40} style={{ margin: '0 auto 16px', opacity: 0.4 }} />
        </motion.div>
      )}
      <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>{title}</div>
      {sub && <div style={{ fontSize: 13 }}>{sub}</div>}
    </motion.div>
  )
}

// ── Animated card wrapper ─────────────────────────────────────────────────────
export function AnimCard({ children, style, className, delay = 0 }) {
  return (
    <motion.div
      className={`card ${className || ''}`}
      style={style}
      variants={fadeUp}
      initial="hidden"
      animate="visible"
      transition={{ delay }}
      whileHover={{
        y: -3,
        boxShadow: '0 8px 32px rgba(0,0,0,0.10)',
        transition: { duration: 0.2 },
      }}
    >
      {children}
    </motion.div>
  )
}
