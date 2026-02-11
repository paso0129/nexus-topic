'use client';

import Link from 'next/link';
import { useState } from 'react';
import ThemeToggle from './ThemeToggle';
import MobileMenu from './MobileMenu';

const navLinks = [
  { href: '/', label: 'Home' },
  { href: '/about', label: 'About' },
];

export default function Header() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const siteName = process.env.NEXT_PUBLIC_SITE_NAME || 'NexusTopic';

  return (
    <>
      {/* Accent top line */}
      <div className="h-0.5 bg-gradient-to-r from-accent-600 via-accent-400 to-accent-600" />

      <header className="sticky top-0 z-50 bg-dark-base/95 backdrop-blur-md border-b border-dark-border">
        <div className="container mx-auto px-4">
          <div className="flex items-center justify-between h-16">
            {/* Logo */}
            <Link href="/" className="flex items-center space-x-2 group">
              <span className="text-2xl font-black tracking-tight text-text-primary group-hover:text-accent-400 transition-colors">
                {siteName}
              </span>
            </Link>

            {/* Desktop Nav */}
            <nav className="hidden md:flex items-center space-x-8">
              {navLinks.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  className="text-text-secondary hover:text-accent-400 transition-colors text-sm font-medium uppercase tracking-wide"
                >
                  {link.label}
                </Link>
              ))}
              <ThemeToggle />
            </nav>

            {/* Mobile menu button */}
            <div className="flex items-center gap-2 md:hidden">
              <ThemeToggle />
              <button
                onClick={() => setMobileMenuOpen(true)}
                className="p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-dark-elevated transition-colors"
                aria-label="Open menu"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </header>

      <MobileMenu
        isOpen={mobileMenuOpen}
        onClose={() => setMobileMenuOpen(false)}
        links={navLinks}
      />
    </>
  );
}
