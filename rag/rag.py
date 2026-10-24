r"""最小可用的 RAG 检索层

链路：语料分块 → 本地向量化（bge-small-zh）→ Chroma 持久化 → 混合检索（向量 + BM25）

为什么是混合：bge-small-zh 对代码标识符/文件名区分度弱（实测 Q5/Q8 纯向量召不回），
BM25 靠字面匹配补位，两路用 RRF 融合，不用调权重。

可调参数都在下面，改完重跑：
    .\.venv\Scripts\python.exe evals\retrieval_eval.py

用法：
    .\.venv\Scripts\python.exe rag\rag.py build                    # 建/重建索引
    .\.venv\Scripts\python.exe rag\rag.py query "问题" [--k 5] [--mode hybrid|dense|lex]
    .\.venv\Scripts\python.exe rag\rag.py stats                    # 索引里有多少块
"""

import os
import re
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import chromadb  # noqa: E402

from embed import embed_texts, get_model  # noqa: E402

try:  # 作为包导入（evals 里）
    from rag.lexical import BM25  # noqa: E402
except ImportError:  # 直接当脚本跑（python rag\rag.py）
    from lexical import BM25  # noqa: E402

HERE = Path(__file__).resolve().parent
_DEFAULT_CORPUS = APP / "corpus" if (APP / "corpus").is_dir() else APP.parent.parent
PRA = Path(os.getenv("CORPUS_ROOT", str(_DEFAULT_CORPUS)))  # 语料根目录（可用 CORPUS_ROOT 覆盖）
CORPUS_MANIFEST = APP / "evals" / "corpus.txt"
DB_DIR = APP / "chroma_db"
COLLECTION = "pra_corpus"

CHUNK_MODE = os.getenv('CHUNK_MODE', 'window')  # window(实测更好) | symbol(按符号切块，实验用)
CHUNK_LINES = 30        # 每块多少行
OVERLAP = 8             # 相邻块重叠多少行
MAX_CHARS = 1500        # 单块字符上限（超长行会被再切）
EMBED_BATCH = 64        # 一次向量化多少块
DEFAULT_K = 5
RRF_K = 60              # RRF 常数；60 是常用默认值
DENSE_POOL = 20         # 融合时向量召回的候选池


# ---------------- 语料 ----------------

def load_corpus_entries():
    """读 corpus.txt，返回 [(相对路径, 文本)]。"""
    rels = []
    for line in CORPUS_MANIFEST.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            rels.append(s)
    out, missing = [], []
    for rel in rels:
        p = PRA / rel
        if p.is_file():
            out.append((rel, p.read_text(encoding="utf-8", errors="replace")))
        else:
            missing.append(rel)
    if missing:
        raise FileNotFoundError(f"corpus.txt 里有文件不存在: {missing}")
    return out


def chunk_text(text: str):
    """按行窗口切块，返回 [(起始行号, 结束行号, 块文本)]（行号从 1 开始）。"""
    lines = text.splitlines()
    if not lines:
        return []
    if OVERLAP >= CHUNK_LINES:
        raise ValueError("OVERLAP 必须小于 CHUNK_LINES，否则会死循环")

    chunks, start, n = [], 0, len(lines)
    while start < n:
        end = min(start + CHUNK_LINES, n)
        body = "\n".join(lines[start:end]).strip()
        if body:
            if len(body) <= MAX_CHARS:
                pieces = [body]
            else:
                step = MAX_CHARS // 2
                pieces = [body[i:i + step] for i in range(0, len(body), step)]
            for piece in pieces:
                chunks.append((start + 1, end, piece))
        if end == n:
            break
        start += CHUNK_LINES - OVERLAP
    return chunks



# ---------------- 代码文件的「结构概览」块 ----------------

CODE_SUFFIX = {".py", ".js"}
DEF_RE = __import__("re").compile(r"^(async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)")
ROUTE_RE = __import__("re").compile(r"^(?:@app\.|app\.)(get|post|put|patch|delete|options|head|use)\(\s*[\"']([^\"']+)")
JS_FUNC_RE = __import__("re").compile(r"^(?:async\s+)?function\s+([A-Za-z0-9_]+)|^const\s+([A-Za-z0-9_]+)\s*=\s*(?:async\s*)?\(")


