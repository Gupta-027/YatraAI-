'use client';

import 'leaflet/dist/leaflet.css';

import L from 'leaflet';
import { useEffect } from 'react';
import { MapContainer, Marker, Polyline, Popup, TileLayer, useMap } from 'react-leaflet';

import type { MapPoint } from './Map';

/** Inline SVG pin — avoids Leaflet's default icon, which 404s under bundlers. */
function pinIcon(colour: string, label?: string) {
  const text = label
    ? `<text x="12" y="16" text-anchor="middle" font-size="11" font-weight="700" fill="#fff" font-family="system-ui">${label}</text>`
    : `<circle cx="12" cy="12" r="4" fill="#fff"/>`;
  return L.divIcon({
    className: 'yatra-pin',
    html: `<svg width="30" height="42" viewBox="0 0 24 34" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 0C5.4 0 0 5.4 0 12c0 9 12 22 12 22s12-13 12-22c0-6.6-5.4-12-12-12z" fill="${colour}"/>
      ${text}
    </svg>`,
    iconSize: [30, 42],
    iconAnchor: [15, 42],
    popupAnchor: [0, -38],
  });
}

function FitBounds({ points }: { points: MapPoint[] }) {
  const map = useMap();
  useEffect(() => {
    if (!points.length) return;
    if (points.length === 1) {
      map.setView([points[0].lat, points[0].lon], 14);
      return;
    }
    const bounds = L.latLngBounds(points.map((p) => [p.lat, p.lon] as [number, number]));
    map.fitBounds(bounds, { padding: [36, 36], maxZoom: 15 });
  }, [map, points]);
  return null;
}

export default function MapCanvas({
  points,
  showRoute,
}: {
  points: MapPoint[];
  showRoute?: boolean;
}) {
  const centre: [number, number] = [points[0]?.lat ?? 20.59, points[0]?.lon ?? 78.96];

  return (
    <MapContainer
      center={centre}
      zoom={12}
      scrollWheelZoom={false}
      style={{ height: '100%', width: '100%' }}
      attributionControl
    >
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        maxZoom={19}
      />
      <FitBounds points={points} />

      {showRoute && points.length > 1 && (
        <Polyline
          positions={points.map((p) => [p.lat, p.lon] as [number, number])}
          pathOptions={{ color: '#23306b', weight: 3, opacity: 0.55, dashArray: '6 8' }}
        />
      )}

      {points.map((point, index) => (
        <Marker
          key={`${point.label}-${index}`}
          position={[point.lat, point.lon]}
          icon={pinIcon(point.colour ?? '#23306b', point.sequence ? String(point.sequence) : undefined)}
        >
          <Popup>
            <strong>{point.label}</strong>
            {point.sublabel && (
              <>
                <br />
                <span style={{ color: '#5b6178' }}>{point.sublabel}</span>
              </>
            )}
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}
