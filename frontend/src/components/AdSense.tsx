'use client';

import { useEffect, useRef } from 'react';

interface AdSenseProps {
  slot?: string;
  format?: 'auto' | 'fluid' | 'rectangle' | 'vertical' | 'horizontal';
  responsive?: boolean;
  variant?: 'banner' | 'sidebar' | 'in-feed';
  style?: React.CSSProperties;
}

export default function AdSense({
  slot = 'header',
  format = 'auto',
  responsive = true,
  variant = 'banner',
  style = {},
}: AdSenseProps) {
  const clientId = process.env.NEXT_PUBLIC_ADSENSE_CLIENT_ID;
  const adRef = useRef<HTMLModElement>(null);
  const pushed = useRef(false);

  useEffect(() => {
    if (typeof window !== 'undefined' && clientId && !pushed.current) {
      try {
        const adEl = adRef.current;
        if (adEl && !adEl.getAttribute('data-adsbygoogle-status')) {
          ((window as any).adsbygoogle = (window as any).adsbygoogle || []).push({});
          pushed.current = true;
        }
      } catch (err) {
        // Silently ignore duplicate push errors
      }
    }
  }, [clientId]);

  const slotId = getSlotId(slot);

  if (!clientId) {
    const variantStyles: Record<string, string> = {
      banner: 'h-24 my-6',
      sidebar: 'h-64 mb-6',
      'in-feed': 'h-32 my-4',
    };

    return (
      <div className={`bg-dark-surface border border-dark-border rounded-lg flex items-center justify-center ${variantStyles[variant]}`}>
        <div className="text-center">
          <p className="text-text-tertiary text-xs uppercase tracking-wider font-medium">
            Advertisement
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="adsense-container text-center" style={style}>
      <ins
        ref={adRef}
        className="adsbygoogle"
        style={{ display: 'block', textAlign: 'center' }}
        data-ad-client={clientId}
        data-ad-slot={slotId}
        data-ad-format={format}
        data-full-width-responsive={responsive ? 'true' : 'false'}
      />
    </div>
  );
}

function getSlotId(position: string): string {
  const slots: Record<string, string> = {
    header: process.env.NEXT_PUBLIC_ADSENSE_SLOT_HEADER || '1234567890',
    'in-article': process.env.NEXT_PUBLIC_ADSENSE_SLOT_IN_ARTICLE || '0987654321',
    footer: process.env.NEXT_PUBLIC_ADSENSE_SLOT_FOOTER || '1122334455',
    sidebar: process.env.NEXT_PUBLIC_ADSENSE_SLOT_SIDEBAR || '5544332211',
  };

  return slots[position] || slots.header;
}
