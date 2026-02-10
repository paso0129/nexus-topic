'use client';

import { useEffect } from 'react';

interface AdSenseProps {
  slot?: string;
  format?: 'auto' | 'fluid' | 'rectangle' | 'vertical' | 'horizontal';
  responsive?: boolean;
  style?: React.CSSProperties;
}

export default function AdSense({
  slot = 'header',
  format = 'auto',
  responsive = true,
  style = {},
}: AdSenseProps) {
  const clientId = process.env.NEXT_PUBLIC_ADSENSE_CLIENT_ID;

  useEffect(() => {
    if (typeof window !== 'undefined' && clientId) {
      try {
        ((window as any).adsbygoogle = (window as any).adsbygoogle || []).push({});
      } catch (err) {
        console.error('AdSense error:', err);
      }
    }
  }, [clientId]);

  // Don't render if no client ID
  if (!clientId) {
    return (
      <div className="text-center p-4 bg-gray-100 dark:bg-gray-800 rounded">
        <p className="text-sm text-gray-500">
          AdSense not configured. Set NEXT_PUBLIC_ADSENSE_CLIENT_ID in .env.local
        </p>
      </div>
    );
  }

  // Get slot ID from config (you might want to load this from env or config)
  const slotId = getSlotId(slot);

  return (
    <div className="adsense-container my-8 text-center" style={style}>
      <ins
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

// Helper function to get slot ID based on position
function getSlotId(position: string): string {
  // These should match your AdSense ad unit slot IDs
  // You can load these from environment variables or a config file
  const slots: Record<string, string> = {
    header: process.env.NEXT_PUBLIC_ADSENSE_SLOT_HEADER || '1234567890',
    'in-article': process.env.NEXT_PUBLIC_ADSENSE_SLOT_IN_ARTICLE || '0987654321',
    footer: process.env.NEXT_PUBLIC_ADSENSE_SLOT_FOOTER || '1122334455',
    sidebar: process.env.NEXT_PUBLIC_ADSENSE_SLOT_SIDEBAR || '5544332211',
  };

  return slots[position] || slots.header;
}
