export type ChatMessage = {
  type: 'human' | 'ai' | 'system';
  content: string;
};

const storageKey = (threadId: string) => `history:${threadId}`;

export function loadHistory(threadId: string): ChatMessage[] {
  try {
    const raw = localStorage.getItem(storageKey(threadId));
    return raw ? (JSON.parse(raw) as ChatMessage[]) : [];
  } catch {
    return [];
  }
}

export function saveHistory(threadId: string, messages: ChatMessage[]): void {
  localStorage.setItem(storageKey(threadId), JSON.stringify(messages));
}

export function appendMessage(
  threadId: string,
  message: ChatMessage,
  options?: { max?: number }
): ChatMessage[] {
  const current = loadHistory(threadId);
  const next = [...current, message];
  const capped = options?.max ? next.slice(-options.max) : next;
  saveHistory(threadId, capped);
  return capped;
}


