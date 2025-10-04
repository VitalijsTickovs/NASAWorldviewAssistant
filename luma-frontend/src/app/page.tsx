"use client";

import { useEffect, useMemo, useState } from 'react';
import { useAgentSSE, type AgentEvent } from '@/hooks/useAgentSSE';

export default function Page() {
  const [q, setQ] = useState("");
  const [submitted, setSubmitted] = useState<string | null>(null);
  const [threadId, setThreadId] = useState<string>("");

  useEffect(() => {
    const saved = localStorage.getItem("thread_id") || crypto.randomUUID();
    localStorage.setItem("thread_id", saved);
    setThreadId(saved);
  }, []);

  const { data, done, cancel } = useAgentSSE(submitted ?? "", threadId);

  const [cachedMessages, setCachedMessages] = useState<AgentEvent["messages"]>([]);
  useEffect(() => {
    if (!threadId) return;
    const cached = localStorage.getItem(`history:${threadId}`);
    setCachedMessages(cached ? JSON.parse(cached) : []);
  }, [threadId]);

  useEffect(() => {
    if (done && data?.messages && threadId) {
      localStorage.setItem(`history:${threadId}`, JSON.stringify(data.messages));
      setCachedMessages(data.messages);
    }
  }, [done, data, threadId]);
  
  const messages = useMemo(() => {
    if (data?.messages?.length) return data.messages;
    return cachedMessages;
  }, [data, cachedMessages]);

  return (
    <main className="p-6 max-w-2xl mx-auto">
      <h1 className="text-xl font-semibold">NASA Worldview Assistant</h1>

      <div className="mt-4 flex gap-2">
        <input
          className="border px-3 py-2 flex-1"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Ask something…"
        />
        <button
          className="px-3 py-2 border"
          onClick={() => setSubmitted(q)}
          disabled={!q}
        >
          Send
        </button>
        <button className="px-3 py-2 border" onClick={cancel}>
          Stop
        </button>
      </div>

      <div className="mt-6 space-y-3">
        {messages.map((m, idx) => (
          <div key={idx} className={m.type === 'human' ? 'text-right' : 'text-left'}>
            <div className={
              'inline-block rounded px-3 py-2 ' +
              (m.type === 'human' ? 'bg-blue-600 text-white' : 'bg-gray-100')
            }>
              {m.content}
            </div>
          </div>
        ))}
        {!done && data?.output && (
          <div className="text-left">
            <div className="inline-block rounded px-3 py-2 bg-gray-100">
              {data.output}
            </div>
          </div>
        )}
      </div>

      {/* Placeholder area for NASA Worldview preview */}
      <div className="mt-6 border rounded p-4 text-sm text-gray-600">
        NASA Worldview preview will appear here (image or URL placeholder).
      </div>
    </main>
  );
}