'use client'
import { useState, useEffect, createContext, useContext } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { motion, AnimatePresence } from 'framer-motion'
import {
  LayoutDashboard, Search, Store, Bot, ArrowLeftRight,
  ShoppingBag, Globe, Layers, Download, Sun, Moon,
  ChevronLeft, Menu, X, Activity,
} from 'lucide-react'

// ── Theme context ─────────────────────────────────────────────────────────────
const ThemeCtx = createContext({ dark: false, toggle: () => {} })
export const useTheme = () => useContext(ThemeCtx)

export function ThemeProvider({ children }) {
  const [dark, setDark] = useState(false)
  useEffect(() => {
    const saved = localStorage.getItem('cj-theme')
    if (saved === 'dark' || (!saved && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
      setDark(true)
      document.documentElement.classList.add('dark')
    }
  }, [])
  const toggle = () => {
    setDark(d => {
      const next = !d
      document.documentElement.classList.toggle('dark', next)
      localStorage.setItem('cj-theme', next ? 'dark' : 'light')
      return next
    })
  }
  return <ThemeCtx.Provider value={{ dark, toggle }}>{children}</ThemeCtx.Provider>
}

// ── Nav items ─────────────────────────────────────────────────────────────────
const NAV = [
  { label: 'Dashboard',       href: '/',              icon: LayoutDashboard },
  { label: 'Customer 360',    href: '/customer',       icon: Search },
  { divider: true, label: 'CHANNELS' },
  { label: 'Online',          href: '/online',         icon: Globe },
  { label: 'Offline (EBO)',   href: '/offline',        icon: Store },
  { label: 'Both',            href: '/both',           icon: Layers },
  { divider: true, label: 'ANALYTICS' },
  { label: 'Cohorts',         href: '/cohorts',        icon: Activity },
  { label: 'Migration',       href: '/migration',      icon: ArrowLeftRight },
  { label: 'Stores',          href: '/stores',         icon: ShoppingBag },
  { label: 'Export',          href: '/export',         icon: Download },
  { divider: true, label: 'AI' },
  { label: 'AI Agent',        href: '/agent',          icon: Bot },
]

const BOTTOM_NAV = [
  { label: 'Home',     href: '/',         icon: LayoutDashboard },
  { label: 'Customer', href: '/customer', icon: Search },
  { label: 'Cohorts',  href: '/cohorts',  icon: Activity },
  { label: 'Stores',   href: '/stores',   icon: ShoppingBag },
  { label: 'AI',       href: '/agent',    icon: Bot },
]

// ── Nav link (shared by drawer + desktop sidebar) ─────────────────────────────
function NavLink({ item, collapsed, onClick }) {
  const pathname = usePathname()
  const Icon = item.icon
  const active = pathname === item.href
  return (
    <motion.div whileHover={{ x: collapsed ? 0 : 3 }} transition={{ duration: 0.15 }}>
      <Link
        href={item.href}
        onClick={onClick}
        style={{
          display: 'flex', alignItems: 'center',
          gap: 10,
          padding: collapsed ? '10px 0' : '9px 12px',
          borderRadius: 8, marginBottom: 2, textDecoration: 'none',
          justifyContent: collapsed ? 'center' : 'flex-start',
          background: active ? 'var(--accent-light)' : 'transparent',
          color: active ? 'var(--accent)' : 'var(--text-secondary)',
          fontWeight: active ? 600 : 400, fontSize: 13,
          transition: 'background 0.15s, color 0.15s',
          position: 'relative',
        }}
        onMouseEnter={e => { if (!active) e.currentTarget.style.background = 'var(--bg-hover)' }}
        onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent' }}
      >
        {active && (
          <motion.div
            layoutId="sidebarActiveIndicator"
            style={{
              position: 'absolute', left: 0, top: '20%', bottom: '20%',
              width: 3, borderRadius: '0 2px 2px 0', background: 'var(--accent)',
            }}
            transition={{ type: 'spring', stiffness: 400, damping: 30 }}
          />
        )}
        <Icon size={16} style={{ flexShrink: 0 }} />
        {!collapsed && <span style={{ overflow: 'hidden', whiteSpace: 'nowrap' }}>{item.label}</span>}
      </Link>
    </motion.div>
  )
}

// ── Desktop Sidebar ───────────────────────────────────────────────────────────
function DesktopSidebar({ collapsed, onCollapse }) {
  const { dark, toggle } = useTheme()

  return (
    <motion.aside
      animate={{ width: collapsed ? 64 : 240 }}
      transition={{ type: 'tween', duration: 0.22, ease: 'easeInOut' }}
      style={{
        background: 'var(--sidebar-bg)', borderRight: '1px solid var(--border)',
        display: 'flex', flexDirection: 'column', overflow: 'hidden',
        flexShrink: 0, position: 'sticky', top: 0, height: '100vh',
      }}
    >
      {/* Logo */}
      {collapsed ? (
        /* Collapsed: brand mark icon acts as expand toggle */
        <motion.div
          onClick={onCollapse}
          whileHover={{ scale: 1.08 }} whileTap={{ scale: 0.93 }}
          style={{
            display: 'flex', justifyContent: 'center', alignItems: 'center',
            padding: '14px 0', borderBottom: '1px solid var(--border)',
            minHeight: 60, cursor: 'pointer',
          }}
        >
          <div style={{
            width: 32, height: 32, borderRadius: 9,
            background: 'linear-gradient(135deg, var(--accent) 0%, var(--sand) 100%)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 2px 8px rgba(97,112,56,0.30)',
          }}>
            <Activity size={15} color="white" strokeWidth={2.2} />
          </div>
        </motion.div>
      ) : (
        /* Expanded: brand icon + name + collapse button */
        <div style={{
          padding: '12px 14px', display: 'flex', alignItems: 'center',
          justifyContent: 'space-between', borderBottom: '1px solid var(--border)', minHeight: 60,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            <div style={{
              width: 32, height: 32, borderRadius: 9, flexShrink: 0,
              background: 'linear-gradient(135deg, var(--accent) 0%, var(--sand) 100%)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 2px 8px rgba(97,112,56,0.30)',
            }}>
              <Activity size={15} color="white" strokeWidth={2.2} />
            </div>
            <div>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 800, letterSpacing: '-0.01em', lineHeight: 1.1 }}>
                <span style={{ color: 'var(--text-primary)' }}>C</span>
                <span style={{ color: 'var(--accent)' }}>Journey</span>
              </div>
              <div style={{ fontSize: 9.5, color: 'var(--text-muted)', marginTop: 2, letterSpacing: '0.04em', textTransform: 'uppercase', fontWeight: 500 }}>
                Customer Intelligence
              </div>
            </div>
          </div>
          <motion.button
            whileHover={{ scale: 1.12 }} whileTap={{ scale: 0.9 }}
            onClick={onCollapse}
            style={{
              background: 'var(--bg-hover)', border: 'none', borderRadius: 7,
              width: 26, height: 26, cursor: 'pointer', display: 'flex',
              alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)',
              flexShrink: 0,
            }}
          >
            <ChevronLeft size={13} />
          </motion.button>
        </div>
      )}

      {/* Nav */}
      <nav style={{ flex: 1, overflowY: 'auto', padding: '10px 8px' }}>
        {NAV.map((item, i) => {
          if (item.divider) return collapsed ? null : (
            <div key={i} style={{ padding: '14px 10px 5px', display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{
                fontSize: 9, fontWeight: 700, letterSpacing: '0.12em',
                color: 'var(--text-muted)', textTransform: 'uppercase', whiteSpace: 'nowrap',
              }}>{item.label}</span>
              <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
            </div>
          )
          return <NavLink key={item.href} item={item} collapsed={collapsed} />
        })}
      </nav>

      {/* Theme toggle */}
      <div style={{ padding: '10px 8px', borderTop: '1px solid var(--border)' }}>
        <motion.button
          whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.97 }}
          onClick={toggle}
          style={{
            width: '100%', display: 'flex', alignItems: 'center',
            gap: 9, padding: collapsed ? '10px 0' : '8px 10px',
            background: 'var(--bg-hover)', border: 'none', borderRadius: 8,
            cursor: 'pointer', color: 'var(--text-secondary)', fontSize: 13,
            justifyContent: collapsed ? 'center' : 'flex-start',
          }}
        >
          <AnimatePresence mode="wait">
            <motion.div
              key={dark ? 'sun' : 'moon'}
              initial={{ rotate: -60, opacity: 0, scale: 0.7 }}
              animate={{ rotate: 0, opacity: 1, scale: 1 }}
              exit={{ rotate: 60, opacity: 0, scale: 0.7 }}
              transition={{ duration: 0.25 }}
            >
              {dark ? <Sun size={15} /> : <Moon size={15} />}
            </motion.div>
          </AnimatePresence>
          <AnimatePresence>
            {!collapsed && (
              <motion.span
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
                style={{ fontWeight: 500 }}
              >
                {dark ? 'Light Mode' : 'Dark Mode'}
              </motion.span>
            )}
          </AnimatePresence>
        </motion.button>
      </div>
    </motion.aside>
  )
}

