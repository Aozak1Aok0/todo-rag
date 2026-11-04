# LLM 判分 20261104-1944

- 答案文件：`rerank-ans-40.jsonl` · 题数 40（有效 40）
- 要点命中 **123/169**（72.8%）· 幻觉 2 题

| 题 | 命中 | 未命中编号 | 幻觉 | 备注 |
|---|---|---|---|---|
| Q1 | 2/9 | 2,3,4,5,6,7,8 | 否 | 答案只明确列出了 /docs 和 /static，其余期望路由均未提及；/app 与 /rag 虽在语料中存在但不在期望 |
| Q2 | 3/4 | 1 | 否 | 答案明确给出 docs_url=None、自定义 /docs 用 get_swagger_ui_html 指向本地 js |
| Q3 | 0/4 | 1,2,3,4 | 否 | 答案明确表示语料未给出 SEEDS 具体值，因此四个要点均未命中；但语料摘录中 store.py 实际包含 SEEDS  |
| Q4 | 3/3 | - | 否 | 答案明确给出 400 与 detail、strip 判空抛 HTTPException(400)、以及 422 仅用于  |
| Q5 | 4/4 | - | 否 | 答案明确列出四个期望的包及版本，与语料摘录完全一致；额外列出的 chromadb、fastembed、mcp 也在摘录中 |
| Q6 | 3/4 | 3 | 否 | 要点1、2、4命中；要点3未命中，答案错误否认 steps 字段存在，但该断言与语料直接矛盾，应记入 hallucina |
| Q7 | 0/4 | 1,2,3,4 | 是 | 答案对 FastAPI 数据层与接口细节大量声称『资料中没有』，但语料摘录实际包含 store.py 完整实现及 /ap |
| Q8 | 2/3 | 3 | 否 | 答案明确指出拼写错误并给出正确写法 startsWith()，也说明资料中方法名拼写有误（笔误），但未给出 str.st |
| Q9 | 3/4 | 4 | 否 | 答案明确指出表只有 id/name/completed 三列、无用户字段与鉴权、所有请求共用同一份列表故不支持多用户；但 |
| Q10 | 1/4 | 2,3,4 | 否 | 答案仅命中模型名 deepseek-chat；base_url、key 来源与缺失行为均称资料中没有，故未命中，且与语料 |
| Q11 | 4/4 | - | 否 | 答案完整覆盖了 RAG_K 环境变量默认 8、1..10 校验返回 400、is None 与 or 对 k=0 的区别 |
| Q12 | 4/4 | - | 否 | 答案准确覆盖了三种失败情况的返回码（503/503/502）以及 retrieve 同步、用 run_in_thread |
| Q13 | 5/5 | - | 否 | 答案明确覆盖了 max_steps=5、优先正则匹配 Final Answer、Action/Action Input  |
| Q14 | 4/4 | - | 否 | 答案明确覆盖了四个要点：/agent 用 tools+tool_choice=auto 由模型决定、/agent-raw |
| Q15 | 2/4 | 1,4 | 否 | 答案明确提到 SELECT 1 FROM todos LIMIT 1 判空和仅空表插种子，但未确认 CREATE TAB |
| Q16 | 4/5 | 5 | 否 | 答案明确命中 db_path 用 TODO_DB、默认 BASE_DIR/todos.db、row_factory=sq |
| Q17 | 0/5 | 1,2,3,4,5 | 是 | 答案未命中任何期望要点，且错误声称 Express 无 DELETE 路由、FastAPI DELETE 状态码被截断， |
| Q18 | 5/5 | - | 否 | 答案明确覆盖了 completed 布尔校验返回 400、changes===0 返回 404、更新后 SELECT 返 |
| Q19 | 3/4 | 4 | 否 | 依赖、start/dev、test 占位均明确命中；main 为 index.js 与实际入口 server.js 的对 |
| Q20 | 4/4 | - | 否 | 答案完整列出了四组依赖及版本号，正确标注了 RAG 可选依赖（chromadb、fastembed）、MCP 依赖（mc |
| Q21 | 3/5 | 2,5 | 否 | 答案命中 /chat 流式 SSE、/rag 非流式结构化 JSON 与 run_in_threadpool，但未提 / |
| Q22 | 5/5 | - | 否 | 答案明确覆盖了全部五个要点：http 模块、express、端口 3000、text/plain 的 Hello Wor |
| Q23 | 4/5 | 5 | 否 | sort 默认按字符串 Unicode 码点排序、sort 与 reverse 改原数组、slice 返回新数组不改原数 |
| Q24 | 4/5 | 2 | 否 | 答案明确命中 *toppings 收成元组、get 避免 KeyError、w 清空/a 追加、json.dump/lo |
| Q25 | 0/3 | 1,2,3 | 否 | 答案明确表示资料未说明 sort/sorted 的行为差异及切片语义，三个要点均未表达，故全部未命中。 |
| Q26 | 4/4 | - | 否 | 答案明确覆盖了 * 选择器的 font-family 与 text-align、h1 颜色 rgb(170,170,18 |
| Q27 | 2/4 | 3,4 | 否 | 答案正确列出顶层字段和 members 字段，但未提及 formed 为 2016，也未说明 powers 是字符串数组 |
| Q28 | 4/4 | - | 否 | 答案明确说明语料无登录/鉴权实现，仅提及 CORS origin 限制，指出无 token/session/密码相关代码 |
| Q29 | 3/3 | - | 否 | 答案明确说明资料未提及作者和出处，符合语料仅有诗文、无标注且应拒答的要求。 |
| Q30 | 3/4 | 4 | 否 | 答案明确说明每次操作新建连接、无 WAL/busy_timeout、无重试或锁处理，但未指出只适合单用户 demo 或  |
| Q31 | 4/4 | - | 否 | 答案明确给出 days 默认 7、范围 1..90 否则 400、返回 obs.summarize(days)，并说明  |
| Q32 | 2/3 | 3 | 否 | 默认值 1 和范围 0..2（否则 400）均明确命中；答案明确表示资料未说明 0 的语义，按规则判为未命中，且未编造实 |
| Q33 | 3/4 | 3 | 否 | 答案明确给出先追加带 tool_calls 的 assistant 消息、再追加 role=tool 带 tool_ca |
| Q34 | 4/4 | - | 否 | 答案明确覆盖了 SQLite 存 0/1、FastAPI 用 bool()、Express 用 ===1、PATCH 写 |
| Q35 | 3/4 | 4 | 否 | 答案明确说明 req.body 无值、POST 返回 400、PATCH 返回 400，但未提及 Express 5 不 |
| Q36 | 3/4 | 4 | 否 | 答案明确给出 Express 的 cors 配置、指出 FastAPI 语料无 CORS、并得出两边不对称的结论；但未提 |
| Q37 | 4/4 | - | 否 | 答案完整列出五个字段、distance 四舍五入 4 位、preview 取第二行前 160 字符，并说明响应含 k 与 |
| Q38 | 4/4 | - | 否 | 答案明确指出 strip 删两端空白而非仅空格、rstrip 只删右端、不是删空行，并称该说法不严谨/有误导，四个要点均 |
| Q39 | 3/4 | 3 | 否 | 答案明确说没有测试文件、没有 CI 配置、没有测试流程说明，但未提及 package.json 中 test 脚本是 e |
| Q40 | 5/5 | - | 否 | 答案明确覆盖了表结构一致、种子第三条不同、completed 0/1 转换、相对路径依赖工作目录、并发写可能 datab |
