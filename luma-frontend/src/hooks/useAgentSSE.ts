'use client';
import { useEffect, useRef, useState } from 'react';

export type AgentEvent = { messages: any[]; output: string; images_output: any[] };

export function useAgentSSE(input: string, threadId?: string) {
  const [data, setData] = useState<AgentEvent | null>(null);
  const [done, setDone] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!input) return;
    setDone(false);
    setData(null);
    const params = new URLSearchParams({ input, ...(threadId ? { thread_id: threadId } : {}) });
    const es = new EventSource(`/api/agent/stream?${params.toString()}`);
    esRef.current = es;

    const onUpdate = (e: MessageEvent) => setData(JSON.parse(e.data));
    const onDone = () => { setDone(true); es.close(); };

    es.addEventListener('update', onUpdate);
    es.addEventListener('done', onDone);
    es.onerror = () => es.close();

    return () => { es.removeEventListener('update', onUpdate); es.removeEventListener('done', onDone); es.close(); };
  }, [input, threadId]);

  const cancel = () => { esRef.current?.close(); };

  return { data, done, cancel };
}