// ── Mobile top header ─────────────────────────────────────────────────────────
function MobileHeader({ onMenuOpen }) {
  const { dark, toggle } = useTheme()
  return (
    <header style={{
      position: 'fixed', top: 0, left: 0, right: 0, height: 56,
      background: 'var(--sidebar-bg)', borderBottom: '1px solid var(--border)',
      display: 'flex', alignItems: 'center', padding: '0 14px', zIndex: 30, gap: 10,
    }}>
      <motion.button
        whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.88 }}
        onClick={onMenuOpen}
        style={{
          background: 'var(--bg-hover)', border: 'none', borderRadius: 8,
          width: 36, height: 36, cursor: 'pointer', display: 'flex',
          alignItems: 'center', justifyContent: 'center', color: 'var(--text-secondary)',
          flexShrink: 0,
        }}
      >
        <Menu size={17} />
      </motion.button>

      <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{
          width: 26, height: 26, borderRadius: 7, flexShrink: 0,
          background: 'linear-gradient(135deg, var(--accent) 0%, var(--sand) 100%)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          boxShadow: '0 2px 6px rgba(97,112,56,0.28)',
        }}>
          <Activity size={13} color="white" strokeWidth={2.2} />
        </div>
        <div style={{ fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 800, letterSpacing: '-0.01em' }}>
          <span style={{ color: 'var(--text-primary)' }}>C</span>
          <span style={{ color: 'var(--accent)' }}>Journey</span>
        </div>
      </div>

      <motion.button
        whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.88 }}
        onClick={toggle}
        style={{
          background: 'var(--bg-hover)', border: 'none', borderRadius: 8,
          width: 36, height: 36, cursor: 'pointer', display: 'flex',
          alignItems: 'center', justifyContent: 'center', color: 'var(--text-secondary)',
          flexShrink: 0,
        }}
      >
        <AnimatePresence mode="wait">
          <motion.div
            key={dark ? 'sun' : 'moon'}
            initial={{ rotate: -60, opacity: 0, scale: 0.7 }}
            animate={{ rotate: 0, opacity: 1, scale: 1 }}
            exit={{ rotate: 60, opacity: 0, scale: 0.7 }}
            transition={{ duration: 0.25 }}
          >
            {dark ? <Sun size={15} /> : <Moon size={15} />}
          </motion.div>
        </AnimatePresence>
      </motion.button>
    </header>
  )
}

