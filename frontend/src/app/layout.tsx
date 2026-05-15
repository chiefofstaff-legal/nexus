import type { Metadata } from "next";
import { Analytics } from "@vercel/analytics/next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ChiefOfStaff.pro",
  description: "AI-powered legal document management, entity analysis, and workflow automation",
  icons: {
    icon: "/favicon.ico",
    apple: "/apple-touch-icon.png",
  },
  openGraph: {
    title: "ChiefOfStaff.pro",
    description: "Decision-Oriented Network Notarisation for Attorneys",
    url: "https://free.donnaoss.com",
    siteName: "ChiefOfStaff.pro",
    images: [
      {
        url: "/og.png",
        width: 1200,
        height: 630,
        alt: "ChiefOfStaff.pro — Decision-Oriented Network Notarisation for Attorneys",
      },
    ],
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "ChiefOfStaff.pro",
    description: "Decision-Oriented Network Notarisation for Attorneys",
    images: ["/og.png"],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased" suppressHydrationWarning>
      <body className="min-h-full">
        {children}
        <Analytics />
      </body>
    </html>
  );
}
