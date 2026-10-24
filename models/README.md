# models/（不入库）

RAG 用的本地 embedding 模型：**BAAI/bge-small-zh-v1.5**（fastembed 版，约 91MB）。
体积原因不提交；按下面命令下载到 `models/bge-small-zh-v1.5/`。

```bash
mkdir -p models/bge-small-zh-v1.5
cd models/bge-small-zh-v1.5
for f in config.json model_optimized.onnx special_tokens_map.json tokenizer.json tokenizer_config.json vocab.txt; do
  curl -sL --fail "https://hf-mirror.com/Qdrant/bge-small-zh-v1.5/resolve/main/$f" -o "$f"
done
```

然后建索引：

```powershell
.\.venv\Scripts\python.exe rag\rag.py build
```