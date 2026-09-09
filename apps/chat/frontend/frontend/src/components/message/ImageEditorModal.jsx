import { useCallback, useEffect, useRef, useState } from 'react'

const COLORS = ['#ff4d4f', '#faad14', '#52c41a', '#1677ff', '#722ed1', '#111827']

function canvasPoint(canvas, event) {
  const rect = canvas.getBoundingClientRect()
  const x = ((event.clientX - rect.left) / rect.width) * canvas.width
  const y = ((event.clientY - rect.top) / rect.height) * canvas.height
  return { x, y }
}

export default function ImageEditorModal({ file, onCancel, onSend, primaryLabel = '发送图片' }) {
  const canvasRef = useRef(null)
  const historyRef = useRef([])
  const drawingRef = useRef(null)
  const [tool, setTool] = useState('brush')
  const [color, setColor] = useState(COLORS[0])
  const [size, setSize] = useState(4)
  const [text, setText] = useState('')
  const [ready, setReady] = useState(false)
  const [busy, setBusy] = useState(false)

  const pushHistory = useCallback(() => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return
    historyRef.current = [...historyRef.current.slice(-20), ctx.getImageData(0, 0, canvas.width, canvas.height)]
  }, [])

  useEffect(() => {
    if (!file) return undefined
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return undefined
    setReady(false)
    const objectUrl = URL.createObjectURL(file)
    const image = new Image()
    image.onload = () => {
      const maxW = 960
      const maxH = 620
      const scale = Math.min(1, maxW / image.width, maxH / image.height)
      canvas.width = Math.max(1, Math.round(image.width * scale))
      canvas.height = Math.max(1, Math.round(image.height * scale))
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      ctx.drawImage(image, 0, 0, canvas.width, canvas.height)
      historyRef.current = []
      pushHistory()
      setReady(true)
    }
    image.src = objectUrl
    return () => URL.revokeObjectURL(objectUrl)
  }, [file, pushHistory])

  const restoreImageData = (imageData) => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx || !imageData) return
    ctx.putImageData(imageData, 0, 0)
  }

  const onPointerDown = (event) => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx || !ready) return
    const start = canvasPoint(canvas, event)
    canvas.setPointerCapture?.(event.pointerId)
    if (tool === 'text') {
      const label = text.trim()
      if (!label) return
      ctx.save()
      ctx.fillStyle = color
      ctx.font = `${Math.max(16, size * 5)}px sans-serif`
      ctx.textBaseline = 'top'
      ctx.fillText(label, start.x, start.y)
      ctx.restore()
      pushHistory()
      return
    }
    const snapshot = ctx.getImageData(0, 0, canvas.width, canvas.height)
    drawingRef.current = { start, last: start, snapshot }
    if (tool === 'brush') {
      ctx.save()
      ctx.strokeStyle = color
      ctx.lineWidth = size
      ctx.lineCap = 'round'
      ctx.lineJoin = 'round'
      ctx.beginPath()
      ctx.moveTo(start.x, start.y)
      ctx.restore()
    }
  }

  const onPointerMove = (event) => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    const drawing = drawingRef.current
    if (!canvas || !ctx || !drawing) return
    const point = canvasPoint(canvas, event)
    if (tool === 'brush') {
      ctx.save()
      ctx.strokeStyle = color
      ctx.lineWidth = size
      ctx.lineCap = 'round'
      ctx.lineJoin = 'round'
      ctx.beginPath()
      ctx.moveTo(drawing.last.x, drawing.last.y)
      ctx.lineTo(point.x, point.y)
      ctx.stroke()
      ctx.restore()
      drawing.last = point
      return
    }
    if (tool === 'rect') {
      restoreImageData(drawing.snapshot)
      ctx.save()
      ctx.strokeStyle = color
      ctx.lineWidth = size
      ctx.strokeRect(drawing.start.x, drawing.start.y, point.x - drawing.start.x, point.y - drawing.start.y)
      ctx.restore()
    }
  }

  const onPointerUp = (event) => {
    const canvas = canvasRef.current
    if (!canvas || !drawingRef.current) return
    canvas.releasePointerCapture?.(event.pointerId)
    drawingRef.current = null
    pushHistory()
  }

  const undo = () => {
    if (historyRef.current.length <= 1) return
    historyRef.current.pop()
    restoreImageData(historyRef.current[historyRef.current.length - 1])
  }

  const send = async () => {
    const canvas = canvasRef.current
    if (!canvas || !file) return
    setBusy(true)
    try {
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png', 0.92))
      if (!blob) throw new Error('图片导出失败')
      const edited = new File([blob], `${String(file.name || 'image').replace(/\.[^.]+$/, '')}-edited.png`, { type: 'image/png' })
      await onSend(edited)
    } finally {
      setBusy(false)
    }
  }

  if (!file) return null

  return (
    <div className="modalBackdrop" role="presentation">
      <div className="imageEditorModal" role="dialog" aria-modal="true" aria-label="图片编辑器">
        <div className="imageEditorModal__head">
          <div>
            <div className="imageEditorModal__title">编辑图片</div>
            <div className="imageEditorModal__sub">{file.name || '粘贴图片'}</div>
          </div>
          <button type="button" className="wxBtn" onClick={onCancel} disabled={busy}>关闭</button>
        </div>
        <div className="imageEditorModal__tools">
          {[
            ['brush', '画笔'],
            ['rect', '框选'],
            ['text', '文字'],
          ].map(([id, label]) => (
            <button key={id} type="button" className={`chatToolBtn${tool === id ? ' is-active' : ''}`} onClick={() => setTool(id)}>
              {label}
            </button>
          ))}
          <div className="imageEditorModal__swatches" role="group" aria-label="颜色">
            {COLORS.map((c) => (
              <button
                key={c}
                type="button"
                className={`imageEditorModal__swatch${color === c ? ' is-active' : ''}`}
                style={{ background: c }}
                aria-label={c}
                onClick={() => setColor(c)}
              />
            ))}
          </div>
          <label className="imageEditorModal__range">
            粗细
            <input type="range" min="2" max="18" value={size} onChange={(e) => setSize(Number(e.target.value))} />
          </label>
          <input className="imageEditorModal__textInput" value={text} onChange={(e) => setText(e.target.value)} placeholder="文字标注" disabled={tool !== 'text'} />
          <button type="button" className="wxBtn" onClick={undo} disabled={busy}>撤销</button>
        </div>
        <div className="imageEditorModal__stage">
          <canvas
            ref={canvasRef}
            className="imageEditorModal__canvas"
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
          />
        </div>
        <div className="imageEditorModal__foot">
          <button type="button" className="wxBtn" onClick={onCancel} disabled={busy}>取消</button>
          <button type="button" className="wxBtn wxBtn--primary" onClick={() => void send()} disabled={!ready || busy}>
            {busy ? '处理中…' : primaryLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
