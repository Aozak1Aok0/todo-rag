import { useEffect, useState } from 'react'

const STATUS_LABEL = {
  pending: '待确认',
  executing: '执行中',
  executed: '已执行',
  cancelled: '已取消',
  failed: '失败',
  expired: '已过期',
}

function fmtTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('zh-CN', { hour12: false })
}

export default function ProposalHistory({ version }) {
  const [data, setData] = useState({ items: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  async function load() {
    setLoading(true)
    setError('')
    try {
      const resp = await fetch('/multi-agent/proposals?limit=6')
      const body = await resp.json().catch(() => ({}))
      if (!resp.ok) throw new Error(body.detail || `HTTP ${resp.status}`)
      setData({ items: body.items || [], total: body.total || 0 })
    } catch (e) {
      setError(e.message || String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // version 变化时主动刷新；load 本身不需要进依赖
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version])

  return (
    <section className="card history-card">
      <div className="history-head">
        <div>
          <h2>最近写操作</h2>
          <div className="sub">proposal 审计记录 · 共 {data.total} 条</div>
        </div>
        <button className="ghost small" onClick={load} disabled={loading}>
          {loading ? '刷新中…' : '刷新'}
        </button>
      </div>

      {error && <div className="error">加载失败：{error}</div>}
      {!loading && !error && data.items.length === 0 && (
        <div className="history-empty">还没有写操作记录</div>
      )}

      <div className="history-list">
        {data.items.map((p) => (
          <div className="history-row" key={p.id}>
            <span className={'status ' + p.status}>
              {STATUS_LABEL[p.status] || p.status}
            </span>
            <span className="history-main">
              <span className="history-summary">{p.summary}</span>
              <span className="history-meta">
                {p.action} · {fmtTime(p.finished_at || p.created_at)}
              </span>
            </span>
          </div>
        ))}
      </div>
    </section>
  )
}
