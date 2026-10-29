#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ check_report.py —— 把【报告里的每一个数字】回源到跑批产出逐格核对 ★
★ ★ 纪律：★ 交付物的数字必须能被独立复算；★ 这就是那个复算器 ★
★ ★ 纪律：★ 写入器 ≠ 检查器 ⇒ ★ 本脚本【只读】报告与 out/、★ 不写任何东西 ★★
"""
import json, pathlib, re, statistics as st, sys, random

HERE = pathlib.Path(__file__).resolve().parent
REPORT = HERE / "七臂同量纲对照_工作流_vs_skill_2026-10-29.md"
ARMS = ["direct", "bestof3", "w_layer2", "w_layer3", "l0_expand", "skill_v1", "skill_v3"]
ARMLABEL = {"direct": "直调", "bestof3": "等预算对照", "w_layer2": "工作流·层2", "w_layer3": "工作流·层3",
            "l0_expand": "L0 Agent", "skill_v1": "v1.1", "skill_v3": "v3"}
FAILS = []


def cont(pc):
    v = [x.get("cov", 0.0) for x in pc.values()]
    return sum(v) / len(v) if v else 0.0


def load(tag):
    rows = [json.loads(l) for l in (HERE / ("out/units_%s.jsonl" % tag)).read_text(encoding="utf-8").splitlines() if l.strip()]
    ok = [r for r in rows if r.get("ok")]
    for r in ok:
        r["_c"] = cont(r.get("per_conclusion"))
    return rows, ok


def boot(xs, iters=10000, seed=20261029):
    rnd = random.Random(seed); n = len(xs); m = []
    for _ in range(iters):
        m.append(st.median([xs[rnd.randrange(n)] for _ in range(n)]))
    m.sort()
    return m[int(.025 * iters)], m[int(.975 * iters)]


def cell(txt):
    return txt.strip().strip("*").replace("**", "")


def main():
    rows2, ok2 = load("ab2")
    rows1, ok1 = load("ab1")
    rep = REPORT.read_text(encoding="utf-8")
    lines = rep.splitlines()

    # ── ① 主表（第 4 节）──
    print("① 主表逐格回源")
    main_tbl = []
    grab = False
    for ln in lines:
        if ln.startswith("## 4 · 主表"):
            grab = True; continue
        if grab and ln.startswith("## 5"):
            break
        if grab and ln.startswith("| ") and "---" not in ln:
            c = [x for x in ln.strip().strip("|").split("|")]
            main_tbl.append(c)
    for row in main_tbl:
        arm = next((a for a in ARMS if ARMLABEL[a] in row[0]), None)
        if arm is None:
            continue
        rs = [r for r in ok2 if r["arm"] == arm]
        cov = sum(r["_c"] for r in rs) / len(rs)
        hit = sum((r.get("n_hit") or 0) / r["n_gold"] for r in rs if r.get("n_gold")) / len([r for r in rs if r.get("n_gold")])
        claims = sum(r["n_claims"] for r in rs) / len(rs)
        calls = sum(r["calls"]["n_calls"] for r in rs) / len(rs)
        tok = int(sum(r["calls"]["tokens"] for r in rs) / len(rs))
        n_all = len([r for r in rows2 if r["arm"] == arm])
        n_fail = n_all - len(rs)
        checks = [("覆盖", cell(row[2]), "%.4f" % cov), ("命中率", cell(row[3]), "%.4f" % hit),
                  ("缺席率", cell(row[4]), "%.4f" % (1 - cov)), ("结论条", cell(row[5]), "%.1f" % claims),
                  ("调用", cell(row[6]), "%.1f" % calls), ("调用失败", cell(row[7]), "%d" % sum(r["calls"]["n_fail"] for r in rs)),
                  ("token", cell(row[8]), "%d" % tok)]
        for name, got, exp in checks:
            if got != exp:
                FAILS.append("主表 %s %s：报告 %s ≠ 复算 %s" % (arm, name, got, exp))
        print("   %-11s 覆盖 报告 %s / 复算 %.4f %s" % (arm, cell(row[2]), cov, "✔" if cell(row[2]) == "%.4f" % cov else "★"))

    # ── ② 配对比较（第 5.1 / 5.2 节）──
    print("② 配对比较逐格回源")
    idx = {(r["arm"], r["task_id"], r["rep"]): r for r in ok2}
    pair_rows = []
    grab = False
    for ln in lines:
        if ln.startswith("## 5 · 配对比较"):
            grab = True; continue
        if grab and ln.startswith("## 6"):
            break
        if grab and ln.startswith("| ") and "---" not in ln:
            pair_rows.append([x for x in ln.strip().strip("|").split("|")])
    n_checked = 0
    for row in pair_rows:
        m = re.match(r"\s*(\w+) vs (\w+)\s*$", cell(row[0]))
        if not m:
            continue
        a, b = m.group(1), m.group(2)
        d = []
        for (arm, tid, rep_), r in idx.items():
            if arm != a:
                continue
            o = idx.get((b, tid, rep_))
            if o:
                d.append(r["_c"] - o["_c"])
        if not d:
            continue
        lo, hi = boot(d)
        exp_med = ("%+.4f" % st.median(d))
        if cell(row[2]) != exp_med:
            FAILS.append("配对 %s vs %s 中位差：报告 %s ≠ 复算 %s" % (a, b, cell(row[2]), exp_med))
        npos = sum(1 for x in d if x > 1e-9); nneg = sum(1 for x in d if x < -1e-9)
        if cell(row[4]) != "%d/%d" % (npos, nneg):
            FAILS.append("配对 %s vs %s 同向/反向：报告 %s ≠ 复算 %d/%d" % (a, b, cell(row[4]), npos, nneg))
        ci = re.match(r"\[([+\-0-9.]+),\s*([+\-0-9.]+)\]", cell(row[3]))
        if ci and (abs(float(ci.group(1)) - lo) > 0.0006 or abs(float(ci.group(2)) - hi) > 0.0006):
            FAILS.append("配对 %s vs %s CI：报告 %s ≠ 复算 [%.4f, %.4f]" % (a, b, cell(row[3]), lo, hi))
        n_checked += 1
    print("   核对 %d 条配对（★ 中位差 / CI / 同向-反向 三项 ★）" % n_checked)

    # ── ③ 两遍对照（第 3 节）──
    print("③ 两遍对照回源")
    for a in ARMS:
        o1 = sum(r["_c"] for r in ok1 if r["arm"] == a) / len([r for r in ok1 if r["arm"] == a])
        o2 = sum(r["_c"] for r in ok2 if r["arm"] == a) / len([r for r in ok2 if r["arm"] == a])
        m = re.search(r"\| %s \| ([\d.]+) \| ([\d.]+) \|" % re.escape(a), rep)
        if not m:
            FAILS.append("两遍对照缺 %s" % a); continue
        if m.group(1) != "%.4f" % o1 or m.group(2) != "%.4f" % o2:
            FAILS.append("两遍对照 %s：报告 %s/%s ≠ 复算 %.4f/%.4f" % (a, m.group(1), m.group(2), o1, o2))
    print("   七臂两遍覆盖逐条核完")

    # ── ④ 逐题表（第 6 节）──
    print("④ 逐题表回源")
    grab = False; pt = []
    for ln in lines:
        if ln.startswith("## 6 · 逐题"):
            grab = True; continue
        if grab and ln.startswith("## 7"):
            break
        if grab and ln.startswith("| D0"):
            pt.append([x for x in ln.strip().strip("|").split("|")])
    for row in pt:
        tid = cell(row[0])
        for j, a in enumerate(ARMS):
            v = [r["_c"] for r in ok2 if r["arm"] == a and r["task_id"] == tid]
            exp = "%.3f" % (sum(v) / len(v)) if v else "-"
            if cell(row[j + 1]) != exp:
                FAILS.append("逐题 %s %s：报告 %s ≠ 复算 %s" % (tid, a, cell(row[j + 1]), exp))
    print("   %d 题 × %d 臂 = %d 格全核" % (len(pt), len(ARMS), len(pt) * len(ARMS)))

    # ── ⑤ 成本对齐（第 7 节）──
    print("⑤ 成本对齐回源")
    grab = False; ct = []
    for ln in lines:
        if ln.startswith("## 7 · 成本对齐"):
            grab = True; continue
        if grab and ln.startswith("## 8"):
            break
        if grab and ln.startswith("| ") and "---" not in ln:
            ct.append([x for x in ln.strip().strip("|").split("|")])
    for row in ct:
        arm = next((a for a in ARMS if ARMLABEL[a] in row[0] or row[0].strip().startswith(a)), None)
        if arm is None:
            continue
        rs = [r for r in ok2 if r["arm"] == arm]
        cov = sum(r["_c"] for r in rs) / len(rs)
        tok = sum(r["calls"]["tokens"] for r in rs) / len(rs)
        wall = sum(r["wall_s"] for r in rs) / len(rs)
        for name, got, exp in [("覆盖", cell(row[1]), "%.4f" % cov),
                               ("token", cell(row[2]), "%d" % int(tok)),
                               ("覆盖/千tok", cell(row[3]), "%.3f" % (cov * 1000 / tok)),
                               ("秒", cell(row[4]), "%.1f" % wall),
                               ("覆盖/千秒", cell(row[5]), "%.1f" % (cov * 1000 / wall))]:
            if got != exp:
                FAILS.append("成本表 %s %s：报告 %s ≠ 复算 %s" % (arm, name, got, exp))
    print("   七臂成本五项逐格核完")

    # ── ⑥ 噪声地板（第 2 节引用）──
    print("⑥ 噪声地板回源")
    sigs = []
    for tid in sorted(set(r["task_id"] for r in ok2)):
        s = []
        for a in ARMS:
            v = [r["_c"] for r in ok2 if r["arm"] == a and r["task_id"] == tid]
            if len(v) >= 2:
                s.append(st.pstdev(v))
        if s:
            sigs.append((tid, sum(s) / len(s)))
    mean_sig = sum(x[1] for x in sigs) / len(sigs); max_sig = max(x[1] for x in sigs)
    for name, exp in [("σ 均值", "%.4f" % mean_sig), ("σ 最大", "%.4f" % max_sig)]:
        if exp not in rep:
            FAILS.append("噪声地板 %s 复算 %s 未出现在报告里" % (name, exp))
    print("   σ 均值 %.4f ｜ σ 最大 %.4f （★ 报告里都有 ★）" % (mean_sig, max_sig))

    # ── ⑦ 装饰符号 ──
    print("⑦ 装饰符号")
    for f in ["七臂同量纲对照_工作流_vs_skill_2026-10-29.md", "PREREG.md", "out/results_ab2.md"]:
        s = (HERE / f).read_text(encoding="utf-8")
        n = s.count("★") + s.count("⇒")
        if n:
            FAILS.append("%s 残留装饰符号 %d 个" % (f, n))
        print("   %-46s 残留 %d" % (f, n))

    print()
    if FAILS:
        print("★ 不一致 %d 条：" % len(FAILS))
        for f in FAILS[:40]:
            print("   -", f)
        return 1
    print("✔ 报告全量回源核对通过（★ 主表 / 配对 / 两遍 / 逐题 / 成本 / 地板 / 装饰符号 ★）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
