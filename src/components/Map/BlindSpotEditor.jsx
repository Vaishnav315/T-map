import React, { useState, useEffect } from 'react';
import { useMapEvents, Rectangle, useMap } from 'react-leaflet';
import L from 'leaflet';

export default function BlindSpotEditor({ isBlueprint, isDrawingMode, blindSpots, setBlindSpots }) {
  const [currentRect, setCurrentRect] = useState(null);
  const [draggingIdx, setDraggingIdx] = useState(null);
  const [dragStart, setDragStart] = useState(null);
  const map = useMap();

  useEffect(() => {
    if (isDrawingMode) {
      map.dragging.disable();
    } else {
      map.dragging.enable();
    }
  }, [isDrawingMode, map]);

  useMapEvents({
    mousedown: (e) => {
      if (!isBlueprint || !isDrawingMode) return;
      if (draggingIdx === null) {
        setCurrentRect([e.latlng, e.latlng]);
      }
    },
    mousemove: (e) => {
      if (!isBlueprint || !isDrawingMode) return;
      
      if (draggingIdx !== null && dragStart) {
        const deltaLat = e.latlng.lat - dragStart.lat;
        const deltaLng = e.latlng.lng - dragStart.lng;
        
        setBlindSpots(prev => {
          const next = [...prev];
          const oldBounds = next[draggingIdx];
          
          const p1 = oldBounds[0];
          const p2 = oldBounds[1];
          
          const lat1 = typeof p1.lat === 'number' ? p1.lat : p1[0];
          const lng1 = typeof p1.lng === 'number' ? p1.lng : p1[1];
          const lat2 = typeof p2.lat === 'number' ? p2.lat : p2[0];
          const lng2 = typeof p2.lng === 'number' ? p2.lng : p2[1];
          
          next[draggingIdx] = [
            { lat: lat1 + deltaLat, lng: lng1 + deltaLng },
            { lat: lat2 + deltaLat, lng: lng2 + deltaLng }
          ];
          return next;
        });
        
        setDragStart(e.latlng);
      } else if (currentRect) {
        setCurrentRect([currentRect[0], e.latlng]);
      }
    },
    mouseup: (e) => {
      if (!isBlueprint || !isDrawingMode) return;
      
      if (draggingIdx !== null) {
        setDraggingIdx(null);
        setDragStart(null);
      } else if (currentRect) {
        if (currentRect[0].lat !== e.latlng.lat || currentRect[0].lng !== e.latlng.lng) {
          const newSpot = [currentRect[0], e.latlng];
          setBlindSpots([...blindSpots, newSpot]);
        }
        setCurrentRect(null);
      }
    }
  });

  return (
    <>
      {Array.isArray(blindSpots) && blindSpots.map((bounds, idx) => {
        if (!bounds || !Array.isArray(bounds) || bounds.length < 2) return null;
        
        const p1 = bounds[0];
        const p2 = bounds[1];
        if (!p1 || !p2) return null;
        
        const lat1 = p1.lat !== undefined ? p1.lat : p1[0];
        const lng1 = p1.lng !== undefined ? p1.lng : p1[1];
        const lat2 = p2.lat !== undefined ? p2.lat : p2[0];
        const lng2 = p2.lng !== undefined ? p2.lng : p2[1];
        
        if (lat1 === undefined || lng1 === undefined || lat2 === undefined || lng2 === undefined) return null;

        const normalizedBounds = [
          [lat1, lng1],
          [lat2, lng2]
        ];
        
        return (
          <Rectangle 
            key={`bs-${idx}`} 
            bounds={normalizedBounds} 
            pathOptions={{ color: '#ff3333', fillColor: '#ff3333', fillOpacity: 0.4, weight: 2, dashArray: '5, 5' }}
            eventHandlers={{
              mousedown: (e) => {
                if (isDrawingMode) {
                  L.DomEvent.stopPropagation(e);
                  setDraggingIdx(idx);
                  setDragStart(e.latlng);
                }
              }
            }}
          />
        );
      })}
      {currentRect && (
        <Rectangle 
          bounds={currentRect} 
          pathOptions={{ color: '#ff3333', fillColor: '#ff3333', fillOpacity: 0.4, weight: 2, dashArray: '5, 5' }} 
        />
      )}
    </>
  );
}
