"""轻量 BM25（纯标准库）——给 RAG 补一路「关键词」召回。

为什么需要：bge-small-zh 是中文小模型，对代码标识符 / 文件名（startWith、requirements.txt）
的区分度很弱。实测「startWith()」这种查询，向量检索甚至会把英文诗排在 JS 笔记前面。
BM25 靠字面匹配，正好补这块短板；两路用 RRF 融合，不用调权重。
"""

import math
import re
from collections import Counter

ASCII_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*|[0-9]+")
CJK_RE = re.compile(r"[\u4e00-\u9fff]+")


def tokenize(text: str):
    """ASCII 词 + CJK 二元组（中文不切词，二元组够用）。"""
    text = text.lower()
    toks = []
    for t in ASCII_RE.findall(text):
        toks.append(t)
        toks.extend(x for x in re.split(r"[._]", t) if x)
    for run in CJK_RE.findall(text):
        toks.extend(run[i:i + 2] for i in range(len(run) - 1))
    return [t for t in toks if t]


class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.docs = [tokenize(d) for d in docs]
        self.N = len(self.docs)
        self.avgdl = (sum(len(d) for d in self.docs) / self.N) if self.N else 0.0
        df = Counter()
        for d in self.docs:
            df.update(set(d))
        self.idf = {t: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for t, n in df.items()}

    def scores(self, query: str):
        q = tokenize(query)
        out = []
        for d in self.docs:
            tf = Counter(d)
            dl = len(d)
            s = 0.0
            for t in q:
                f = tf.get(t)
                if not f:
                    continue
                s += self.idf.get(t, 0.0) * f * (self.k1 + 1) / (
                    f + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                )
            out.append(s)
        return out