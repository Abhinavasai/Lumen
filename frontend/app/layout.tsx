import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/sidebar";

const inter = Inter({
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700", "800"],
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: "Job Hunter",
  description: "AI-powered job hunting dashboard",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={`${inter.className} bg-background text-text-primary antialiased`}>
        <Sidebar />
        <main className="pl-64 min-h-screen overflow-y-auto">
          <div className="max-w-7xl mx-auto p-8">{children}</div>
        </main>
      </body>
    </html>
  );
}
