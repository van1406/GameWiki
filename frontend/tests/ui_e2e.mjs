/**
 * ui_e2e.mjs — end-to-end browser test of the per-game chat separation.
 *
 * Drives the real app (Vite dev server + FastAPI backend) in headless Chrome
 * over the DevTools protocol and walks the manual checklist:
 *   ask in GTA 5 -> switch to Minecraft (empty) -> ask -> switch back
 *   (GTA 5 restored) -> switch again (Minecraft restored) -> clear chat on
 *   Minecraft (only Minecraft cleared).
 *
 * Prerequisites (run first in other terminals):
 *   uvicorn backend.main:app --port 8000
 *   npm run dev          (from frontend/)
 *   chrome --headless --remote-debugging-port=9222 about:blank
 *
 * Run:  node tests/ui_e2e.mjs
 */

const CDP_PORT = 9222
const APP_URL = 'http://localhost:5173'

function listTargets() {
  return fetch(`http://localhost:${CDP_PORT}/json/list`).then((r) => r.json())
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function connect() {
  const targets = await listTargets()
  const page = targets.find((t) => t.type === 'page')
  if (!page) throw new Error('No page target in Chrome — is it running with --remote-debugging-port?')
  const ws = new WebSocket(page.webSocketDebuggerUrl)
  await new Promise((res, rej) => {
    ws.onopen = res
    ws.onerror = rej
  })
  let id = 0
  const pending = new Map()
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data)
    if (msg.id && pending.has(msg.id)) {
      pending.get(msg.id)(msg)
      pending.delete(msg.id)
    }
  }
  const send = (method, params = {}) =>
    new Promise((resolve) => {
      const msgId = ++id
      pending.set(msgId, resolve)
      ws.send(JSON.stringify({ id: msgId, method, params }))
    })
  const evaluate = async (expression) => {
    const res = await send('Runtime.evaluate', {
      expression,
      awaitPromise: true,
      returnByValue: true,
    })
    if (res.result?.exceptionDetails) {
      throw new Error('Page error: ' + JSON.stringify(res.result.exceptionDetails.exception))
    }
    return res.result?.result?.value
  }
  return { send, evaluate, close: () => ws.close() }
}

const PAGE_TEST = `(() => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const results = [];
  const record = (name, ok, detail) => results.push({ name, ok, detail });
  const sel = () => document.querySelector('select');
  const userCount = () => document.querySelectorAll('main .flex.justify-end').length;
  const asstCount = () => document.querySelectorAll('main .flex.justify-start').length;
  const firstUserText = () => {
    const el = document.querySelector('main .flex.justify-end > div');
    return el ? el.textContent : '';
  };
  const setSelect = (v) => {
    const s = sel();
    Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value').set.call(s, v);
    s.dispatchEvent(new Event('change', { bubbles: true }));
  };
  const setInput = (v) => {
    const i = document.querySelector('input.gw-input');
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(i, v);
    i.dispatchEvent(new Event('input', { bubbles: true }));
  };
  const waitFor = async (fn, timeout = 60000) => {
    const t0 = Date.now();
    while (Date.now() - t0 < timeout) {
      try { if (fn()) return true; } catch {}
      await sleep(300);
    }
    return false;
  };
  const ask = async (q) => {
    setInput(q);
    await sleep(100);
    document.querySelector('form button[type=submit]').click();
  };

  return (async () => {
    // 0. pass the landing screen (START button) if it is showing
    const start = [...document.querySelectorAll('button')].find(b => b.textContent.includes('START'));
    if (start) { start.click(); await sleep(500); }
    // wait for games to load
    if (!await waitFor(() => sel() && sel().options.length >= 2)) {
      record('games loaded', false, 'select never populated');
      return results;
    }
    record('games loaded', true, [...sel().options].map(o => o.value).join(','));

    // 1-2. GTA 5 selected -> ask
    setSelect('gta5');
    await sleep(300);
    record('GTA 5 selected', sel().value === 'gta5', sel().value);
    await ask('How do I remove a 5-star wanted level?');
    record('GTA 5 question asked', await waitFor(() => userCount() === 1), 'user msgs=' + userCount());
    record('GTA 5 answer arrived', await waitFor(() => asstCount() === 1), 'assistant msgs=' + asstCount());

    // 3-4. switch to Minecraft -> chat must be empty
    setSelect('minecraft');
    await sleep(400);
    record('switched to Minecraft', sel().value === 'minecraft', sel().value);
    record('Minecraft chat starts empty',
      userCount() === 0 && asstCount() === 0,
      'users=' + userCount() + ' assistants=' + asstCount());

    // 5. ask in Minecraft
    await ask('How do I find diamonds?');
    record('Minecraft question asked', await waitFor(() => userCount() === 1), 'user msgs=' + userCount());
    record('Minecraft answer arrived', await waitFor(() => asstCount() === 1), 'assistant msgs=' + asstCount());
    const mcText = firstUserText();

    // 6-7. back to GTA 5 -> previous conversation restored
    setSelect('gta5');
    await sleep(400);
    record('GTA 5 history restored',
      userCount() === 1 && asstCount() === 1 && firstUserText().includes('5-star'),
      JSON.stringify(firstUserText()));

    // 8. back to Minecraft -> its conversation restored
    setSelect('minecraft');
    await sleep(400);
    record('Minecraft history restored',
      userCount() === 1 && asstCount() === 1 && firstUserText() === mcText,
      JSON.stringify(firstUserText()));

    // 9-10. clear chat while Minecraft selected -> only Minecraft cleared
    [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Clear chat').click();
    await sleep(400);
    record('Minecraft cleared', userCount() === 0 && asstCount() === 0,
      'users=' + userCount() + ' assistants=' + asstCount());

    // 11-12. GTA 5 conversation still present
    setSelect('gta5');
    await sleep(400);
    record('GTA 5 history kept after clearing Minecraft',
      userCount() === 1 && asstCount() === 1 && firstUserText().includes('5-star'),
      JSON.stringify(firstUserText()));

    return results;
  })();
})()`

async function main() {
  const { send, evaluate, close } = await connect()
  await send('Page.enable')
  await send('Runtime.enable')
  await send('Page.navigate', { url: APP_URL })
  await sleep(3500)

  let results
  try {
    results = await evaluate(PAGE_TEST)
  } finally {
    close()
  }

  let ok = true
  for (const r of results || []) {
    console.log(`  [${r.ok ? 'PASS' : 'FAIL'}] ${r.name}  ${r.detail ?? ''}`)
    ok = ok && r.ok
  }
  if (!results || results.length === 0) {
    console.log('  [FAIL] no results — page did not run')
    ok = false
  }
  console.log(ok ? '\nUI E2E: ALL PASS' : '\nUI E2E: FAILURES')
  process.exit(ok ? 0 : 1)
}

main().catch((e) => {
  console.error('UI E2E error:', e.message)
  process.exit(1)
})
