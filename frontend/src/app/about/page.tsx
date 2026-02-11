import { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'About',
  description: 'Learn more about NexusTopic and our mission to deliver trending tech insights.',
};

export default function AboutPage() {
  const siteName = process.env.NEXT_PUBLIC_SITE_NAME || 'NexusTopic';

  return (
    <div className="max-w-3xl mx-auto px-4 py-12">
      <h1 className="text-4xl font-bold text-text-primary mb-6">About {siteName}</h1>

      <div className="space-y-6 text-text-secondary leading-relaxed">
        <p>
          {siteName} is an AI-powered platform that discovers and analyzes trending topics
          from across the web. We aggregate signals from sources like Hacker News, Reddit,
          and Google Trends to identify what&apos;s capturing attention in the tech world.
        </p>

        <p>
          Our mission is simple: cut through the noise and deliver the insights that matter.
          Each article dives deep into <em>why</em> a topic is trending, providing context
          and analysis you won&apos;t find in a simple news headline.
        </p>

        <h2 className="text-2xl font-bold text-text-primary pt-4">How It Works</h2>
        <ul className="list-disc list-inside space-y-2 text-text-secondary">
          <li>We monitor trending signals across multiple platforms in real-time</li>
          <li>AI analyzes why each topic is gaining traction</li>
          <li>In-depth articles are generated with comprehensive coverage</li>
          <li>Content is continuously updated as stories develop</li>
        </ul>

        <h2 className="text-2xl font-bold text-text-primary pt-4">Contact</h2>
        <p>
          Have feedback or suggestions? We&apos;d love to hear from you.
          Reach out via our social channels linked in the footer.
        </p>
      </div>
    </div>
  );
}
