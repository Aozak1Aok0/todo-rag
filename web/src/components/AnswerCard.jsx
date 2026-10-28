import { useState } from 'react'

function fmtMs(ms) {
  if (ms == null) return ''
  return ms >= 1000 ? (ms / 1000).toFixed(1) + ' s' : ms + ' ms'
}

const ROUTE_LABEL = {
  todos: '待办 Agent',
  docs: '文档 Agent',
  both: '待办 + 文档',
}

export default function AnswerCard({ item, onDecide }) {
  const {
    question, answer, sources = [], usage, ms, error, pending,
    verification, route, trace = [], plan, proposal, deciding, decisionError,
  } = item
  const [copied, setCopied] = useState(false)
  const verifyPrefix = route === 'both' ? '文档部分校验' : '校验'
  const routeLabel = plan?.intent === 'write' && route === 'todos'
    ? '待办写入'
    : (ROUTE_LABEL[route] || route)
  const proposalExpired = proposal?.expires_at
    ? Date.parse(proposal.expires_at) <= Date.now()
    : false
  const proposalMinutes = proposal?.expires_at
    ? Math.max(1, Math.ceil((Date.parse(proposal.expires_at) - Date.now()) / 60000))
    : Math.max(1, Math.ceil((proposal?.expires_in_seconds || 0) / 60))

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
          {item.multi ? 'Supervisor 正在分派 Agent…' : '检索 + 生成中…'}
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
            {route && <span>路由 {routeLabel}</span>}
            <button className="ghost small" onClick={copy}>{copied ? '已复制' : '复制回答'}</button>
          </div>

          {proposal && proposal.status === 'pending' && (
            <div className={'proposal' + (proposalExpired ? ' expired' : '')}>
              <div className="proposal-head">
                <span>需要确认的写操作</span>
                <span className={'badge ' + (proposalExpired ? 'muted' : 'warn')}>
                  {proposalExpired ? '已过期' : '待确认'}
                </span>
              </div>
              <div className="proposal-summary">{proposal.summary}</div>
              <div className="proposal-args">
                {proposal.action} · {JSON.stringify(proposal.args)}
              </div>
              {!proposalExpired && (
                <div className="proposal-actions">
                  <button
                    className="primary small"
                    disabled={deciding}
                    onClick={() => onDecide?.(item, true)}
                  >
                    {deciding ? '执行中…' : '确认执行'}
                  </button>
                  <button
                    className="ghost small"
                    disabled={deciding}
                    onClick={() => onDecide?.(item, false)}
                  >
                    取消
                  </button>
                </div>
              )}
              <div className="hint">
                {proposalExpired
                  ? 'proposal 已过期，请重新发起'
                  : `确认前不会修改数据 · ${proposalMinutes} 分钟内有效`}
              </div>
            </div>
          )}

          {decisionError && <div className="error">确认失败：{decisionError}</div>}

          {route && (
            <div className="agent-trace">
              <div className="agent-trace-head">
                <span>多 Agent 协作轨迹</span>
                <span className="badge">{routeLabel}</span>
              </div>
              <div className="trace-rows">
                {trace.map((t, i) => (
                  <div className="trace-row" key={`${t.agent}-${i}`}>
                    <span className={'dot ' + (t.status === 'ok' ? 'ok' : 'err')} />
                    <span className="agent-name">{t.agent}</span>
                    <span className="agent-detail">{t.detail || ''}</span>
                    <span className="agent-ms">{fmtMs(t.latency_ms)}</span>
                  </div>
                ))}
              </div>
              {plan?.reason && <div className="reason">路由理由：{plan.reason}</div>}
            </div>
          )}

          {verification && (
            <div className={'verify ' + (verification.verdict === 'ok' ? 'ok' : 'warn')}>
              <div className="verify-head">
                {verification.verdict === 'ok'
                  ? `${verifyPrefix}：通过（断言均可在资料中找到依据）`
                  : `${verifyPrefix}：${(verification.unsupported || []).length} 条断言未被资料支持`}
              </div>
              {((verification.unsupported || []).length > 0 || verification.reason) && (
                <details>
                  <summary>查看校验明细</summary>
                  {verification.reason && <div className="reason">{verification.reason}</div>}
                  {(verification.unsupported || []).length > 0 && (
                    <ul>
                      {verification.unsupported.map((x, i) => (
                        <li key={i}>{x}</li>
                      ))}
                    </ul>
                  )}
                </details>
              )}
            </div>
          )}

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
