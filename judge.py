#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ judge.py —— 出表（★ 主尺＝连续覆盖、★ 辅尺＝命中数、★ 配对比较 ★）

★ ★ 口径（★ 事前定死、★ 见 PREREG.md ★）★★
★   **主尺 = 连续覆盖**：★ 对每题的每条金标 C、★ 算「C 的关键 token 有多少出现在该臂的结论集里」★
★     （★ 分母＝C 全文的 token、★ 分子＝与该臂结论集的交集、★ 再对 C 取均值 ★）★★
★     ⇒ ★ 为什么不用【命中数】当主尺：★ 金标 C 是【整段命题】（★ 含型号/接口/数值等细节 ★）★
★       ⇒ ★ 「命中」要求 60% token 全中、★ 太严 ⇒ ★ 实测多数臂在多数题上命中数为 0 ★
★       ⇒ ★ **命中数只作辅尺**（★ 它是 L0 那套的原始口径、★ 保留以便对他们的读数 ★）★★
★   **辅尺 = 命中数**（★ L0/run_l0.py 的 coarse_cover 原样口径 ★）
★   **缺席率 = 1 − 连续覆盖**（★ 「有多少金标维度压根没被说到」★）
"""
import json, pathlib, statistics as st, sys
from itertools import combinations

HERE = pathlib.Path(__file__).resolve().parent
# ★ out 目录：★ 本目录优先、★ 上一级回落（★ 解压后 code/ 与 out/ 同级 ★）
_OUT_CANDIDATES = [HERE / "out", HERE.parent / "out"]
OUT = next((c for c in _OUT_CANDIDATES if c.exists()), _OUT_CANDIDATES[0])

ARM_NAME = {
    "direct": "直调（1 次）",
    "bestof3": "等预算对照（3 次独立直调）",
    "w_layer2": "③组工作流 · 层2（固定动作集）",
    "w_layer3": "③组工作流 · 层3（动作空间演化）",
    "l0_expand": "L0 Agent（自主建问题空间）",
    "skill_v1": "thinking-surface v1.1",
    "skill_v3": "thinking-surface v3",
}
ARMS = list(ARM_NAME)


def cont_cov(per_c):
    """★ 连续覆盖 = 各 C 的 token 覆盖率的均值（★ 无命中阈值 ★）"""
    if not per_c:
        return None
    vals = [v.get("cov", 0.0) for v in per_c.values()]
    return sum(vals) / len(vals)


def boot_ci(xs, iters=10000, seed=20261029):
    if not xs:
        return (float("nan"), float("nan"))
    import random
    rnd = random.Random(seed)
    n = len(xs)
    meds = []
    for _ in range(iters):
        meds.append(st.median([xs[rnd.randrange(n)] for _ in range(n)]))
    meds.sort()
    return (meds[int(0.025 * iters)], meds[int(0.975 * iters)])


def main(tag="ab1"):
    p = OUT / ("units_%s.jsonl" % tag)
    if not p.exists():
        print("★ 没有 %s" % p)
        return 1
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    ok = [r for r in rows if r.get("ok")]
    for r in ok:
        r["_cov_cont"] = cont_cov(r.get("per_conclusion"))
        r["_hit_rate"] = (r.get("n_hit") / r["n_gold"]) if r.get("n_gold") else None
    agg = {}
    for arm in ARMS:
        rs = [r for r in ok if r["arm"] == arm]
        if not rs:
            continue
        agg[arm] = {
            "n": len(rs),
            "cov_cont": round(sum(r["_cov_cont"] for r in rs) / len(rs), 4),
            "hit_rate": round(sum(r["_hit_rate"] for r in rs if r["_hit_rate"] is not None) /
                              len([r for r in rs if r["_hit_rate"] is not None]), 4),
            "absence": round(1 - sum(r["_cov_cont"] for r in rs) / len(rs), 4),
            "n_claims": round(sum(r.get("n_claims", 0) for r in rs) / len(rs), 1),
            "calls": round(sum(r["calls"]["n_calls"] for r in rs) / len(rs), 1),
            "calls_fail": sum(r["calls"]["n_fail"] for r in rs),
            "tokens": int(sum(r["calls"]["tokens"] for r in rs) / len(rs)),
            "wall": round(sum(r["wall_s"] for r in rs) / len(rs), 1),
        }

    # ★ 配对比较（★ 同题同 rep ★）
    idx = {(r["arm"], r["task_id"], r["rep"]): r for r in ok}
    comps = {}
    for arm in ARMS:
        if arm == "direct":
            continue
        diffs, hits = [], []
        for (a, tid, rep), r in sorted(idx.items()):
            if a != arm:
                continue
            b = idx.get(("direct", tid, rep))
            if not b:
                continue
            diffs.append(r["_cov_cont"] - b["_cov_cont"])
            hits.append((r.get("n_hit") or 0) - (b.get("n_hit") or 0))
        if diffs:
            lo, hi = boot_ci(diffs)
            comps["%s vs direct" % arm] = {
                "n": len(diffs), "median_d": round(st.median(diffs), 4),
                "mean_d": round(sum(diffs) / len(diffs), 4), "ci95": [lo, hi],
                "pos": sum(1 for d in diffs if d > 1e-9), "zero": sum(1 for d in diffs if abs(d) <= 1e-9),
                "neg": sum(1 for d in diffs if d < -1e-9),
                "hit_pos": sum(1 for d in hits if d > 0), "hit_neg": sum(1 for d in hits if d < 0),
                "hit_zero": sum(1 for d in hits if d == 0),
            }

    res = {"tag": tag, "n_rows": len(rows), "n_ok": len(ok), "n_fail": len(rows) - len(ok),
           "agg": agg, "comps": comps}
    (OUT / ("results_%s.json" % tag)).write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

    L = ["# 结果表 · 七臂同量纲对照（★ 工作流 ＋ skill ＋ 直调 ★）\n",
         "> 任务：③组 D01–D09（★ 规则应用题 ＋ 每题自带 conclusion_space 作金标 ★）｜ 模型：MiniMax-M3（关推理）",
         "> 主尺 = 连续覆盖（★ 每条金标 C 的 token 覆盖率的均值 ★）｜ 辅尺 = 命中数（L0 原口径）\n",
         "## 0 · 通道健康度\n", "| 项 | 值 |\n|---|---|",
         "| 单元 | %d（成功 %d、失败 %d）|" % (len(rows), len(ok), len(rows) - len(ok)),
         "| 调用失败总数 | %d |" % sum(r["calls"]["n_fail"] for r in ok),
         "", "## 1 · 主表\n",
         "| 臂 | n | **连续覆盖** | 命中率(辅) | 缺席率 | 结论条数 | 调用 | 调用失败 | token | 秒 |",
         "|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|"]
    for arm in ARMS:
        a = agg.get(arm)
        if not a:
            continue
        L.append("| **%s** %s | %d | **%.4f** | %.4f | %.4f | %.1f | %.1f | %d | %d | %.0f |"
                 % (arm, ARM_NAME[arm], a["n"], a["cov_cont"], a["hit_rate"], a["absence"],
                    a["n_claims"], a["calls"], a["calls_fail"], a["tokens"], a["wall"]))
    L += ["", "## 2 · 配对比较（★ 同题同 rep、★ 对照 = direct ★）\n",
          "| 对比 | n 对 | 差值中位数 | 差值均值 | bootstrap 95% CI | 同向 | 持平 | 反向 | 命中数 同向/持平/反向 |",
          "|---|--:|--:|--:|---|--:|--:|--:|--:|"]
    for k, c in comps.items():
        L.append("| %s | %d | **%+.4f** | %+.4f | [%+.4f, %+.4f] | %d | %d | %d | %d/%d/%d |"
                 % (k, c["n"], c["median_d"], c["mean_d"], c["ci95"][0], c["ci95"][1],
                    c["pos"], c["zero"], c["neg"], c["hit_pos"], c["hit_zero"], c["hit_neg"]))
    L += ["", "## 3 · 逐题（★ 连续覆盖 · 每题 n=rep 数 ★）\n", "| 题 | " + " | ".join(ARMS) + " |",
          "|---|" + "---|" * len(ARMS)]
    tasks = sorted(set(r["task_id"] for r in ok))
    for tid in tasks:
        cells = []
        for arm in ARMS:
            rs = [r["_cov_cont"] for r in ok if r["arm"] == arm and r["task_id"] == tid]
            cells.append("%.3f" % (sum(rs) / len(rs)) if rs else "-")
        L.append("| %s | %s |" % (tid, " | ".join(cells)))
    L += ["", "## 4 · 题内噪声地板（★ 同臂同题不同 rep 的 σ · ★ 判决线锚它 ★）\n",
          "| 题 | 各臂 rep 间 σ（连续覆盖） |", "|---|---|"]
    for tid in tasks:
        sig = []
        for arm in ARMS:
            rs = [r["_cov_cont"] for r in ok if r["arm"] == arm and r["task_id"] == tid]
            if len(rs) >= 2:
                sig.append(st.pstdev(rs))
        L.append("| %s | %s |" % (tid, ("%.4f" % (sum(sig) / len(sig))) if sig else "-"))
    (OUT / ("results_%s.md" % tag)).write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "ab1"))
