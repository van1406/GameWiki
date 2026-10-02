/**
 * Landing.jsx — the first screen shown when the site opens.
 *
 * Purely additive entry flow:   Landing  →  [ START ]  →  existing GameWiki UI.
 * The chatbot interface (App.jsx) is rendered untouched by main.jsx once the
 * user presses START. Nothing here is persisted, so a page refresh lands back
 * on this screen.
 */
export default function Landing({ onStart }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-6 py-16 text-center">
      {/* Same "GW" mark used in the chat header */}
      <div
        aria-hidden
        className="animate-fade-up mb-7 grid h-14 w-14 place-items-center rounded-2xl bg-gradient-to-br from-cyan-400 to-violet-600 font-display text-base font-black text-slate-950 shadow-lg shadow-cyan-500/25"
        style={{ animationDelay: '0.05s' }}
      >
        GW
      </div>

      <h1
        className="animate-fade-up text-glow bg-gradient-to-r from-cyan-300 via-sky-400 to-violet-400 bg-clip-text font-display text-4xl font-black tracking-[0.16em] text-transparent sm:text-6xl sm:tracking-widest"
        style={{ animationDelay: '0.15s' }}
      >
        GAMEWIKI AI
      </h1>

      <p
        className="animate-fade-up mt-5 text-sm font-medium tracking-[0.28em] text-slate-400 sm:text-base"
        style={{ animationDelay: '0.3s' }}
      >
        Your Personal Game Wiki
      </p>

      <button
        type="button"
        onClick={onStart}
        className="landing-cta rounded-xl border border-cyan-400/40 bg-gradient-to-r from-cyan-500 to-violet-600 px-10 py-4 font-display text-sm font-black tracking-[0.35em] text-white transition hover:brightness-110 focus:outline-none focus:ring-2 focus:ring-cyan-400/60 focus:ring-offset-2 focus:ring-offset-[#05070f] active:scale-95"
      >
        [ START ]
      </button>
    </div>
  )
}
