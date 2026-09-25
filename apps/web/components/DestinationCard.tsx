import Link from 'next/link';

import { destinationImage } from '@/lib/utils';

export function DestinationCard({
  cluster,
  subtitle,
}: {
  subtitle?: string;
  cluster: {
    slug: string;
    name: string;
    state: string;
    recommended_days: number;
    hero_image_url: string | null;
  };
}) {
  return (
    <Link
      href={`/plan?destination=${cluster.slug}`}
      className="group relative block aspect-[4/3] overflow-hidden rounded-2xl shadow-card"
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={destinationImage(cluster.slug, 800, cluster.hero_image_url)}
        alt={cluster.name}
        loading="lazy"
        className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
      />
      <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/10 to-transparent" />
      <div className="absolute inset-x-0 bottom-0 p-5">
        <h3 className="font-display text-xl text-white">{cluster.name}</h3>
        <p className="text-sm text-white/80">
          {subtitle ?? `${cluster.state} · ${cluster.recommended_days} days`}
        </p>
      </div>
    </Link>
  );
}
