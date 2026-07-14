import { useMapEvents } from 'react-leaflet';

export default function MatrixClickTracker({ isBlueprint, onCoord }) {
  useMapEvents({
    click: (e) => {
      if (isBlueprint) {
        onCoord({ x: Math.round(e.latlng.lng), y: Math.round(e.latlng.lat) });
      }
    },
  });
  return null;
}
