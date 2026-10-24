import { useEffect, useRef, useState } from 'react'
import AnswerCard from './components/AnswerCard'

const EXAMPLES = [
  '这个服务对外暴露了哪些路由？',
  'Swagger 白屏是怎么解决的？',
  'Express 和 FastAPI 版的数据层有什么不同？',
  'todos 表里有没有 created_at 字段？',
]

const STORAGE_KEY = 'todo-rag:history:v1'

function loadHistory() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

export default function App() {
  const [question, setQuestion] = useState('')
  const [k, setK] = useState(5)
  const [items, setItems] = useState(loadHistory)
  const [loading, setLoading] = useState(false)
  const inputRef = useRef(null)

  // 历史落 localStorage（最多 20 条，丢了也只是体验损失）
  useEffect(() => {
    const slim = items.slice(0, 20).map(({ loading: _l, ...rest }) => rest)
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(slim))
    } catch {
      /* 配额满了就算了 */
    }
  }, [items])

  async function ask(text) {
    const q = String(text ?? question).trim()
    if (!q || loading) return

    const id = crypto.randomUUID ? crypto.randomUUID() : String(Date.now())
    setLoading(true)
    setQuestion('')
    setItems((prev) => [{ id, question: q, pending: true }, ...prev])

    const t0 = performance.now()
    try {
      const resp = await fetch('/rag-verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q, k, max_revisions: 0 }),
      })
      const data = await resp.json().catch(() => ({}))
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`)

      const ms = Math.round(performance.now() - t0)
      setItems((prev) =>
        prev.map((it) => (it.id === id ? { ...it, ...data, ms, pending: false } : it))
      )
    } catch (e) {
      setItems((prev) =>
        prev.map((it) =>
          it.id === id ? { ...it, pending: false, error: e.message || String(e) } : it
        )
      )
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  function onKeyDown(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault()
      ask()
    }
  }

  return (
    <div className="wrap">
      <header>
        <div>
          <h1>知识库问答</h1>
          <div className="sub">
            本地语料 · 混合检索（向量 + BM25）· DeepSeek 回答 · 独立校验
          </div>
        </div>
        <nav className="links">
          <a href="/docs" target="_blank" rel="noreferrer">API 文档</a>
          <a href="/stats-ui" target="_blank" rel="noreferrer">用量面板</a>
        </nav>
      </header>

      <section className="card ask-card">
        <label htmlFor="q" className="sub">问题</label>
        <textarea
          id="q"
          ref={inputRef}
          rows={3}
          value={question}
          placeholder="比如：这个服务对外暴露了哪些路由？"
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={onKeyDown}
        />
        <div className="row">
          <span className="hint">Ctrl / ⌘ + Enter 发送</span>
          <label className="sub" htmlFor="k">检索块数</label>
          <select id="k" value={k} onChange={(e) => setK(Number(e.target.value))}>
            {[3, 5, 8, 10].map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
          <button className="primary" onClick={() => ask()} disabled={loading || !question.trim()}>
            {loading ? '检索中…' : '问一问'}
          </button>
        </div>

        <div className="chips">
          {EXAMPLES.map((ex) => (
            <button key={ex} className="chip" onClick={() => ask(ex)} disabled={loading}>
              {ex}
            </button>
          ))}
        </div>
      </section>

      <section className="list">
        {items.length === 0 && (
          <div className="empty">
            还没有问答记录。点上面的示例问题，或者自己问一个。
          </div>
        )}
        {items.map((item) => (
          <AnswerCard key={item.id} item={item} />
        ))}
      </section>

      {items.length > 0 && (
        <footer>
          <button
            className="ghost"
            onClick={() => {
              if (confirm('清空本地历史记录？')) setItems([])
            }}
          >
            清空历史
          </button>
          <span className="hint">历史只存在本机浏览器</span>
        </footer>
      )}
    </div>
  )
}