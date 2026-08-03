import type { Metadata, Viewport } from 'next';

import { Providers } from './providers';
import './globals.css';

export const metadata: Metadata = {
  title: {
    default: 'YatraAI — context-aware group travel intelligence',
    template: '%s · YatraAI',
  },
  description:
    'Fair, explainable and feasible group itineraries for ten curated Indian destinations. ' +
    'Structured data decides the facts, OR-Tools schedules the days, and every plan passes a ' +
    'constraint validator before you see it.',
  applicationName: 'YatraAI',
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: '#faf7f2' },
    { media: '(prefers-color-scheme: dark)', color: '#12131a' },
  ],
  width: 'device-width',
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Applied before paint so the theme never flashes. */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var s=localStorage.getItem('yatraai.theme');var d=s?s==='dark':window.matchMedia('(prefers-color-scheme: dark)').matches;if(d)document.documentElement.classList.add('dark');}catch(e){}})();`,
          }}
        />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
