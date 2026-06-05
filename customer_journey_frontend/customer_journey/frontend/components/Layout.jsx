'use client'
import { useState, useEffect, createContext, useContext } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { motion, AnimatePresence } from 'framer-motion'
import {
  LayoutDashboard, Search, Store, Bot, ArrowLeftRight,
  ShoppingBag, Globe, Layers, Download, Sun, Moon,
  ChevronLeft, Menu, X, Activity, User, LogOut,
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

// ── Nav items — each carries an accent colour for its active icon chip ──────────
const NAV = [
  { label: 'Dashboard',     href: '/',          icon: LayoutDashboard, color: 'var(--accent)' },
  { label: 'Customer 360',  href: '/customer',  icon: Search,          color: 'var(--blue)'   },
  { divider: true, label: 'CHANNELS' },
  { label: 'Online',        href: '/online',    icon: Globe,           color: 'var(--teal)'   },
  { label: 'Offline (EBO)', href: '/offline',   icon: Store,           color: 'var(--sand)'   },
  { label: 'Both',          href: '/both',      icon: Layers,          color: 'var(--purple)' },
  { divider: true, label: 'ANALYTICS' },
  { label: 'Cohorts',       href: '/cohorts',   icon: Activity,        color: 'var(--green)'  },
  { label: 'Migration',     href: '/migration', icon: ArrowLeftRight,  color: 'var(--blue)'   },
  { label: 'Stores',        href: '/stores',    icon: ShoppingBag,     color: 'var(--sand)'   },
  { label: 'Export',        href: '/export',    icon: Download,        color: 'var(--teal)'   },
]

const BOTTOM_NAV = [
  { label: 'Home',     href: '/',         icon: LayoutDashboard, color: 'var(--accent)' },
  { label: 'Customer', href: '/customer', icon: Search,          color: 'var(--blue)'   },
  { label: 'Cohorts',  href: '/cohorts',  icon: Activity,        color: 'var(--green)'  },
  { label: 'Stores',   href: '/stores',   icon: ShoppingBag,     color: 'var(--sand)'   },
  { label: 'Online',   href: '/online',   icon: Globe,           color: 'var(--teal)'   },
]

// ── Sidebar palette (applied INLINE so it can never fail to load) ──────────────
// These were previously only in the `.app-sidebar` CSS class; if that external
// rule didn't apply (dev HMR / CSS ordering), every white-on-olive tab collapsed
// to invisible white-on-white. Defining them inline on each sidebar root makes the
// olive rail + white text bullet-proof — they cascade to the tab cards as usual.
const SIDEBAR_VARS = {
  '--sidebar-bg'      : 'linear-gradient(180deg, #36441C 0%, #2E3A14 55%, #263010 100%)',
  '--nav-card-bg'     : 'rgba(255,255,255,0.08)',
  '--nav-card-border' : 'rgba(255,255,255,0.14)',
  '--nav-card-hover'  : 'rgba(255,255,255,0.15)',
  '--nav-active-bg'   : '#6E8238',
  '--nav-active-border': 'rgba(255,255,255,0.30)',
  '--nav-icon-bg'     : 'rgba(255,255,255,0.16)',
  '--signout-bg'      : '#6E8238',
  '--signout-hover'   : '#7E9444',
  '--bg-card'         : 'rgba(255,255,255,0.10)',
  '--bg-subtle'       : 'rgba(255,255,255,0.08)',
  '--bg-hover'        : 'rgba(255,255,255,0.16)',
  '--border'          : 'rgba(255,255,255,0.14)',
  '--border-strong'   : 'rgba(255,255,255,0.26)',
  '--text-primary'    : '#FFFFFF',
  '--text-secondary'  : 'rgba(255,255,255,0.82)',
  '--text-muted'      : 'rgba(255,255,255,0.55)',
  '--accent'          : '#C7DE7E', '--accent-hover': '#D6E993',
  '--blue'            : '#6BB0F2',
  '--teal'            : '#45D2BF',
  '--purple'          : '#C49CEC',
  '--green'           : '#6BD27A',
  '--amber'           : '#ECC25A',
  '--red'             : '#F58A86',
  '--sand'            : '#EBCB7A', '--sand-dark': '#EBCB7A',
}
const SIDEBAR_VARS_DARK = {
  '--sidebar-bg'   : 'linear-gradient(180deg, #29330F 0%, #20290B 55%, #181F08 100%)',
  '--nav-card-bg'  : 'rgba(255,255,255,0.06)',
  '--nav-active-bg': '#5C6E2E',
  '--signout-bg'   : '#5C6E2E',
  '--signout-hover': '#6E8238',
}
const sidebarVars = (dark) => (dark ? { ...SIDEBAR_VARS, ...SIDEBAR_VARS_DARK } : SIDEBAR_VARS)

// ── Brand mark — Libas logo on a white chip so it reads on the dark-olive rail ──
function BrandMark({ size = 38 }) {
  return (
    <div style={{
      width: size, height: size, borderRadius: 11, flexShrink: 0,
      background: '#fff', overflow: 'hidden',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      boxShadow: '0 4px 12px rgba(0,0,0,0.28)', padding: Math.round(size * 0.16),
    }}>
      <img
        src="/purple_Libas-Logo_1_1.avif"
        alt="Libas"
        style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block', transform: 'scale(1.5)' }}
      />
    </div>
  )
}

// ── Nav card (desktop sidebar) ────────────────────────────────────────────────
function NavCard({ item, collapsed }) {
  const pathname = usePathname()
  const Icon = item.icon
  const active = pathname === item.href
  const c = item.color

  return (
    <Link
      href={item.href}
      title={collapsed ? item.label : undefined}
      style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: collapsed ? '7px' : '6px 10px',
        justifyContent: collapsed ? 'center' : 'flex-start',
        borderRadius: 10, marginBottom: 4, textDecoration: 'none',
        background: active ? 'var(--nav-active-bg)' : 'var(--nav-card-bg)',
        border: `1px solid ${active ? 'var(--nav-active-border)' : 'var(--nav-card-border)'}`,
        boxShadow: active ? '0 5px 14px rgba(0,0,0,0.30)' : '0 1px 2px rgba(0,0,0,0.12)',
        color: '#fff', fontWeight: active ? 700 : 600, fontSize: 13,
        position: 'relative', transition: 'background 0.16s, box-shadow 0.16s, border-color 0.16s',
      }}
      onMouseEnter={e => { if (!active) e.currentTarget.style.background = 'var(--nav-card-hover)' }}
      onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'var(--nav-card-bg)' }}
    >
      {active && (
        <motion.div
          layoutId="sidebarActiveIndicator"
          style={{
            position: 'absolute', left: -7, top: '22%', bottom: '22%',
            width: 4, borderRadius: '0 4px 4px 0', background: c,
            boxShadow: `0 0 10px ${c}`,
          }}
          transition={{ type: 'spring', stiffness: 400, damping: 30 }}
        />
      )}
      {/* Icon chip — accent-colour pop when active, frosted white at rest */}
      <span style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        width: 29, height: 29, borderRadius: 8, flexShrink: 0,
        background: active ? c : 'var(--nav-icon-bg)',
        color: active ? '#1E2A0C' : '#fff',
        boxShadow: active ? `0 2px 10px ${c}` : 'none',
        transition: 'background 0.16s, color 0.16s',
      }}>
        <Icon size={16} strokeWidth={2.2} />
      </span>
      {!collapsed && <span style={{ flex: 1, overflow: 'hidden', whiteSpace: 'nowrap' }}>{item.label}</span>}
    </Link>
  )
}

