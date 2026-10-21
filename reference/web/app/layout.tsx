import { devtoolsHookSource } from "@stack-inspect/react";
import type { ReactNode } from "react";

export const metadata = { title: "stack-inspect reference" };

/**
 * Also install via ``instrumentation-client.ts``. A sync inline script is kept
 * as a belt-and-braces early install; Next may still reorder it after chunks.
 */
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en-GB">
      <head>
        <script
          // biome-ignore lint/security/noDangerouslySetInnerHtml: fixed adapter source, not user input
          dangerouslySetInnerHTML={{ __html: devtoolsHookSource }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
