'use client';

/**
 * Leaflet maps, loaded client-side only.
 *
 * `react-leaflet` touches `window` at import time, so every map is behind a
 * dynamic import with `ssr: false`. Tiles come from OpenStreetMap with the
 * required attribution. If tiles fail to load (offline demo), the map still
 * renders markers over a plain background rather than breaking the page.
 */

import dynamic from 'next/dynamic';
import { useMemo } from 'react';

import { seededColour } from '@/lib/utils';

import { Skeleton } from './ui';

export interface MapPoint {
  lat: number;
  lon: number;
  label: string;
  sublabel?: string;
  colour?: string;
  sequence?: number;
  kind?: 'stop' | 'member' | 'meeting' | 'base';
}

const MapCanvas = dynamic(() => import('./MapCanvas'), {
  ssr: false,
  loading: () => <Skeleton className="h-full w-full" />,
});

export function MiniMap({
  points,
  height = 240,
  showRoute = false,
  className,
}: {
  points: MapPoint[];
  height?: number;
  showRoute?: boolean;
  className?: string;
}) {
  const decorated = useMemo(
    () =>
      points.map((p, i) => ({
        ...p,
        colour: p.colour ?? seededColour(p.label),
        sequence: p.sequence ?? (showRoute ? i + 1 : undefined),
      })),
    [points, showRoute]
  );

  if (!decorated.length) {
    return (
      <div
        style={{ height }}
        className="grid place-items-center rounded-2xl border border-[rgb(var(--line))] bg-[rgb(var(--surface-2))] text-sm text-ink-faint"
      >
        Nothing to show on the map yet.
      </div>
    );
  }

  return (
    <div
      style={{ height }}
      className={`overflow-hidden rounded-2xl border border-[rgb(var(--line))] ${className ?? ''}`}
    >
      <MapCanvas points={decorated} showRoute={showRoute} />
    </div>
  );
}