// ── Sidebar footer: user card + sign out + theme toggle ────────────────────────
function SidebarFooter({ collapsed }) {
  const { dark, toggle } = useTheme()
  if (collapsed) {
    return (
      <div style={{ padding: '12px 14px', borderTop: '1px solid var(--border)', display: 'flex', flexDirection: 'column', gap: 8, alignItems: 'center' }}>
        <button onClick={toggle} title={dark ? 'Light mode' : 'Dark mode'} style={iconBtn}>
          {dark ? <Sun size={16} /> : <Moon size={16} />}
        </button>
        <button title="Sign Out" style={{ ...iconBtn, background: 'var(--signout-bg)', borderColor: 'transparent' }}>
          <LogOut size={16} />
        </button>
      </div>
    )
  }
  return (
    <div style={{ padding: '10px 14px 12px', borderTop: '1px solid var(--border)' }}>
      {/* User card */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10, padding: '7px 10px',
        background: 'var(--nav-card-bg)', border: '1px solid var(--nav-card-border)',
        borderRadius: 11, marginBottom: 8,
      }}>
        <div style={{
          width: 32, height: 32, borderRadius: 9, flexShrink: 0,
          background: 'linear-gradient(135deg, #8FA646 0%, #C9A24E 100%)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          boxShadow: '0 2px 8px rgba(0,0,0,0.25)',
        }}>
          <User size={16} color="#fff" strokeWidth={2.2} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: '#fff', lineHeight: 1.2 }}>Welcome back</div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Authorised User</div>
        </div>
        <button onClick={toggle} title={dark ? 'Light mode' : 'Dark mode'}
          style={{ ...iconBtn, width: 30, height: 30 }}>
          <AnimatePresence mode="wait">
            <motion.div key={dark ? 'sun' : 'moon'}
              initial={{ rotate: -60, opacity: 0, scale: 0.7 }}
              animate={{ rotate: 0, opacity: 1, scale: 1 }}
              exit={{ rotate: 60, opacity: 0, scale: 0.7 }}
              transition={{ duration: 0.25 }} style={{ display: 'flex' }}>
              {dark ? <Sun size={15} /> : <Moon size={15} />}
            </motion.div>
          </AnimatePresence>
        </button>
      </div>
      {/* Sign Out — dark olive button, white text */}
      <button
        style={{
          width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
          padding: '9px 14px', borderRadius: 11, border: 'none', cursor: 'pointer',
          background: 'var(--signout-bg)', color: '#fff', fontSize: 13, fontWeight: 700,
          fontFamily: 'var(--font-body)', boxShadow: '0 3px 10px rgba(0,0,0,0.28)',
          transition: 'background 0.16s',
        }}
        onMouseEnter={e => { e.currentTarget.style.background = 'var(--signout-hover)' }}
        onMouseLeave={e => { e.currentTarget.style.background = 'var(--signout-bg)' }}
      >
        <LogOut size={16} /> Sign Out
      </button>
    </div>
  )
}

