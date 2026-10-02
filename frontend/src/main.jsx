import React, { useState } from 'react'
import ReactDOM from 'react-dom/client'
import Landing from './Landing.jsx'
import GameWiki from './App.jsx'
import './index.css'

// Entry flow: landing page first, the existing GameWiki UI after START.
// State is not persisted, so refreshing the site starts at the landing page again.
function Root() {
  const [started, setStarted] = useState(false)
  return started ? <GameWiki /> : <Landing onStart={() => setStarted(true)} />
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
)
