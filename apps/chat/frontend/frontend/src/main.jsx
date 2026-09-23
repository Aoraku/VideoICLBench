import { StrictMode, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import AppRouter from './router/index.jsx'

function SessionBoundary() {
  const [unavailable, setUnavailable] = useState(false)
  useEffect(() => {
    const expired = () => setUnavailable(true)
    window.addEventListener('vic-session-unavailable', expired)
    return () => window.removeEventListener('vic-session-unavailable', expired)
  }, [])
  if (unavailable) return <main role="alert" style={{maxWidth:560,margin:'15vh auto',padding:32,lineHeight:1.8}}><h1>此应用页面已失效</h1><p>环境已重置或关闭。请回到 VideoICL 工作台，点击“打开独立应用”进入当前环境。</p><p>可以关闭这个旧标签页。</p></main>
  return <AppRouter />
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <SessionBoundary />
  </StrictMode>,
)
