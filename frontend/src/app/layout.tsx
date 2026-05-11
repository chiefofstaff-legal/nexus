import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ChiefOfStaff.pro",
  description: "AI-powered legal document management, entity analysis, and workflow automation",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased" suppressHydrationWarning>
      <body className="min-h-full">{children}</body>
    </html>
  );
}
