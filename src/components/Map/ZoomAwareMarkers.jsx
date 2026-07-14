import { useState } from 'react';
import { Marker, Tooltip, useMapEvents } from 'react-leaflet';
import { createMarkerIcon } from '../../utils/leafletHelpers';
import { MAP_ZOOM } from '../../constants/mapConfig';

export default function ZoomAwareMarkers({ cameras, activeCamera, onSelect, isBlueprint }) {
  const [zoom, setZoom] = useState(isBlueprint ? 0 : MAP_ZOOM);

  useMapEvents({ zoomend: (e) => setZoom(e.target.getZoom()) });

  const getSize = (z) => {
    if (isBlueprint) {
      if (z >= 2) return 22;
      if (z >= 0) return 18;
      return 14;
    }
    if (z >= 19) return 26;
    if (z >= 17) return 22;
    return 18;
  };

  return cameras.map((cam) => (
    <Marker
      key={cam.id}
      position={isBlueprint ? cam.blueprint_coords : cam.coords}
      icon={createMarkerIcon(activeCamera?.id === cam.id, getSize(zoom), cam.accessible !== false)}
      eventHandlers={{ click: () => onSelect(cam.id), mousedown: () => onSelect(cam.id), touchstart: () => onSelect(cam.id) }}
    >
      <Tooltip
        direction="top"
        offset={[0, -10]}
        opacity={1.0}
        className="custom-hover-tooltip"
      >
        <div className="tooltip-card">
          <strong className="tooltip-title">{cam.name}</strong>
          <div className="tooltip-details">
            <div className="tooltip-row">
              <span className="tooltip-label">ID:</span>
              <span className="tooltip-val">{cam.id}</span>
            </div>
            <div className="tooltip-row">
              <span className="tooltip-label">Brand:</span>
              <span className="tooltip-val">{cam.brand}</span>
            </div>
            <div className="tooltip-row">
              <span className="tooltip-label">Status:</span>
              <span className={`tooltip-val status-${cam.accessible !== false ? 'online' : 'offline'}`}>
                {cam.status || (cam.accessible !== false ? 'ONLINE / ACCESSIBLE' : 'OFFLINE')}
              </span>
            </div>
          </div>
        </div>
      </Tooltip>
    </Marker>
  ));
}
