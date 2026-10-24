"""本地免费中文向量化：BAAI/bge-small-zh-v1.5（fastembed + onnxruntime，无需 API key）。

背景 / 为什么这么写：
    huggingface-hub 默认会把模型存到缓存再用「符号链接」放进度快照目录。
    本机上这一步建不出链接（snapshot 目录恒为空、blobs 却在），导致 fastembed 一直
    报 `model_optimized.onnx ... File doesn't exist`。换 hub 版本、清缓存、关沙箱都无效。
    解法：用普通 HTTP 把模型文件当**真实副本**下到 models/bge-small-zh-v1.5/，
    再用 `specific_model_path` 指本地目录 —— 彻底绕开 hub 的快照机制。

模型文件（已下载，共约 91MB，见 .gitignore）：
    models/bge-small-zh-v1.5/{config.json, model_optimized.onnx,
        special_tokens_map.json, tokenizer.json, tokenizer_config.json, vocab.txt}
若丢失，重新下（国内用 hf-mirror 镜像）：
    for f in config.json model_optimized.onnx special_tokens_map.json tokenizer.json tokenizer_config.json vocab.txt; do
      curl -sL --fail "https://hf-mirror.com/Qdrant/bge-small-zh-v1.5/resolve/main/$f" -o "models/bge-small-zh-v1.5/$f"
    done

用法：
    from embed import embed_texts
    vecs = embed_texts(["文本一", "文本二"])   # -> list[list[float]]，512 维
"""

from pathlib import Path

from fastembed import TextEmbedding

MODEL_NAME = "BAAI/bge-small-zh-v1.5"
MODEL_DIR = Path(__file__).resolve().parent / "models" / "bge-small-zh-v1.5"

_model = None


def get_model() -> TextEmbedding:
    global _model
    if _model is None:
        if not MODEL_DIR.is_dir():
            raise FileNotFoundError(
                f"本地模型目录不存在：{MODEL_DIR}\n"
                "按本文件顶部注释用 hf-mirror 重新下载模型文件。"
            )
        _model = TextEmbedding(model_name=MODEL_NAME, specific_model_path=str(MODEL_DIR))
    return _model


def embed_texts(texts):
    """把一批文本转成向量（list[list[float]]，512 维，已做 L2 归一化便于余弦相似度）。"""
    return [list(map(float, v)) for v in get_model().embed(list(texts))]


if __name__ == "__main__":
    vs = embed_texts(["测试中文向量化", "FastAPI 的路由怎么定义"])
    print("维度 =", len(vs[0]))
    print("前 4 维 =", [round(x, 4) for x in vs[0][:4]])
