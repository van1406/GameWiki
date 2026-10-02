/**
 * Renders one turn of the conversation:
 *  - user questions as chat bubbles
 *  - AI answers as a "card" with status badge, answer text and sources
 */
export default function Message({ msg }) {
  if (msg.role === 'user') {
    return (
      <div className="flex animate-fade-up justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-gradient-to-br from-cyan-500 to-sky-700 px-4 py-2.5 text-sm text-white shadow-lg shadow-cyan-500/10">
          {msg.text}
        </div>
      </div>
    )
  }

  const notFound = msg.found === false

  return (
    <div className="flex animate-fade-up justify-start">
      <div
        className={`w-full rounded-2xl border p-4 shadow-2xl shadow-black/40 sm:p-5 ${
          notFound
            ? 'border-amber-400/30 bg-amber-500/[0.06]'
            : 'border-cyan-400/20 bg-slate-900/70'
        }`}
      >
        {/* Header row */}
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <span
            className={`font-display text-[11px] font-bold tracking-[0.2em] ${
              notFound ? 'text-amber-300' : 'text-cyan-300'
            }`}
          >
            {notFound ? '⚠ NO MATCH FOUND' : 'AI ANSWER'}
          </span>
          <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[10px] font-medium uppercase tracking-wider text-slate-400">
            {msg.gameName}
          </span>
        </div>

        {/* Answer */}
        <p className="whitespace-pre-line text-sm leading-relaxed text-slate-100">
          {msg.text}
        </p>
        {!notFound && (
          <p className="mt-2 text-[11px] text-slate-500">
            Answer generated from the game knowledge base.
          </p>
        )}
        {notFound && (
          <p className="mt-2 text-[11px] text-amber-200/70">
            No sufficiently relevant information was retrieved, so nothing was invented.
          </p>
        )}

        {/* Sources */}
        {msg.sources?.length > 0 && (
          <div className="mt-4 border-t border-white/5 pt-3">
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500">
              Sources
            </div>
            <div className="flex flex-wrap gap-2">
              {msg.sources.map((source, i) => (
                <div
                  key={`${source.file}-${source.page}-${i}`}
                  className="max-w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2"
                  title={[source.title, ...(source.sections || [])].filter(Boolean).join(' · ')}
                >
                  <div className="flex items-center gap-2 text-xs text-slate-200">
                    <span aria-hidden>📄</span>
                    <span className="font-medium">{source.file}</span>
                    {source.page != null && (
                      <span className="text-slate-500">page {source.page}</span>
                    )}
                  </div>
                  {[source.title, ...(source.sections || [])].filter(Boolean).length > 0 && (
                    <div className="mt-0.5 max-w-[240px] truncate text-[10px] text-slate-500">
                      {[source.title, ...(source.sections || [])].filter(Boolean).join(' · ')}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Retrieval meta */}
        {msg.found !== false && typeof msg.chunks === 'number' && (
          <div className="mt-3 text-[10px] uppercase tracking-wider text-slate-600">
            Retrieved {msg.chunks} chunk{msg.chunks === 1 ? '' : 's'}
            {typeof msg.score === 'number' ? ` · best match ${msg.score.toFixed(2)}` : ''}
          </div>
        )}
      </div>
    </div>
  )
}
