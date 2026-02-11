import { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Privacy Policy',
  description: 'Privacy policy for NexusTopic.',
};

export default function PrivacyPage() {
  const siteName = process.env.NEXT_PUBLIC_SITE_NAME || 'NexusTopic';

  return (
    <div className="max-w-3xl mx-auto px-4 py-12">
      <h1 className="text-4xl font-bold text-text-primary mb-6">Privacy Policy</h1>

      <div className="space-y-6 text-text-secondary leading-relaxed">
        <p>
          Your privacy is important to us. This privacy policy explains how {siteName} collects,
          uses, and protects your information when you visit our website.
        </p>

        <h2 className="text-2xl font-bold text-text-primary pt-4">Information We Collect</h2>
        <p>
          We may collect non-personal information such as browser type, operating system,
          and pages visited. This data helps us improve the user experience.
        </p>

        <h2 className="text-2xl font-bold text-text-primary pt-4">Cookies</h2>
        <p>
          We use cookies to enhance your experience. Third-party services, including
          Google AdSense, may use cookies to serve relevant advertisements based on
          your browsing history.
        </p>

        <h2 className="text-2xl font-bold text-text-primary pt-4">Google AdSense</h2>
        <p>
          We use Google AdSense to display advertisements. Google may use cookies and
          web beacons to serve ads based on your visits to this and other websites.
          You can opt out of personalized advertising by visiting{' '}
          <a href="https://www.google.com/settings/ads" className="text-accent-400 hover:text-accent-500 underline" target="_blank" rel="noopener noreferrer">
            Google Ads Settings
          </a>.
        </p>

        <h2 className="text-2xl font-bold text-text-primary pt-4">Changes to This Policy</h2>
        <p>
          We may update this privacy policy from time to time. Any changes will be posted
          on this page with an updated date.
        </p>

        <p className="text-text-tertiary text-sm pt-4">
          Last updated: {new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}
        </p>
      </div>
    </div>
  );
}
