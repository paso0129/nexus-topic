import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Header from "@/components/Header";
import Footer from "@/components/Footer";
import Script from "next/script";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: {
    default: "AdSense Blog - AI-Powered Content",
    template: "%s | AdSense Blog"
  },
  description: "High-quality AI-generated content with strategic AdSense monetization",
  keywords: ["blog", "adsense", "ai content", "technology", "news"],
  authors: [{ name: "AdSense Blog" }],
  creator: "AdSense Blog Automation",
  openGraph: {
    type: "website",
    locale: "en_US",
    url: process.env.NEXT_PUBLIC_SITE_URL || "https://yourdomain.com",
    siteName: process.env.NEXT_PUBLIC_SITE_NAME || "AdSense Blog",
    title: "AdSense Blog - AI-Powered Content",
    description: "High-quality AI-generated content with strategic AdSense monetization",
  },
  twitter: {
    card: "summary_large_image",
    title: "AdSense Blog - AI-Powered Content",
    description: "High-quality AI-generated content with strategic AdSense monetization",
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      'max-video-preview': -1,
      'max-image-preview': 'large',
      'max-snippet': -1,
    },
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const adsenseId = process.env.NEXT_PUBLIC_ADSENSE_CLIENT_ID;

  return (
    <html lang="en">
      <head>
        {adsenseId && (
          <>
            <Script
              async
              src={`https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${adsenseId}`}
              crossOrigin="anonymous"
              strategy="afterInteractive"
            />
          </>
        )}
      </head>
      <body className={inter.className}>
        <div className="min-h-screen flex flex-col">
          <Header />
          <main className="flex-grow container mx-auto px-4 py-8">
            {children}
          </main>
          <Footer />
        </div>
      </body>
    </html>
  );
}
