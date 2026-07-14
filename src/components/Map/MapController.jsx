import { useEffect } from 'react';
import { useMap } from 'react-leaflet';

export default function MapController({ selectedCoords }) {
  const map = useMap();
  useEffect(() => {
    if (selectedCoords) {
      map.flyTo(selectedCoords, map.getZoom(), { animate: true, duration: 0.7 });
    }
  }, [selectedCoords, map]);
  return null;
}
