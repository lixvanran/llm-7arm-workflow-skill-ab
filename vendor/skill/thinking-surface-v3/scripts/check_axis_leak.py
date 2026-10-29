#!/usr/bin/env python3
"""轴库泄题闸门 v2：拿"金标评分词"当尺子，量轴库有多接近答案。

背景（真实事件，不是假想）：
    v3 轴库最初是我**看着 v2 题集**写的 ⇒ "食堂"(T9)、"取件码"(T11)、
    "不会用手机"(T10 金标轴原话) 混进了库。
    ⇒ A7 臂（工具选轴）等于偷看了答案，它与 A6 的对比**无效**。

判据（可机械判定，不靠自觉）：
    1) **硬泄漏**：轴库词条命中某题的 `must`/`forbid` 评分词，而该词**不在题面**里
       ⇒ 库把答案的词汇递给了臂 ⇒ 必须修（改词或换轴）。
    2) **答案覆盖率**（不是红绿，是连续量）：
       对每题，统计"该题金标轴的 must 词里，有多少能被轴库词汇命中"，
       记作 cover(t)。
       cover 高 ⇒ 这题的答案本身就是通用设计维度 ⇒ 任何通用词库都会撞上
       ⇒ 该题**不能**用来判断"工具选轴 vs 模型自选轴"。
    3) 题面里出现过的词**不算泄漏**（工具本来就能看见任务），
       但仍会被记成"题面命中"以供对照。

用法：
    python3 check_axis_leak.py            # 报告 + 退出码（0=无硬泄漏）
    python3 check_axis_leak.py --json     # 机器可读
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import axis_picker  # noqa: E402


def load_topics(path: Path):
    """自带 loader（不依赖 harness 目录 ⇒ 脚本在 skill 里也自包含）。"""
    import json as _json
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(_json.loads(line))
    return out


def find_topics(explicit: str = "") -> Path:
    """按 显式参数 > 脚本向上搜索 > cwd 的顺序找题集文件。"""
    if explicit:
        p = Path(explicit)
        if p.exists():
            return p
    here = Path(__file__).resolve().parent
    for base in [here, *here.parents][:6]:
        cand = base / "topics_v2.jsonl"
        if cand.exists():
            return cand
        cand2 = base / "evals" / "harness" / "topics_v2.jsonl"
        if cand2.exists():
            return cand2
        cand3 = base / "lab" / "topics_v2.jsonl"          # 源码树：同级 lab
        if cand3.exists():
            return cand3
        for sub in base.glob("*/evals/harness/topics_v2.jsonl"):   # 包内：兄弟 skill 目录
            return sub
    cwd = Path.cwd() / "topics_v2.jsonl"
    if cwd.exists():
        return cwd
    raise SystemExit("找不到 topics_v2.jsonl（用 --topics 指定）")


def library_terms():
    """轴库所有词条：(轴 id, 字段, 词)"""
    out = []
    for aid, ax in axis_picker.AXES.items():
        out.append((aid, "name", ax["name"]))
        for e in ax["examples"]:
            out.append((aid, "examples", e))
    for aid, kw in axis_picker.KEYWORDS.items():
        for w in kw.split():
            out.append((aid, "keywords", w))
    return out


def _norm(s):
    return re.sub(r"\s+", "", s or "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topics", default="")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    topics = load_topics(find_topics(args.topics))
    terms = library_terms()
    # 轴库词条 → 归一化后的词
    lib_words = {}
    for aid, field, t in terms:
        w = _norm(t)
        if len(w) >= 2:
            lib_words.setdefault(w, []).append((aid, field))

    report = {"hard_leaks": [], "per_topic": {}}
    # 子串匹配：库里的词**包含**金标词也算漏（"预约时间" 含 "预约"）
    for t in topics:
        text_blob = _norm(t.get("title", "") + t.get("prompt", ""))
        must, forbid = [], []
        for a in t.get("axes", []):
            must += [m for m in (a.get("must") or [])]
            forbid += [f for f in (a.get("forbid") or [])]
        must, forbid = set(must), set(forbid)
        gold_words = must | forbid
        in_text, covered = [], []
        for w in gold_words:
            hits = []
            for lib_w, srcs in lib_words.items():
                if w in lib_w:          # 库词包含金标词
                    hits += [f"{a}:{f}({lib_w})" for a, f in srcs]
            if not hits:
                continue
            if w in text_blob:
                in_text.append(w)
            else:
                covered.append(w)
                report["hard_leaks"].append({
                    "topic": t["id"], "word": w, "in": sorted(set(hits)),
                })
        n_gold = max(len(gold_words), 1)
        report["per_topic"][t["id"]] = {
            "title": t.get("title"),
            "gold_words": sorted(gold_words),
            "covered_by_library": sorted(covered),
            "visible_in_prompt": sorted(in_text),
            "cover": round(len(covered) / n_gold, 3),
            "cover_incl_text": round((len(covered) + len(in_text)) / n_gold, 3),
        }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 1 if report["hard_leaks"] else 0

    print("=== 硬泄漏（库里的词＝金标评分词，且该词不在题面里）===")
    if not report["hard_leaks"]:
        print("  无")
    else:
        for h in report["hard_leaks"]:
            print(f"  {h['topic']:4s} 「{h['word']}」  出现在轴库: {', '.join(h['in'])}")

    print("\n=== 每题的『答案覆盖率』cover = 库能命中的金标词 / 全部金标词 ===")
    print("  （cover 低 ⇒ 通用词库给不出这题的答案 ⇒ 该题可用于判断『工具 vs 模型自选』）")
    for tid, r in sorted(report["per_topic"].items()):
        flag = "  ⚠️ 库≈答案 ⇒ 不可用于 A7 对比" if r["cover"] >= 0.30 else "  ✓ 可用"
        print(f"  {tid:4s} cover={r['cover']:.2f}  题面可见={r['visible_in_prompt'] or '—'}{flag}")
    return 1 if report["hard_leaks"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