// ── Mobile drawer ─────────────────────────────────────────────────────────────
function MobileDrawer({ open, onClose }) {
  const { dark, toggle } = useTheme()
  const pathname = usePathname()

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
            style={{
              position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)',
              zIndex: 40, backdropFilter: 'blur(3px)',
            }}
          />
          <motion.aside
            key="drawer"
            initial={{ x: -280 }} animate={{ x: 0 }} exit={{ x: -280 }}
            transition={{ type: 'spring', stiffness: 320, damping: 32 }}
            style={{
              position: 'fixed', top: 0, left: 0, height: '100dvh', width: 270,
              zIndex: 50, background: 'var(--sidebar-bg)', borderRight: '1px solid var(--border)',
              display: 'flex', flexDirection: 'column', overflowY: 'auto',
            }}
          >
            {/* Header */}
            <div style={{
              padding: '14px 16px', display: 'flex', alignItems: 'center',
              justifyContent: 'space-between', borderBottom: '1px solid var(--border)', minHeight: 60,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                <div style={{
                  width: 30, height: 30, borderRadius: 8, flexShrink: 0,
                  background: 'linear-gradient(135deg, var(--accent) 0%, var(--sand) 100%)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  boxShadow: '0 2px 8px rgba(97,112,56,0.28)',
                }}>
                  <Activity size={14} color="white" strokeWidth={2.2} />
                </div>
                <div>
                  <div style={{ fontFamily: 'var(--font-display)', fontSize: 15, fontWeight: 800, letterSpacing: '-0.01em', lineHeight: 1.1 }}>
                    <span style={{ color: 'var(--text-primary)' }}>C</span>
                    <span style={{ color: 'var(--accent)' }}>Journey</span>
                  </div>
                  <div style={{ fontSize: 9.5, color: 'var(--text-muted)', marginTop: 1, letterSpacing: '0.04em', textTransform: 'uppercase', fontWeight: 500 }}>
                    Customer Intelligence
                  </div>
                </div>
              </div>
              <motion.button
                whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.9 }}
                onClick={onClose}
                style={{
                  background: 'var(--bg-hover)', border: 'none', borderRadius: 7,
                  width: 30, height: 30, cursor: 'pointer', display: 'flex',
                  alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)',
                }}
              >
                <X size={14} />
              </motion.button>
            </div>

            {/* Nav */}
            <nav style={{ flex: 1, overflowY: 'auto', padding: '10px 8px' }}>
              {NAV.map((item, i) => {
                if (item.divider) return (
                  <div key={i} style={{ padding: '14px 10px 5px', display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{
                      fontSize: 9, fontWeight: 700, letterSpacing: '0.12em',
                      color: 'var(--text-muted)', textTransform: 'uppercase', whiteSpace: 'nowrap',
                    }}>{item.label}</span>
                    <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
                  </div>
                )
                const Icon = item.icon
                const active = pathname === item.href
                return (
                  <Link key={item.href} href={item.href} onClick={onClose} style={{
                    display: 'flex', alignItems: 'center', gap: 11,
                    padding: '10px 12px', borderRadius: 8, marginBottom: 2,
                    textDecoration: 'none', fontSize: 13.5,
                    background: active ? 'var(--accent-light)' : 'transparent',
                    color: active ? 'var(--accent)' : 'var(--text-secondary)',
                    fontWeight: active ? 600 : 400, transition: 'background 0.15s',
                  }}
                  onMouseEnter={e => { if (!active) e.currentTarget.style.background = 'var(--bg-hover)' }}
                  onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent' }}
                  >
                    <Icon size={17} style={{ flexShrink: 0 }} />
                    {item.label}
                  </Link>
                )
              })}
            </nav>

            {/* Theme */}
            <div style={{ padding: '10px 8px', borderTop: '1px solid var(--border)' }}>
              <button onClick={toggle} style={{
                width: '100%', display: 'flex', alignItems: 'center', gap: 9,
                padding: '9px 12px', background: 'var(--bg-hover)', border: 'none',
                borderRadius: 8, cursor: 'pointer', color: 'var(--text-secondary)', fontSize: 13.5, fontWeight: 500,
              }}>
                {dark ? <Sun size={15} /> : <Moon size={15} />}
                {dark ? 'Light Mode' : 'Dark Mode'}
              </button>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}