const iconBtn = {
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  width: 34, height: 34, borderRadius: 9, cursor: 'pointer', flexShrink: 0,
  background: 'var(--nav-card-bg)', border: '1px solid var(--nav-card-border)', color: '#fff',
}

const sectionLabel = {
  fontSize: 10, fontWeight: 700, letterSpacing: '0.14em',
  color: 'var(--text-muted)', textTransform: 'uppercase', whiteSpace: 'nowrap',
}

// ── Desktop Sidebar ───────────────────────────────────────────────────────────
function DesktopSidebar({ collapsed, onCollapse }) {
  const { dark } = useTheme()
  return (
    <motion.aside
      className="app-sidebar"
      animate={{ width: collapsed ? 76 : 268 }}
      transition={{ type: 'tween', duration: 0.22, ease: 'easeInOut' }}
      style={{
        ...sidebarVars(dark),
        background: 'var(--sidebar-bg)', borderRight: '1px solid var(--border)',
        display: 'flex', flexDirection: 'column', overflow: 'hidden',
        flexShrink: 0, position: 'sticky', top: 0, height: '100vh',
      }}
    >
      {/* Logo card */}
      <div style={{ padding: collapsed ? '12px 12px 4px' : '12px 14px 4px' }}>
        <div
          onClick={collapsed ? onCollapse : undefined}
          style={{
            display: 'flex', alignItems: 'center', gap: 10,
            justifyContent: collapsed ? 'center' : 'flex-start',
            padding: collapsed ? '8px' : '9px 12px',
            background: '#5C6E2E', border: '1px solid var(--nav-active-border)',
            borderRadius: 12, cursor: collapsed ? 'pointer' : 'default',
          }}
        >
          <BrandMark size={collapsed ? 34 : 36} />
          {!collapsed && (
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: 17, fontWeight: 800, letterSpacing: '-0.02em', color: '#fff', lineHeight: 1.1 }}>
                LibasCJ
              </div>
              <div style={{ fontSize: 9.5, color: 'var(--text-muted)', marginTop: 2, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 600 }}>
                Customer Journey
              </div>
            </div>
          )}
          {!collapsed && (
            <motion.button
              whileHover={{ scale: 1.12 }} whileTap={{ scale: 0.9 }}
              onClick={onCollapse}
              style={{ ...iconBtn, width: 26, height: 26, borderRadius: 8, background: '#FBFAF0', border: 'none', color: '#2E3A14' }}
            >
              <ChevronLeft size={15} strokeWidth={2.6} />
            </motion.button>
          )}
        </div>
      </div>

      {/* Nav */}
      <nav style={{ flex: 1, overflowY: 'auto', padding: collapsed ? '4px 12px' : '4px 14px' }}>
        {NAV.map((item, i) => {
          if (item.divider) return collapsed
            ? <div key={i} style={{ height: 1, background: 'var(--border)', margin: '7px 6px' }} />
            : <div key={i} style={{ padding: '9px 4px 3px', ...sectionLabel }}>{item.label}</div>
          return <NavCard key={item.href} item={item} collapsed={collapsed} />
        })}
      </nav>

      <SidebarFooter collapsed={collapsed} />
    </motion.aside>
  )
}

