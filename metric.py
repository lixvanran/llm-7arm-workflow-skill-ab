#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ metric.py —— ★ 尺子（★ 从 l0/run_l0.py 【原样 AST 抽取】、★ 不复制、不漂移、无 import 副作用 ★）

★ 为什么这么绕（★ 实测 2026-10-29 ★）：★ l0/run_l0.py 顶层 `from llm import LLM`
★   ⇒ ★ 直接 import 它会把我自己的 llm.py 抢走 ⇒ ★ 于是改用【AST 抽出那两个函数的源码】exec ★
★   ⇒ ★ 函数体一个字不改（★ 口径与 L0 那套【完全一致】★）、★ 且不碰 sys.modules ★★
"""
import ast, pathlib, re, unicodedata

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
# ★ 路径：★ 包内 vendor 优先、★ 否则回落 worktree 原件（★ 仓单独 clone 也能跑 ★）
_LOCAL = pathlib.Path(__file__).resolve().parent / "vendor" / "l0" / "run_l0.py"
RUN_L0 = (_LOCAL if _LOCAL.exists() else REPO / "l0" / "run_l0.py")


def _load_fns(names):
    src = RUN_L0.read_text(encoding="utf-8")
    tree = ast.parse(src)
    ns = {"re": re, "unicodedata": unicodedata}
    # ★ 先把模块级的常量（TOKEN_RE / STOP）原样取过来
    #   ⇒ ★ 不能只走 literal_eval（★ TOKEN_RE = re.compile(...) 不是字面量 ★）★
    #   ⇒ ★ 改成【按源码 exec】★ ——★ 常量与函数都出自同一份原文、★ 口径不会漂 ★★
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            code = ast.get_source_segment(src, node)
            try:
                exec(compile(code, str(RUN_L0), "exec"), ns)
            except Exception:
                pass
        if isinstance(node, ast.FunctionDef) and node.name in names:
            code = ast.get_source_segment(src, node)
            exec(compile(code, str(RUN_L0), "exec"), ns)
    return ns


_ns = _load_fns({"key_tokens", "coarse_cover"})
key_tokens = _ns["key_tokens"]
coarse_cover = _ns["coarse_cover"]

if __name__ == "__main__":
    print("★ 尺子已从 %s 原样抽出" % RUN_L0)
    g = [{"id": "C1", "text": "顺序读 7450 MB/s 正确"},
         {"id": "C2", "text": "保修 5 年"}]
    print("   自测：", coarse_cover(g, ["顺序读 7450 MB/s 是对的", "保修 5 年"]))
