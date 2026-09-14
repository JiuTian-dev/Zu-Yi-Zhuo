interface MapSwitchButtonProps {
  label: string
  onClick(): void
}

/** Folio-style top-right map trigger used to switch home ↔ match. */
export default function MapSwitchButton({ label, onClick }: MapSwitchButtonProps) {
  return (
    <button className="map-switch" type="button" aria-label={label} title={label} onClick={onClick}>
      <span className="map-switch-inner">
        <span className="map-switch-icon">
          <img className="map-switch-img" src="/ui/map.svg" alt="" width={22} height={16} />
        </span>
      </span>
    </button>
  )
}