// ── Mobile bottom nav ─────────────────────────────────────────────────────────
function MobileBottomNav() {
  const pathname = usePathname()
  return (
    <nav style={{
      position: 'fixed', bottom: 0, left: 0, right: 0,
      height: 60, background: 'var(--sidebar-bg)', borderTop: '1px solid var(--border)',
      display: 'flex', alignItems: 'center', justifyContent: 'space-around',
      zIndex: 30, paddingBottom: 'env(safe-area-inset-bottom)',
    }}>
      {BOTTOM_NAV.map(item => {
        const Icon = item.icon
        const active = pathname === item.href
        return (
          <Link key={item.href} href={item.href} style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            gap: 3, padding: '6px 0', textDecoration: 'none',
            color: active ? 'var(--accent)' : 'var(--text-muted)',
            flex: 1, transition: 'color 0.2s', position: 'relative',
          }}>
            {active && (
              <motion.div
                layoutId="bottomNavDot"
                style={{
                  position: 'absolute', top: 0, left: '50%',
                  transform: 'translateX(-50%)',
                  width: 28, height: 2,
                  background: 'var(--accent)', borderRadius: '0 0 3px 3px',
                }}
                transition={{ type: 'spring', stiffness: 400, damping: 30 }}
              />
            )}
            <motion.div whileHover={{ scale: 1.15 }} whileTap={{ scale: 0.88 }}>
              <Icon size={20} />
            </motion.div>
            <span style={{ fontSize: 10, fontWeight: active ? 600 : 400 }}>{item.label}</span>
          </Link>
        )
      })}
    </nav>
  )
}

// ── Page transition wrapper ───────────────────────────────────────────────────
function PageTransition({ children }) {
  const pathname = usePathname()
  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={pathname}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -6 }}
        transition={{ duration: 0.22, ease: 'easeOut' }}
        style={{ minHeight: '100%' }}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  )
}

// ── Root layout ───────────────────────────────────────────────────────────────
export default function Layout({ children }) {
  const [collapsed, setCollapsed] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(false)

  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 768)
    check()
    window.addEventListener('resize', check)
    return () => window.removeEventListener('resize', check)
  }, [])

  return (
    <ThemeProvider>
      {isMobile ? (
        <div style={{ minHeight: '100dvh', background: 'var(--bg-base)' }}>
          <MobileHeader onMenuOpen={() => setDrawerOpen(true)} />
          <MobileDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
          <main style={{ paddingTop: 56, paddingBottom: 76, minHeight: '100dvh' }}>
            <PageTransition>{children}</PageTransition>
          </main>
          <MobileBottomNav />
        </div>
      ) : (
        <div style={{ display: 'flex', minHeight: '100vh', background: 'var(--bg-base)' }}>
          <DesktopSidebar collapsed={collapsed} onCollapse={() => setCollapsed(c => !c)} />
          <main style={{ flex: 1, overflow: 'auto', minWidth: 0 }}>
            <PageTransition>{children}</PageTransition>
          </main>
        </div>
      )}
    </ThemeProvider>
  )
}
