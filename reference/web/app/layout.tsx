import { devtoolsHookSource } from "@stack-inspect/react";
import Script from "next/script";
import type { ReactNode } from "react";

export const metadata = { title: "stack-inspect reference" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en-GB">
      <body>
        {/* biome-ignore lint/correctness/useUniqueElementIds: Next.js requires a stable Script id */}
        <Script id="stack-inspect-hook" strategy="beforeInteractive">
          {devtoolsHookSource}
        </Script>
        {children}
      </body>
    </html>
  );
}
