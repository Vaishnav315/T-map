import L from 'leaflet';

export const createMarkerIcon = (isSelected, size = 16, isAccessible = true) => {
  const color = isAccessible ? '#00ffcc' : '#ff3366';
  const borderWeight = isSelected ? '3px' : '2px';
  const shadowSpread = isSelected ? '12px' : '6px';
  const glow = `0 0 ${shadowSpread} ${color}, inset 0 0 4px ${color}`;

  return L.divIcon({
    className: 'custom-tactical-dot-marker',
    html: `
      <div style="
        width: ${size}px;
        height: ${size}px;
        background: rgba(8, 14, 24, 0.85);
        border: ${borderWeight} solid ${color};
        border-radius: 50%;
        box-shadow: ${glow};
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.2s ease-in-out;
        cursor: pointer;
      ">
        <div style="
          width: ${Math.max(4, Math.round(size * 0.35))}px;
          height: ${Math.max(4, Math.round(size * 0.35))}px;
          background: ${color};
          border-radius: 50%;
          box-shadow: 0 0 6px ${color};
        "></div>
      </div>
    `,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
};
