# evals —— 本 skill 的对照实验

> 目的不是"证明 skill 有用"，而是**让它可以被证伪**。
> 每个数字都能被别人用同一条命令重跑。

## 1. 实验设计（一句话）

6 个臂，同 7 道题、同一模型、同一温度、同一题面对打：

| 臂 | 做法 | 作用 |
|---|---|---|
| `A0` | 裸题面，1 次调用 | 基线 |
| `A1` | 4 个专业身份各出 1 份 | **常见做法**：换身份 |
| `A2` | 1 次调用要求 4 条不同做法 | **常见做法**：一句话多角度 |
| `A3` | **本 skill**：测绘决策点 → 签路径 → 分头走 → 核对合流 | 被检验的设计 |
| `A3c` | 分支由外部预注册轴给定 | 本设计的上界（分支质量是瓶颈吗） |
| `A4` | 分支由**任务无关维度**给定 | **H0 臂**：杀死"只是结构有效" |

三道关键检验：
1. **H0 臂 A4**——若 `A3 ≈ A4`，说明有效的只是"分支结构"，与任务相关无关。
2. **负对照题 T7**（路径唯一）——若 `A3` 在 T7 上也展得很宽，那它测的是噪声，不是思维面。
3. **兑现率**——宽度与有效性必须并排报，否则"一派胡言"也能拿高分。

## 2. 怎么跑

```bash
cd evals/harness
python3 -m venv .venv && .venv/bin/pip install scikit-learn
.venv/bin/python check_topics.py          # 泄题闸门（必须全绿）
.venv/bin/python test_metrics.py          # 指标变异注入自检（必须全绿）
.venv/bin/python run.py --out runs/x --reps 3 --workers 16
.venv/bin/python run_skl_ideas.py runs/x  # A2 的逐条思路骨架
.venv/bin/python health.py runs/x         # 判官健康度（换模型重跑抽样）
.venv/bin/python analyze.py runs/x        # 读数表 + 执行预注册判决线
```

## 3. 判定规则（事前写死，公式型）

见 `evals/harness/prereg.md` §5。一句话：
> X 优于 Y ⟺ 各题均值差 > 0 **且** ≥2/3 题同向 **且** ≥2/3 题上差值超过该题的跨 rep 噪声地板。

## 4. 结果

见 `evals/RESULTS.md`。

## 5. 已知的坑

- 跑批前先看 `runs/<dir>/manifest.json` 的 `expected`，收尾核对 `integrity.json`——**半截产物和完整产物长得一模一样**。
- A2 一次调用出 4 条思路，**总输出量远少于 4 次调用的臂**：任何"更宽"的结论都必须连着成本一起看。
- MiniMax 的思考 token 会吃光 `max_tokens` 导致输出为空——`client.py` 把这种情况记成失败并显式重试，不静默归零。
