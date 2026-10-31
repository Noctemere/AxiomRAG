"use client";

import { FormEvent, useState } from "react";

type StreamEvent = {
  event: string;
  data: string;
};

type Citation = {
  source_name: string;
  quote: string;
  provenance: {
    page_number: number | null;
    region_id: string | null;
  };
};

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function* readSse(response: Response): AsyncGenerator<StreamEvent> {
  if (!response.body) {
    throw new Error("The query stream returned no response body.");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        const event = frame.match(/^event: (.+)$/m)?.[1] ?? "message";
        const data = frame.match(/^data: (.+)$/m)?.[1];
        if (data !== undefined) {
          yield { event, data: JSON.parse(data) as string };
        }
      }
      if (done) return;
    }
  } finally {
    reader.releaseLock();
  }
}

export default function QueryClient() {
  const [query, setQuery] = useState("");
  const [answer, setAnswer] = useState("");
  const [citations, setCitations] = useState<Citation[]>([]);
  const [route, setRoute] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [controller, setController] = useState<AbortController | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!query.trim() || loading) return;
    const nextController = new AbortController();
    setController(nextController);
    setLoading(true);
    setAnswer("");
    setCitations([]);
    setRoute("");
    setError("");
    try {
      const response = await fetch(`${apiUrl}/api/v1/query/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: nextController.signal,
        body: JSON.stringify({ text: query, tenant_id: crypto.randomUUID() }),
      });
      if (!response.ok) {
        throw new Error(`Query request failed with HTTP ${response.status}.`);
      }
      for await (const eventItem of readSse(response)) {
        if (eventItem.event === "route") setRoute(eventItem.data);
        if (eventItem.event === "token") setAnswer((current) => current + eventItem.data);
        if (eventItem.event === "citation") {
          setCitations((current) => [...current, JSON.parse(eventItem.data) as Citation]);
        }
        if (eventItem.event === "error") throw new Error(eventItem.data);
      }
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") return;
      setError(caught instanceof Error ? caught.message : "The query failed.");
    } finally {
      setLoading(false);
      setController(null);
    }
  }

  return (
    <main className="workspace">
      <p className="eyebrow">AXIOMRAG / QUERY WORKSPACE</p>
      <h1>Ask your sources.</h1>
      <p className="lede">Stream grounded answers from documents and structured data.</p>
      <form className="query-form" onSubmit={submit}>
        <label htmlFor="query">Question</label>
        <textarea
          id="query"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="What does the policy say about quarterly review?"
          rows={4}
          disabled={loading}
        />
        <div className="form-actions">
          <button type="submit" disabled={loading || !query.trim()}>
            {loading ? "Thinking..." : "Ask question"}
          </button>
          {loading && (
            <button type="button" className="secondary" onClick={() => controller?.abort()}>
              Stop
            </button>
          )}
        </div>
      </form>
      {route && <p className="route">Route: {route}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {answer && (
        <section className="answer" aria-live="polite">
          <p className="eyebrow">ANSWER</p>
          <p className="answer-text">{answer}</p>
          {citations.length > 0 && (
            <div className="citations">
              <p className="eyebrow">SOURCES</p>
              {citations.map((citation, index) => (
                <article key={`${citation.source_name}-${index}`}>
                  <strong>{citation.source_name}</strong>
                  <p>{citation.quote}</p>
                  {citation.provenance.page_number && (
                    <small>Page {citation.provenance.page_number}</small>
                  )}
                </article>
              ))}
            </div>
          )}
        </section>
      )}
    </main>
  );
}
