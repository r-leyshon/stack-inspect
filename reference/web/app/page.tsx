"use client";

import { install as installBrowser } from "@stack-inspect/browser";
import {
  install as installReact,
  observeQueryClient,
} from "@stack-inspect/react";
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import React, { useEffect, useState } from "react";

installBrowser();
installReact(React);

const queryClient = new QueryClient();

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
const fanoutRows = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l"];

export default function Page() {
  return (
    <QueryClientProvider client={queryClient}>
      <main>
        <h1>Reference app</h1>
        <Dashboard />
        <Duplicate />
        <Crash />
        <CustomHeader />
        <NPlusOne />
        <Sequential />
        <ExtraWork />
        <Rerender />
        <Fanout />
        <EffectRestart />
        <Stream />
        <Socket />
        <CachedResults />
      </main>
    </QueryClientProvider>
  );
}

function Dashboard() {
  return (
    <button type="button" onClick={() => fetch("/api/dashboard")}>
      Load dashboard
    </button>
  );
}

function Duplicate() {
  return (
    <button
      type="button"
      onClick={() => {
        void fetch("/api/dashboard");
        void fetch("/api/dashboard");
      }}
    >
      Duplicate fetch
    </button>
  );
}

function Crash() {
  return (
    <button
      type="button"
      onClick={() => {
        void fetch(`${apiUrl}/api/crash`).catch(() => undefined);
      }}
    >
      Crashing endpoint
    </button>
  );
}

function CustomHeader() {
  return (
    <button
      type="button"
      onClick={() => {
        void fetch(`${apiUrl}/api/items`, {
          headers: { "X-Custom-Header": "1" },
        }).catch(() => undefined);
      }}
    >
      Custom header
    </button>
  );
}

function NPlusOne() {
  return (
    <button type="button" onClick={() => fetch(`${apiUrl}/api/n-plus-one`)}>
      N plus one
    </button>
  );
}

function Sequential() {
  return (
    <button type="button" onClick={() => fetch(`${apiUrl}/api/sequential`)}>
      Sequential awaits
    </button>
  );
}

function ExtraWork() {
  const [visible, setVisible] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={async () => {
          await fetch("/api/dashboard");
          setVisible(true);
          await new Promise<void>((resolve) => {
            const visible = () => document.querySelector("[data-user-visible]");
            if (visible()) {
              resolve();
              return;
            }
            const observer = new MutationObserver(() => {
              if (visible()) {
                observer.disconnect();
                resolve();
              }
            });
            observer.observe(document.body, { childList: true, subtree: true });
          });
          await fetch(`${apiUrl}/api/dashboard`);
        }}
      >
        Extra work
      </button>
      {visible ? <p data-user-visible>Visible result</p> : null}
    </>
  );
}

function Rerender() {
  const [tick, setTick] = useState(0);
  return (
    <>
      <button type="button" onClick={() => setTick(tick + 1)}>
        Unchanged child
      </button>
      <QuietChild label="same" />
      <span>{tick}</span>
    </>
  );
}

function QuietChild({ label }: { label: string }) {
  return <span>{label}</span>;
}

function Fanout() {
  const [tick, setTick] = useState(0);
  return (
    <>
      <button type="button" onClick={() => setTick(tick + 1)}>
        Fan out
      </button>
      {fanoutRows.map((row) => (
        <FanChild key={row} label="row" />
      ))}
    </>
  );
}

function FanChild({ label }: { label: string }) {
  return <span>{label}</span>;
}

function EffectRestart() {
  const [value, setValue] = useState(0);
  // biome-ignore lint/correctness/useExhaustiveDependencies: value is the planted restart
  useEffect(() => {
    const handle = setInterval(() => undefined, 10_000);
    return () => clearInterval(handle);
  }, [value]);
  return (
    <button type="button" onClick={() => setValue(value + 1)}>
      Restart effect
    </button>
  );
}

function Stream() {
  return (
    <button
      type="button"
      onClick={() => {
        const source = new EventSource(`${apiUrl}/api/stream`);
        source.onerror = () => source.close();
      }}
    >
      Open stream
    </button>
  );
}

function Socket() {
  return (
    <button
      type="button"
      onClick={() => {
        const socket = new WebSocket(`${apiUrl.replace("http", "ws")}/api/ws`);
        socket.onopen = () => socket.send("hello");
      }}
    >
      Open socket
    </button>
  );
}

function CachedResults() {
  const client = useQueryClient();
  useEffect(() => {
    observeQueryClient(client, "ResultsPanel");
  }, [client]);
  const query = useQuery({
    queryKey: ["results"],
    queryFn: async () => {
      const response = await fetch(`${apiUrl}/api/dashboard`);
      return response.json() as Promise<{ count: number }>;
    },
    enabled: false,
  });
  return (
    <>
      <button type="button" onClick={() => query.refetch()}>
        Load cached results
      </button>
      <button
        type="button"
        onClick={() => {
          void client.invalidateQueries({ queryKey: ["results"] });
        }}
      >
        Invalidate results
      </button>
      <ResultsPanel count={query.data?.count} />
    </>
  );
}

function ResultsPanel({ count }: { count: number | undefined }) {
  return <p>Results {count ?? "none"}</p>;
}