// ── Mobile top header ─────────────────────────────────────────────────────────
function MobileHeader({ onMenuOpen }) {
  const { dark, toggle } = useTheme()
  return (
    <header className="app-sidebar" style={{
      ...sidebarVars(dark),
      position: 'fixed', top: 0, left: 0, right: 0, height: 58,
      background: 'var(--sidebar-bg)', borderBottom: '1px solid var(--border)',
      display: 'flex', alignItems: 'center', padding: '0 14px', zIndex: 30, gap: 10,
    }}>
      <button onClick={onMenuOpen} style={iconBtn}><Menu size={18} /></button>
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 9 }}>
        <BrandMark size={30} />
        <div style={{ fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 800, letterSpacing: '-0.02em', color: '#fff' }}>
          LibasCJ
        </div>
      </div>
      <button onClick={toggle} style={iconBtn}>
        {dark ? <Sun size={16} /> : <Moon size={16} />}
      </button>
    </header>
  )
}

// ── Mobile drawer ─────────────────────────────────────────────────────────────
function MobileDrawer({ open, onClose }) {
  const { dark } = useTheme()
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
            style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 40, backdropFilter: 'blur(3px)' }}
          />
          <motion.aside
            key="drawer"
            className="app-sidebar"
            initial={{ x: -300 }} animate={{ x: 0 }} exit={{ x: -300 }}
            transition={{ type: 'spring', stiffness: 320, damping: 32 }}
            style={{
              ...sidebarVars(dark),
              position: 'fixed', top: 0, left: 0, height: '100dvh', width: 286,
              zIndex: 50, background: 'var(--sidebar-bg)', borderRight: '1px solid var(--border)',
              display: 'flex', flexDirection: 'column', overflowY: 'auto',
            }}
          >
            {/* Logo card */}
            <div style={{ padding: '16px 16px 8px' }}>
              <div style={{
                display: 'flex', alignItems: 'center', gap: 11, padding: '12px 14px',
                background: '#5C6E2E', border: '1px solid var(--nav-active-border)', borderRadius: 14,
              }}>
                <BrandMark size={36} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontFamily: 'var(--font-display)', fontSize: 17, fontWeight: 800, letterSpacing: '-0.02em', color: '#fff', lineHeight: 1.1 }}>LibasCJ</div>
                  <div style={{ fontSize: 9.5, color: 'var(--text-muted)', marginTop: 2, letterSpacing: '0.1em', textTransform: 'uppercase', fontWeight: 600 }}>Customer Journey</div>
                </div>
                <button onClick={onClose} style={{ ...iconBtn, width: 28, height: 28, color: 'var(--text-secondary)' }}><X size={15} /></button>
              </div>
            </div>

            {/* Nav */}
            <nav style={{ flex: 1, overflowY: 'auto', padding: '8px 16px' }}>
              <div style={{ padding: '8px 4px', ...sectionLabel }}>Navigation</div>
              {NAV.map((item, i) => {
                if (item.divider) return <div key={i} style={{ padding: '14px 4px 6px', ...sectionLabel }}>{item.label}</div>
                return <div key={item.href} onClick={onClose}><NavCard item={item} collapsed={false} /></div>
              })}
            </nav>

            <SidebarFooter collapsed={false} />
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}

