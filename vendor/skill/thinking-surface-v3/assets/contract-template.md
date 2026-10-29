# 路径合约（Contract）模板

> 用法：复制本文件，填完，作为生成阶段的输入；生成完作为审计阶段的输入。
> **签名必须在生成前写死。** 生成后补的签名一律作废。

```json
{
  "task": "<任务原文>",
  "fork_map": [
    {
      "decision": "<决策点名称>",
      "real_fork": true,
      "branches": [
        {"brief": "<具体怎么做，1-2句>", "why_different": "<与另一支的差别：机制/代价/受益者>"}
      ]
    }
  ],
  "paths": [
    {
      "id": "p1",
      "label": "<路线名>",
      "brief": "<这条路线的具体做法>",
      "signature": ["<具体可观察要点1>", "<具体可观察要点2>"],
      "anti_signature": ["<这条路上不该出现的东西>"],
      "cost": "<这条路牺牲什么 / 谁会不满意>",
      "covers": ["<它给了不同答案的决策点 id>"]
    }
  ],
  "notes": "<测绘过程中的判断，比如某处是伪分叉、某处路径唯一>"
}
```

## 填写纪律

1. **fork_map 里的每个 decision 至少两个分支**，且至少有一个是**真分叉**。
2. **paths 里的 signature 必须是名词或动作**，不许写"重视/认真/创新/用心"这类空话。
3. **anti_signature 要写别的路径的标志**，不是"不能说的话"。
4. **cost 必填**。写不出代价 ⇒ 这条路径不成立，删掉。
5. **covers 要填**：这条路径在哪些决策点与别人不同。没有 covers 的路径是多余的。

## 交回审计时

生成完，把每条路径的产出按 `path_id` 存成 `outputs.jsonl`（每行 `{"path_id":"p1","text":"..."}`），
然后跑：

```bash
python3 scripts/audit_signatures.py --contract contract.json --outputs outputs.jsonl
```

退出码：`0` 全部兑现｜`1` 有未兑现｜`2` 输入或运行错误。
