import { useEffect, useRef } from 'react';
import { useMap } from 'react-leaflet';
import { BLUEPRINT_CONFIG } from '../../constants/mapConfig';

export default function BlueprintInitializer() {
  const map = useMap();
  const done = useRef(false);

  useEffect(() => {
    if (done.current) return;
    done.current = true;

    const bounds = [[0, 0], [BLUEPRINT_CONFIG.height, BLUEPRINT_CONFIG.width]];
    
    const t = setTimeout(() => {
      // Max bounds intentionally omitted to prevent CRS.Simple zoom assertion crashes
      
      // Calculate minZoom to ensure the map always fills the container
      const containerSize = map.getSize();
      if (containerSize.x > 0 && containerSize.y > 0) {
        const zoomX = Math.log2(containerSize.x / BLUEPRINT_CONFIG.width);
        const zoomY = Math.log2(containerSize.y / BLUEPRINT_CONFIG.height);
        // The minimum zoom should be the larger of the two to ensure no black space
        const minZoom = Math.max(zoomX, zoomY);
        map.setMinZoom(minZoom);
      }
      
      map.fitBounds(bounds, { animate: false });
    }, 60);

    return () => clearTimeout(t);
  }, [map]);

  return null;
}
