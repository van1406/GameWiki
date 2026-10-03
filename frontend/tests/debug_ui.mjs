/** One-off debug: navigate, click START, dump page state (select options, banners, errors). */
const CDP_PORT = 9222
const APP_URL = 'http://localhost:5173'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const targets = await fetch(`http://localhost:${CDP_PORT}/json/list`).then((r) => r.json())
const page = targets.find((t) => t.type === 'page')
const ws = new WebSocket(page.webSocketDebuggerUrl)
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej })
let id = 0
const pending = new Map()
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data)
  if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id) }
}
const send = (method, params = {}) => new Promise((resolve) => {
  const msgId = ++id
  pending.set(msgId, resolve)
  ws.send(JSON.stringify({ id: msgId, method, params }))
})
const evaluate = async (expression) => {
  const res = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
  if (res.result?.exceptionDetails) throw new Error('Page error: ' + JSON.stringify(res.result.exceptionDetails))
  return res.result?.result?.value
}
const log = (...a) => console.log(...a)

await send('Page.enable')
await send('Runtime.enable')
await send('Log.enable')
ws.addEventListener('message', (event) => {
  const msg = JSON.parse(event.data)
  if (msg.method === 'Log.entryAdded') log('[browser log]', msg.params.entry.level, msg.params.entry.text)
  if (msg.method === 'Runtime.exceptionThrown') log('[exception]', JSON.stringify(msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails).slice(0, 500))
  if (msg.method === 'Network.loadingFailed') log('[net fail]', msg.params.errorText, msg.params.type)
})

await send('Page.navigate', { url: APP_URL })
await sleep(4000)
log('after load:', await evaluate(`JSON.stringify({buttons:[...document.querySelectorAll('button')].map(b=>b.textContent.trim())})`))
log('click START result:', await evaluate(`(() => { const b=[...document.querySelectorAll('button')].find(x=>x.textContent.includes('START')); if(!b) return 'no start button'; b.click(); return 'clicked'; })()`))
await sleep(6000)
log('state:', await evaluate(`JSON.stringify({
  hasSelect: !!document.querySelector('select'),
  options: [...(document.querySelector('select')?.options||[])].map(o=>o.value),
  banners: [...document.querySelectorAll('main div')].map(d=>d.textContent).filter(t=>t && t.length<200 && (t.startsWith('⚠') || t.includes('not ready'))).slice(0,5),
  bodySnippet: document.body.innerText.slice(0,400)
}, null, 2)`))
const games = await evaluate(`fetch('/api/games').then(r=>r.status + ' ' + r.headers.get('content-type')).catch(e=>'fetch error: '+e.message)`)
log('direct fetch /api/games ->', games)
ws.close()
