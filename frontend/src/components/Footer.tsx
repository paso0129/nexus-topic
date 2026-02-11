import Link from 'next/link';

export default function Footer() {
  const currentYear = new Date().getFullYear();
  const siteName = process.env.NEXT_PUBLIC_SITE_NAME || 'NexusTopic';

  return (
    <footer className="bg-dark-surface border-t border-dark-border mt-12">
      <div className="container mx-auto px-4 py-10">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {/* About */}
          <div>
            <h3 className="text-sm font-bold uppercase tracking-widest text-accent-400 mb-4">
              About
            </h3>
            <p className="text-text-secondary text-sm leading-relaxed">
              {process.env.NEXT_PUBLIC_SITE_DESCRIPTION ||
                'Discover trending topics and insights powered by AI. We analyze what\'s buzzing across the web and deliver in-depth coverage.'}
            </p>
          </div>

          {/* Links */}
          <div>
            <h3 className="text-sm font-bold uppercase tracking-widest text-accent-400 mb-4">
              Quick Links
            </h3>
            <ul className="space-y-2">
              <li>
                <Link href="/" className="text-text-secondary hover:text-accent-400 text-sm transition-colors">
                  Home
                </Link>
              </li>
              <li>
                <Link href="/about" className="text-text-secondary hover:text-accent-400 text-sm transition-colors">
                  About
                </Link>
              </li>
              <li>
                <Link href="/privacy" className="text-text-secondary hover:text-accent-400 text-sm transition-colors">
                  Privacy Policy
                </Link>
              </li>
            </ul>
          </div>

          {/* Connect */}
          <div>
            <h3 className="text-sm font-bold uppercase tracking-widest text-accent-400 mb-4">
              Connect
            </h3>
            <div className="flex space-x-4">
              <a
                href="https://twitter.com"
                target="_blank"
                rel="noopener noreferrer"
                className="text-text-secondary hover:text-accent-400 transition-colors"
                aria-label="Twitter"
              >
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M8.29 20.251c7.547 0 11.675-6.253 11.675-11.675 0-.178 0-.355-.012-.53A8.348 8.348 0 0022 5.92a8.19 8.19 0 01-2.357.646 4.118 4.118 0 001.804-2.27 8.224 8.224 0 01-2.605.996 4.107 4.107 0 00-6.993 3.743 11.65 11.65 0 01-8.457-4.287 4.106 4.106 0 001.27 5.477A4.072 4.072 0 012.8 9.713v.052a4.105 4.105 0 003.292 4.022 4.095 4.095 0 01-1.853.07 4.108 4.108 0 003.834 2.85A8.233 8.233 0 012 18.407a11.616 11.616 0 006.29 1.84" />
                </svg>
              </a>
            </div>
          </div>
        </div>

        <div className="mt-10 pt-8 border-t border-dark-border text-center">
          <p className="text-text-tertiary text-sm">
            &copy; {currentYear} {siteName}. All rights reserved.
          </p>
          <p className="text-text-tertiary text-xs mt-2">
            Powered by AI &middot; Trending insights delivered daily
          </p>
        </div>
      </div>
    </footer>
  );
}
