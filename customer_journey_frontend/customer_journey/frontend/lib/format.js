// lib/format.js
// Single source of truth for number / currency / date formatting.
// Every page imports from here — never redefine fmt helpers locally.

/** Format a number as Indian-style currency: ₹1.2Cr / ₹3.4L / ₹5.6K */
export function fmtINR(n) {
  if (n == null || isNaN(n)) return '—'
  if (n >= 10000000) return `₹${(n / 10000000).toFixed(1)}Cr`
  if (n >= 100000)   return `₹${(n / 100000).toFixed(1)}L`
  if (n >= 1000)     return `₹${(n / 1000).toFixed(1)}K`
  return `₹${Math.round(n)}`
}

/** Format a plain number: 1.2Cr / 3.4L / 5.6K */
export function fmtNum(n) {
  if (n == null || isNaN(n)) return '—'
  if (n >= 10000000) return `${(n / 10000000).toFixed(1)}Cr`
  if (n >= 100000)   return `${(n / 100000).toFixed(1)}L`
  if (n >= 1000)     return `${(n / 1000).toFixed(1)}K`
  return `${n}`
}

/** Format a date string for display: 5 Mar 2026 */
export function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

/**
 * Build a list of month dropdown options going back `count` months.
 * Returns [{ value: 'YYYY-MM', label: 'Mar 2026' }, ...]
 * Pass `allLabel` to prepend an "all" option with value ''.
 */
export function getMonthOptions(count = 24, { allLabel = null, monthStyle = 'short' } = {}) {
  const opts = []
  if (allLabel) opts.push({ value: '', label: allLabel })
  const now = new Date()
  for (let i = 0; i < count; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
    opts.push({
      value: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`,
      label: d.toLocaleDateString('en-IN', { month: monthStyle, year: 'numeric' }),
    })
  }
  return opts
}

// Legacy aliases — keep old call-sites working
export const fmt  = fmtINR
export const fmtN = fmtNum
