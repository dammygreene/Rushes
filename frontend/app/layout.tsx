import type { Metadata, Viewport } from "next";
import { Bodoni_Moda, IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import { Footer } from "@/components/Footer";
import { Masthead } from "@/components/Masthead";
import "./globals.css";

/**
 * Bodoni is the poster and title-card idiom of cinema, and its optical-size
 * axis is why the headline can be hairline-fine while the italic placeholder
 * at 16px stays sturdy. Plex carries the interface, and Plex Mono carries the
 * only monospace on the page: the source stamps, which are meant to read like
 * labels stencilled on a film can.
 */
const bodoni = Bodoni_Moda({
  subsets: ["latin"],
  style: ["normal", "italic"],
  axes: ["opsz"],
  variable: "--font-bodoni",
  display: "swap",
});

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  variable: "--font-plex-sans",
  display: "swap",
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Rushes: describe the shot, get the clip",
    template: "%s · Rushes",
  },
  description:
    "Describe a shot in plain English. Rushes searches your own archive with vector similarity in ClickHouse and the public web in parallel, then explains why each clip matched.",
};

/**
 * The page is dark-locked, so the browser chrome is told to match rather than
 * frame it in white, and the stock is allowed to run under the notch and the
 * home indicator. `globals.css` pads the body back off both insets.
 */
export const viewport: Viewport = {
  themeColor: "#16130f",
  colorScheme: "dark",
  viewportFit: "cover",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${bodoni.variable} ${plexSans.variable} ${plexMono.variable}`}
    >
      <body className="min-h-dvh antialiased">
        {/* Three tabs and a status lamp stand between the top of the document
            and the field, which is the one thing a keyboard user came for. */}
        <a
          href="#main"
          className="sr-only focus-visible:not-sr-only focus-visible:absolute focus-visible:top-3 focus-visible:left-3 focus-visible:z-10 focus-visible:bg-tungsten focus-visible:px-3 focus-visible:py-2 focus-visible:text-[13px] focus-visible:font-medium focus-visible:text-ink"
        >
          Skip to search
        </a>
        <div className="mx-auto flex min-h-dvh max-w-[92rem] flex-col px-5 pb-10 sm:px-8 sm:pb-16">
          <Masthead />
          <main id="main" className="flex-1">
            {children}
          </main>
          <Footer />
        </div>
      </body>
    </html>
  );
}