def structure_outline(text: str):
    """抽出路由/函数/类的清单（带行号）。

    为什么需要：问「这个服务有哪些路由」时，30 行一块的窗口要召 8 块才凑得全；
    一张一行的结构概览能一次给出全貌，也让「跨文件比较接口」有据可依。
    """
    lines = []
    for i, line in enumerate(text.splitlines(), 1):
        if not line or line[:1].isspace():   # 只取顶格代码，避免把函数内的局部变量当成符号
            continue
        s = line.strip()
        m = ROUTE_RE.match(s)
        if m:
            lines.append(f"L{i}: {m.group(1).upper()} {m.group(2)}")
            continue
        m = DEF_RE.match(s)
        if m:
            lines.append(f"L{i}: {m.group(1)} {m.group(2)}()")
            continue
        m = JS_FUNC_RE.match(s)
        if m:
            lines.append(f"L{i}: function {m.group(1) or m.group(2)}()")
    return lines


def outline_chunk(rel: str, text: str):
    """给代码文件生成一条概览块；没有可抽的东西就返回 None。"""
    if Path(rel).suffix.lower() not in CODE_SUFFIX:
        return None
    items = structure_outline(text)
    if not items:
        return None
    body = "# 文件：%s · 结构概览\n%s" % (rel, "\n".join(items))
    return {"id": f"{rel}#outline", "doc": body,
            "meta": {"source": rel, "chunk": -1, "start_line": 1,
                     "end_line": len(text.splitlines()), "kind": "outline"}}



# ---------------- 代码文件：按符号切块 ----------------

ASSIGN_RE = __import__("re").compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=")
JS_CONST_RE = __import__("re").compile(r"^const\s+([A-Za-z0-9_]+)")


def _is_boundary(line: str, suffix: str):
    s = line.strip()
    if not s or line[:1].isspace():
        return False
    if suffix == ".py":
        return s.startswith(("@", "def ", "async def ", "class ")) or bool(ASSIGN_RE.match(s))
    if suffix == ".js":
        return bool(ROUTE_RE.match(s)) or s.startswith(("function ", "const "))
    return False


def _block_header(first_line: str):
    s = first_line.strip()
    m = ROUTE_RE.match(s)
    if m:
        return f"端点 {m.group(1).upper()} {m.group(2)}"
    m = JS_CONST_RE.match(s)
    if m:
        return f"常量 {m.group(1)}"
    m = DEF_RE.match(s)
    if m:
        kind = m.group(1)
        if kind.startswith("async"):
            kind = "async 函数"
        elif kind == "class":
            kind = "类"
        else:
            kind = "函数"
        return f"{kind} {m.group(2)}"
    m = ASSIGN_RE.match(s)
    if m:
        return f"常量 {m.group(1)}"
    return "模块头部"


def code_blocks(text: str, suffix: str):
    """按顶层符号切块，返回 [(起始行, 结束行, 头部说明, 正文)]。

    为什么：30 行的滑动窗口会把一个端点切成两半，问「有哪些路由」时
    top-k 永远凑不齐；按 `@app.xxx + 函数体` 切，一块就是一个完整语义单元。
    """
    lines = text.splitlines()
    if not lines:
        return []
    bounds = []
    for i, line in enumerate(lines):
        if not _is_boundary(line, suffix):
            continue
        s = line.strip()
        if s.startswith(("def ", "async def ", "class ")) and bounds:
            j = i - 1
            while j >= 0 and not lines[j].strip():
                j -= 1
            if j >= 0 and lines[j].lstrip().startswith("@"):
                continue  # 装饰器和函数算一块
        bounds.append(i)

    out = []
    for k, start in enumerate(bounds):
        end = bounds[k + 1] if k + 1 < len(bounds) else len(lines)
        body = "\n".join(lines[start:end]).strip()
        if body:
            out.append((start + 1, end, _block_header(lines[start]), body))
    return out


# ---------------- 索引 ----------------

