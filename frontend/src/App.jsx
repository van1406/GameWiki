import { useEffect, useRef, useState } from 'react'
import { askQuestion, getGames, getHealth } from './api.js'
import { examplesFor } from './data/examples.js'
import Message from './components/Message.jsx'

export default function App() {
  const [games, setGames] = useState([])
  const [game, setGame] = useState('')
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [bootError, setBootError] = useState('')
  const [health, setHealth] = useState(null)

  const idRef = useRef(0)
  const bottomRef = useRef(null)

  // Load available games + service status once on mount.
  useEffect(() => {
    getGames()
      .then((list) => {
        setGames(list)
        if (list.length > 0) setGame(list[0].id)
        else setBootError('No games found in knowledge_base/. Add game folders and run ingestion.')
      })
      .catch((e) => setBootError(e.message))
    getHealth()
      .then(setHealth)
      .catch(() => {})
  }, [])

  // Keep the newest message in view.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, loading])

  const selectedGame = games.find((g) => g.id === game)
  const indexReady = health?.index_available
  const llmReady = health?.llm?.configured

  async function submit(text) {
    const q = (text ?? question).trim()
    if (!q) {
      setError('Please enter a question first.')
      return
    }
    if (!game) {
      setError('Please select a game first.')
      return
    }
    setError('')
    setQuestion('') // clear the input (covers both form submit and example chips)
    setMessages((prev) => [...prev, { id: ++idRef.current, role: 'user', text: q }])
    setLoading(true)
    try {
      const res = await askQuestion(game, q)
      setMessages((prev) => [
        ...prev,
        {
          id: ++idRef.current,
          role: 'assistant',
          text: res.answer,
          sources: res.sources || [],
          found: res.found !== false,
          chunks: res.retrieved_chunks,
          score: res.top_score,
          gameName: selectedGame?.name || game,
        },
      ])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  function clearChat() {
    setMessages([])
    setError('')
  }

  return (
    <div className="flex min-h-screen flex-col">
      {/* ---------------------------------------------------------- header */}
      <header className="sticky top-0 z-20 border-b border-white/5 bg-[#05070f]/80 backdrop-blur">
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-3 px-4 py-3.5">
          <div className="flex items-center gap-3">
            <div className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-cyan-400 to-violet-600 font-display text-sm font-black text-slate-950 shadow-lg shadow-cyan-500/25">
              GW
            </div>
            <div>
              <h1 className="font-display text-lg font-black tracking-wider bg-gradient-to-r from-cyan-300 via-sky-400 to-violet-400 bg-clip-text text-transparent sm:text-xl">
                GAMEWIKI AI
              </h1>
              <p className="text-[11px] text-slate-400 sm:text-xs">
                Your AI-powered game knowledge assistant
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <div className="hidden items-center gap-3 text-[11px] sm:flex">
              <span
                className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 ${
                  indexReady
                    ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300'
                    : 'border-rose-400/30 bg-rose-400/10 text-rose-300'
                }`}
                title="Vector index status"
              >
                <span className={`h-1.5 w-1.5 rounded-full ${indexReady ? 'bg-emerald-400' : 'bg-rose-400'}`} />
                {indexReady ? 'Index ready' : 'Index missing'}
              </span>
              <span
                className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 ${
                  llmReady
                    ? 'border-cyan-400/30 bg-cyan-400/10 text-cyan-300'
                    : 'border-amber-400/30 bg-amber-400/10 text-amber-300'
                }`}
                title="LLM configuration status"
              >
                <span className={`h-1.5 w-1.5 rounded-full ${llmReady ? 'bg-cyan-400' : 'bg-amber-400'}`} />
                LLM: {health?.llm?.provider || '…'}
              </span>
            </div>

            <button
              onClick={clearChat}
              className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-medium text-slate-300 transition hover:border-rose-400/40 hover:bg-rose-500/10 hover:text-rose-200"
              title="Clear conversation history"
            >
              Clear chat
            </button>
          </div>
        </div>
      </header>

      {/* ------------------------------------------------------------ main */}
      <main className="mx-auto w-full max-w-5xl flex-1 space-y-5 px-4 py-6 sm:py-8">
        {/* Ask panel */}
        <section className="card animate-fade-up rounded-2xl p-5 shadow-2xl shadow-black/40 sm:p-7">
          <div className="flex flex-col gap-5 sm:flex-row sm:items-end">
            {/* Game selector */}
            <label className="flex w-full flex-col gap-1.5 sm:w-56">
              <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">
                Select game
              </span>
              <div className="relative">
                <select
                  value={game}
                  onChange={(e) => setGame(e.target.value)}
                  className="gw-select w-full rounded-xl border border-white/10 px-3.5 py-3 pr-9 text-sm font-semibold text-slate-100 outline-none transition focus:border-cyan-400/50 focus:ring-2 focus:ring-cyan-400/20"
                >
                  {games.length === 0 && <option value="">No games available</option>}
                  {games.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.name}
                      {!g.ingested ? ' (not ingested)' : ''}
                    </option>
                  ))}
                </select>
                <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-cyan-400">▾</span>
              </div>
            </label>

            {/* Question form */}
            <form
              className="flex flex-1 flex-col gap-3 sm:flex-row"
              onSubmit={(e) => {
                e.preventDefault()
                submit()
              }}
            >
              <input
                type="text"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Ask anything about the game..."
                className="gw-input w-full flex-1 rounded-xl border border-white/10 bg-black/30 px-4 py-3 text-sm text-slate-100 outline-none transition focus:border-cyan-400/50 focus:ring-2 focus:ring-cyan-400/20"
                maxLength={400}
              />
              <button
                type="submit"
                disabled={loading}
                className="rounded-xl bg-gradient-to-r from-cyan-500 to-violet-600 px-6 py-3 font-display text-xs font-bold tracking-widest text-white shadow-lg shadow-cyan-500/20 transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {loading ? 'SEARCHING…' : 'ASK GAMEWIKI'}
              </button>
            </form>
          </div>

          {/* Example questions */}
          <div className="mt-5">
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
              Try an example
            </div>
            <div className="flex flex-wrap gap-2">
              {examplesFor(game).map((ex) => (
                <button
                  key={ex}
                  onClick={() => submit(ex)}
                  disabled={loading}
                  className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-slate-300 transition hover:border-cyan-400/40 hover:bg-cyan-400/10 hover:text-cyan-200 disabled:opacity-50"
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>
        </section>

        {/* Banners */}
        {bootError && (
          <div className="rounded-xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
            ⚠ {bootError}
          </div>
        )}
        {error && (
          <div className="rounded-xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
            ⚠ {error}
          </div>
        )}
        {!error && health && !health.index_available && (
          <div className="rounded-xl border border-amber-400/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
            Vector index not built yet — run <code className="rounded bg-black/40 px-1.5 py-0.5">python backend/ingest.py</code>{' '}
            to enable answers.
          </div>
        )}

        {/* Conversation */}
        <section className="space-y-4">
          {messages.length === 0 && !loading && (
            <div className="card grid place-items-center rounded-2xl border-dashed px-6 py-12 text-center">
              <div className="mb-3 text-4xl">🎮</div>
              <p className="text-sm font-medium text-slate-300">
                Pick a game, ask a question, or try an example above.
              </p>
              <p className="mt-1 max-w-md text-xs text-slate-500">
                Answers are generated only from the game knowledge base and always show their sources.
              </p>
            </div>
          )}

          {messages.map((msg) => (
            <Message key={msg.id} msg={msg} />
          ))}

          {loading && (
            <div className="card flex animate-fade-up items-center gap-3 rounded-2xl px-4 py-3">
              <span className="pulse-ring relative inline-flex h-2.5 w-2.5 rounded-full bg-cyan-400" />
              <span className="text-sm text-slate-300">Searching the knowledge base…</span>
              <span className="flex gap-1">
                <i className="dot" />
                <i className="dot dot-2" />
                <i className="dot dot-3" />
              </span>
            </div>
          )}

          <div ref={bottomRef} />
        </section>
      </main>

      {/* ---------------------------------------------------------- footer */}
      <footer className="border-t border-white/5 py-5">
        <p className="text-center text-xs text-slate-500">
          GameWiki AI · Retrieval-Augmented Generation over your own knowledge base · answers cite their sources
        </p>
      </footer>
    </div>
  )
}