// ── Mobile bottom nav ─────────────────────────────────────────────────────────
function MobileBottomNav() {
  const pathname = usePathname()
  const { dark } = useTheme()
  return (
    <nav className="app-sidebar" style={{
      ...sidebarVars(dark),
      position: 'fixed', bottom: 0, left: 0, right: 0,
      height: 64, background: 'var(--sidebar-bg)', borderTop: '1px solid var(--border)',
      display: 'flex', alignItems: 'center', justifyContent: 'space-around',
      zIndex: 30, paddingBottom: 'env(safe-area-inset-bottom)',
    }}>
      {BOTTOM_NAV.map(item => {
        const Icon = item.icon
        const active = pathname === item.href
        const c = item.color
        return (
          <Link key={item.href} href={item.href} style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            gap: 3, padding: '6px 0', textDecoration: 'none',
            color: active ? '#fff' : 'var(--text-secondary)',
            flex: 1, position: 'relative',
          }}>
            <motion.div
              whileHover={{ scale: 1.1 }} whileTap={{ scale: 0.88 }}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                width: 38, height: 32, borderRadius: 10,
                background: active ? c : 'transparent',
                color: active ? '#1E2A0C' : 'var(--text-secondary)',
                boxShadow: active ? `0 2px 10px ${c}` : 'none',
              }}
            >
              <Icon size={20} strokeWidth={2.2} />
            </motion.div>
            <span style={{ fontSize: 10, fontWeight: active ? 700 : 500 }}>{item.label}</span>
          </Link>
        )
      })}
    </nav>
  )
}

// ── Floating "Ask AI" launcher — on every page, navigates to the agent ─────────
function AiFab({ bottom = 28 }) {
  const pathname = usePathname()
  if (pathname === '/agent') return null   // hide on the agent page itself
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.6, y: 16 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 300, damping: 20, delay: 0.25 }}
      style={{ position: 'fixed', right: 24, bottom, zIndex: 35 }}
    >
      {/* Gentle continuous float */}
      <motion.div
        animate={{ y: [0, -8, 0] }}
        transition={{ repeat: Infinity, duration: 3, ease: 'easeInOut' }}
      >
        <Link href="/agent" aria-label="Ask the AI agent" title="Ask AI"
          style={{ textDecoration: 'none', display: 'block' }}>
          <motion.div
            whileHover={{ scale: 1.06 }} whileTap={{ scale: 0.95 }}
            style={{
              display: 'flex', alignItems: 'center', gap: 11,
              padding: '9px 20px 9px 9px', borderRadius: 999,
              background: 'linear-gradient(135deg, var(--accent) 0%, var(--accent-hover) 100%)',
              color: '#fff', fontWeight: 700, fontSize: 14.5, fontFamily: 'var(--font-body)',
              boxShadow: '0 12px 30px rgba(94,110,52,0.5)', cursor: 'pointer',
            }}
          >
            {/* Prominent robot icon with a pulsing halo */}
            <motion.span
              animate={{ boxShadow: ['0 0 0 0 rgba(255,255,255,0.55)', '0 0 0 13px rgba(255,255,255,0)'] }}
              transition={{ repeat: Infinity, duration: 2, ease: 'easeOut' }}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                width: 40, height: 40, borderRadius: '50%',
                background: 'rgba(255,255,255,0.20)', border: '1.5px solid rgba(255,255,255,0.55)',
              }}
            >
              <Bot size={24} strokeWidth={2.4} />
            </motion.span>
            <span>Ask AI</span>
          </motion.div>
        </Link>
      </motion.div>
    </motion.div>
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
          <main style={{ paddingTop: 58, paddingBottom: 80, minHeight: '100dvh' }}>
            <PageTransition>{children}</PageTransition>
          </main>
          <AiFab bottom={84} />
          <MobileBottomNav />
        </div>
      ) : (
        <div style={{ display: 'flex', minHeight: '100vh', background: 'var(--bg-base)' }}>
          <DesktopSidebar collapsed={collapsed} onCollapse={() => setCollapsed(c => !c)} />
          <main style={{ flex: 1, overflow: 'auto', minWidth: 0 }}>
            <PageTransition>{children}</PageTransition>
          </main>
          <AiFab bottom={28} />
        </div>
      )}
    </ThemeProvider>
  )
}