def get_client():
    DB_DIR.mkdir(exist_ok=True)
    return chromadb.PersistentClient(path=str(DB_DIR))


def get_collection(client, create=True):
    if create:
        return client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
    return client.get_collection(COLLECTION)


def build(rebuild: bool = True):
    client = get_client()
    if rebuild:
        try:
            client.delete_collection(COLLECTION)
        except Exception:
            pass
    col = get_collection(client)

    entries = load_corpus_entries()
    ids, docs, metas = [], [], []
    for rel, text in entries:
        oc = outline_chunk(rel, text)
        if oc:  # 代码文件先放一条结构概览
            ids.append(oc["id"])
            docs.append(oc["doc"])
            metas.append(oc["meta"])
        suffix = Path(rel).suffix.lower()
        if CHUNK_MODE == 'symbol' and suffix in CODE_SUFFIX:
            # 代码：按符号切块，块头带上「端点/函数/常量」，一块一个语义单元
            pieces = [(s, e, f"{rel} · {h}", b) for s, e, h, b in code_blocks(text, suffix)]
        else:
            # 文本：行窗口切块；路径写进块文本，方便「点名文件」的查询
            pieces = [(s, e, rel, b) for s, e, b in chunk_text(text)]

        for i, (start, end, label, body) in enumerate(pieces):
            doc = f"# 文件：{label}\n{body}"
            ids.append(f"{rel}#{i}")
            docs.append(doc)
            metas.append({"source": rel, "chunk": i, "start_line": start, "end_line": end})

    for i in range(0, len(ids), EMBED_BATCH):
        batch = docs[i:i + EMBED_BATCH]
        col.upsert(
            ids=ids[i:i + EMBED_BATCH],
            documents=batch,
            metadatas=metas[i:i + EMBED_BATCH],
            embeddings=embed_texts(batch),
        )

    global _ALL
    _ALL = None  # 索引变了，BM25 缓存作废
    print(f"语料 {len(entries)} 个文件 → {len(ids)} 块 → 集合 {COLLECTION}（共 {col.count()} 条）")
    return len(ids)


# ---------------- 检索 ----------------

def embed_query(text: str):
    # 查询用 query_embed（bge 系列推荐；本机实测与 embed 等价，但语义上更对）
    return [list(map(float, v)) for v in get_model().query_embed([text])]


def _hit(cid, doc, meta, distance, lex_score=None):
    return {
        "id": cid,
        "source": meta["source"],
        "start_line": meta["start_line"],
        "end_line": meta["end_line"],
        "distance": distance,
        "lex_score": lex_score,
        "text": doc,
    }


def retrieve_dense(question: str, k: int = DEFAULT_K):
    col = get_collection(get_client(), create=False)
    res = col.query(
        query_embeddings=embed_query(question),
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )
    hits = []
    for i in range(len(res["ids"][0])):
        hits.append(_hit(res["ids"][0][i], res["documents"][0][i],
                         res["metadatas"][0][i], float(res["distances"][0][i])))
    return hits


_ALL = None


def _all_chunks():
    """把整个集合读进内存（语料很小），供 BM25 用；进程内缓存一次。"""
    global _ALL
    if _ALL is None:
        col = get_collection(get_client(), create=False)
        d = col.get(include=["documents", "metadatas"])
        ids, docs, metas = d["ids"], d["documents"], d["metadatas"]
        _ALL = (ids, docs, metas, BM25(docs))
    return _ALL


LIST_Q = re.compile(r"哪些|全部|所有|清单|列表|都有|概览|列举")
ROUTE_MARK = re.compile(r"L\d+: (GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\b")


