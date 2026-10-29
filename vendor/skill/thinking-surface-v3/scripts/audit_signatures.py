#!/usr/bin/env python3
"""签名兑现审计（纯标准库，无第三方依赖）。

用法：
    python3 audit_signatures.py --contract contract.json --outputs outputs.jsonl
    python3 audit_signatures.py --contract contract.json --dir outputs/   # 文件名=路径id.txt

输入
  contract.json:
    {"paths":[{"id":"p1","label":"...","signature":["按成本加成倒推","免费额度"],
               "anti_signature":["成本结构分析"],"cost":"..."}]}
    签名项可用 "A/B" 表示「命中 A 或 B 即可」。
  outputs.jsonl: 每行 {"path_id":"p1","text":"..."}

输出（stdout，JSON）
  {"paths":[{"id":"p1","hit":true,"sig_hit":[...],"sig_missing":[...],"anti_hit":[...]}],
   "fulfillment":0.75,"n":4}

退出码：0 全部兑现 / 1 有未兑现 / 2 输入错误
（退出码三态：不许把「未兑现」和「跑挂了」混成同一个 0）
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

HIT_RATIO = 2 / 3  # 与实验口径一致：签名条数的 2/3


def alternatives(item) -> list[str]:
    if isinstance(item, str):
        parts = [p.strip() for p in item.split("/")]
        return [p for p in parts if p]
    if isinstance(item, list):
        out = []
        for x in item:
            out.extend(alternatives(x))
        return out
    return []


def match(item, text: str) -> bool:
    return any(alt and alt in text for alt in alternatives(item))


def audit(contract: dict, outputs: dict) -> dict:
    paths = contract.get("paths") or []
    results = []
    n_hit = 0
    for p in paths:
        pid = p.get("id")
        text = outputs.get(pid, "")
        sig = p.get("signature") or []
        anti = p.get("anti_signature") or []
        hit_items = [s for s in sig if match(s, text)]
        miss_items = [s for s in sig if not match(s, text)]
        anti_hit = [s for s in anti if match(s, text)]
        need = math.ceil(len(sig) * HIT_RATIO) if sig else 0
        ok = (len(hit_items) >= need) and (len(anti_hit) == 0)
        n_hit += int(ok)
        results.append({
            "id": pid, "label": p.get("label"), "hit": ok,
            "need": need,
            "sig_hit": hit_items, "sig_missing": miss_items, "anti_hit": anti_hit,
            "chars": len(text),
            "cost": p.get("cost"),
        })
    n = len(paths)
    return {
        "paths": results,
        "fulfillment": (n_hit / n) if n else None,
        "n": n,
        "n_hit": n_hit,
        "missing_output": [r["id"] for r in results if r["chars"] == 0],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", required=True)
    ap.add_argument("--outputs", default="")
    ap.add_argument("--dir", default="")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    try:
        contract = json.loads(Path(args.contract).read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"contract 读取失败: {e}", file=sys.stderr)
        return 2
    if not isinstance(contract, dict) or not contract.get("paths"):
        print("contract 里没有 paths", file=sys.stderr)
        return 2

    outputs: dict = {}
    if args.outputs:
        p = Path(args.outputs)
        if not p.exists():
            print(f"outputs 不存在: {p}", file=sys.stderr)
            return 2
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception as e:  # noqa: BLE001
                print(f"outputs 第 {i+1} 行解析失败: {e}", file=sys.stderr)
                return 2
            outputs[r.get("path_id")] = r.get("text") or ""
    elif args.dir:
        d = Path(args.dir)
        if not d.is_dir():
            print(f"目录不存在: {d}", file=sys.stderr)
            return 2
        for f in sorted(d.glob("*.txt")):
            outputs[f.stem] = f.read_text(encoding="utf-8")
    else:
        print("需要 --outputs 或 --dir", file=sys.stderr)
        return 2

    res = audit(contract, outputs)
    txt = json.dumps(res, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(txt, encoding="utf-8")
    print(txt)
    if res["n"] == 0:
        return 2
    return 0 if res["n_hit"] == res["n"] else 1


if __name__ == "__main__":
    sys.exit(main())
