import { useState } from 'react'

function fmtMs(ms) {
  if (ms == null) return ''
  return ms >= 1000 ? (ms / 1000).toFixed(1) + ' s' : ms + ' ms'
}

export default function AnswerCard({ item }) {
  const { question, answer, sources = [], usage, ms, error, pending } = item
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(answer || '')
      setCopied(true)
      setTimeout(() => setCopied(false), 1200)
    } catch {
      /* 忽略：剪贴板权限被拒也不影响阅读 */
    }
  }

  return (
    <article className="card qa">
      <div className="q">{question}</div>

      {pending && (
        <div className="pending">
          <span className="spinner" />
          检索 + 生成中…
        </div>
      )}

      {error && <div className="error">请求失败：{error}</div>}

      {!pending && !error && (
        <>
          <div className="a">{answer}</div>

          <div className="meta">
            <span>{fmtMs(ms)}</span>
            {usage && <span>输入 {usage.in} / 输出 {usage.out} tokens</span>}
            <span>引用 {sources.length} 条</span>
            <button className="ghost small" onClick={copy}>{copied ? '已复制' : '复制回答'}</button>
          </div>

          {sources.length > 0 && (
            <div className="sources">
              {sources.map((s, i) => (
                <div className="src" key={`${s.source}-${s.start_line}-${i}`}>
                  <div className="src-head">
                    <span className="src-name">{s.source}</span>
                    <span className="dist">
                      L{s.start_line}–{s.end_line}
                      {s.distance != null && ` · 距离 ${s.distance}`}
                    </span>
                  </div>
                  {s.preview && <div className="preview">{s.preview}</div>}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </article>
  )
}