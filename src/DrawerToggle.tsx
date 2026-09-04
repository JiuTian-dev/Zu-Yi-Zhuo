interface DrawerToggleProps {
  collapsed: boolean
  label: string
  controlsId: string
  onToggle(): void
}

/** PRODUCT DOM — shared low-noise affordance for collapsible scene cards. */
export default function DrawerToggle({ collapsed, label, controlsId, onToggle }: DrawerToggleProps) {
  return (
    <button
      className="drawer-toggle"
      type="button"
      aria-expanded={!collapsed}
      aria-controls={controlsId}
      aria-label={collapsed ? `打开${label}` : `收起${label}`}
      onClick={onToggle}
    >
      <span className="drawer-toggle-mark" aria-hidden="true">{collapsed ? '+' : '−'}</span>
      <span>{collapsed ? `打开${label}` : '收起'}</span>
    </button>
  )
}