def retrieve(question: str, k: int = DEFAULT_K, mode: str = "hybrid"):
    """mode: hybrid（默认，向量+BM25 的 RRF 融合）/ dense / lex。

    hybrid 上叠了两条可解释的小规则（都不是权重魔改）：
      1) 问题点名了文件（如 server.js / notes.txt）→ 保证该文件至少一块进上下文；
      2) 「哪些/全部/清单/列表」类问题 → 附带最相关文件的结构概览块。
    """
    if mode == "dense":
        return retrieve_dense(question, k)

    ids, docs, metas, bm = _all_chunks()
    lex_scores = bm.scores(question)
    pos = {cid: i for i, cid in enumerate(ids)}

    if mode == "lex":
        order = sorted(range(len(ids)), key=lambda i: -lex_scores[i])[:k]
        return [_hit(ids[i], docs[i], metas[i], None, lex_scores[i]) for i in order]

    pool = min(max(k * 4, DENSE_POOL), len(ids))
    dense = retrieve_dense(question, pool)
    dense_rank = {h["id"]: r for r, h in enumerate(dense, 1)}
    lex_order = sorted(range(len(ids)), key=lambda i: -lex_scores[i])[:pool]
    lex_rank = {ids[i]: r for r, i in enumerate(lex_order, 1)}

    fused = {}
    for cid, r in dense_rank.items():
        fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + r)
    for cid, r in lex_rank.items():
        fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + r)
    ranked = [cid for cid, _ in sorted(fused.items(), key=lambda kv: -kv[1])]

    # 规则 1：点名文件 → 该文件的最相关块直接置顶（文件名是强信号）
    all_sources = {m["source"] for m in metas}
    mentioned = [rel for rel in all_sources if rel in question or Path(rel).name in question]
    priority = []
    for rel in mentioned:
        cand = [h for h in dense if h["source"] == rel]
        if not cand:
            cand = [_hit(ids[i], docs[i], metas[i], None, lex_scores[i])
                    for i in range(len(ids)) if metas[i]["source"] == rel]
        if cand:
            best = min(cand, key=lambda h: h["distance"] if h["distance"] is not None else 9.0)
            priority.append(best["id"])
    if priority:
        ranked = priority + [c for c in ranked if c not in priority]

    # 规则 2：列表类问题 → 附带「含路由」的结构概览（不一定是 top-1 文件）
    if LIST_Q.search(question) and ranked:
        chosen = None
        for cid in ranked:
            if cid not in pos:
                continue
            src = metas[pos[cid]]["source"]
            oid = f"{src}#outline"
            if oid in pos and ROUTE_MARK.search(docs[pos[oid]]):  # 该文件确实有路由
                chosen = oid
                break
        if chosen and chosen not in ranked[:k]:
            ranked = [c for c in ranked if c != chosen]
            ranked.insert(min(k - 1, len(ranked)), chosen)

    out = []
    by_id = {h["id"]: h for h in dense}
    for cid in ranked[:k]:
        h = by_id.get(cid)
        if h is None:
            i = pos[cid]
            h = _hit(cid, docs[i], metas[i], None, lex_scores[i])
        h = dict(h)
        h["score"] = fused.get(cid, 0.0)
        h["dense_rank"] = dense_rank.get(cid)
        h["lex_rank"] = lex_rank.get(cid)
        out.append(h)
    return out


# ---------------- CLI ----------------

def _cli(argv):
    if not argv:
        print(__doc__)
        return
    cmd = argv[0]
    if cmd == "build":
        build(rebuild=True)
    elif cmd == "stats":
        col = get_collection(get_client(), create=False)
        print("集合", COLLECTION, "共", col.count(), "条")
    elif cmd == "query":
        q = argv[1] if len(argv) > 1 else ""
        k = DEFAULT_K
        mode = "hybrid"
        if "--k" in argv:
            k = int(argv[argv.index("--k") + 1])
        if "--mode" in argv:
            mode = argv[argv.index("--mode") + 1]
        for i, h in enumerate(retrieve(q, k, mode), 1):
            d = "  -  " if h.get("distance") is None else f"{h['distance']:.3f}"
            print(f"{i}. dense={d} lex={h.get('lex_score') or 0:.2f} {h['source']}  L{h['start_line']}-{h['end_line']}")
            print("   " + h["text"].replace("\n", " ")[:110] + ("…" if len(h["text"]) > 110 else ""))
    else:
        print("未知命令:", cmd)
        print(__doc__)


if __name__ == "__main__":
    _cli(sys.argv[1:])
