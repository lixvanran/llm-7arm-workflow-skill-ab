#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ run.py —— ★ 七臂 × D01–D09 × reps 的跑批器（★ 增量落盘、★ 可断点续跑 ★）

★ 落盘：★ out/units.jsonl（★ 一行一个 (arm, task, rep) ★）＋ out/calls.jsonl（★ 一行一次调用 ★）★★
★ 断点续跑：★ 已完成的 (arm, task_id, rep) 不重跑 ★
★ 失败不许静默：★ 每个单元记 ok / fail 原因 / 调用数 / token ★
"""
import argparse, concurrent.futures as cf, json, os, pathlib, sys, time

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "l0"))
sys.path.insert(0, str(HERE))          # ★ 我的目录必须【在最前】★ ——★ 否则 l0/llm.py 会抢同名模块 ★
import importlib.util
from llm import LLMBase, LLMChat, Stats          # noqa: E402
import arms as A                                   # noqa: E402

from metric import key_tokens, coarse_cover   # ★ 从 l0/run_l0.py 原样 AST 抽出（★ 见 metric.py ★）

DEVSET = (REPO / "来源与底稿" / "第三组_治塌缩层3" / "cmp8repo" / "repro" / "devset" / "devset.json")
OUT = HERE / "out"


def load_tasks():
    d = json.loads(DEVSET.read_text(encoding="utf-8"))
    return d["tasks"]


def run_unit(arm, task, rep, model):
    st = Stats()
    llm = LLMBase(model=model, temperature=0.7, max_tokens=6000, stats=st)
    t0 = time.time()
    try:
        r = A.ARMS[arm](llm, task, model)
    except Exception as e:                              # noqa: BLE001
        r = {"answer": "", "extra": {"exception": str(e)[:200]}}
    answer = r.get("answer", "") or ""
    ok_gen = bool(answer.strip())
    claims = []
    if ok_gen:
        try:
            claims = A.uniform_claims(llm, answer, model=model)
        except Exception as e:                          # noqa: BLE001
            r.setdefault("extra", {})["extract_exception"] = str(e)[:160]
    gold = task.get("conclusion_space") or []
    cov = coarse_cover(gold, claims) if gold else {"coverage": 0.0, "n_hit": 0, "n_gold": 0}
    return {"arm": arm, "task_id": task["task_id"], "rep": rep, "model": model,
            "ok": ok_gen, "answer": answer, "claims": claims,
            "coverage": cov.get("coverage"), "n_hit": cov.get("n_hit"), "n_gold": cov.get("n_gold"),
            "per_conclusion": cov.get("per_conclusion"),
            "n_claims": len(claims), "calls": st.summary(),
            "wall_s": round(time.time() - t0, 1), "extra": r.get("extra", {})}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--arms", default=",".join(A.ARMS))
    ap.add_argument("--tasks", type=int, default=9)
    ap.add_argument("--model", default="MiniMax-M3")
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--tag", default="ab1")
    a = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    units_p = OUT / ("units_%s.jsonl" % a.tag)
    calls_p = OUT / ("calls_%s.jsonl" % a.tag)
    tasks = load_tasks()[: a.tasks]
    arm_list = [x for x in a.arms.split(",") if x]

    done = set()
    if units_p.exists():
        for line in units_p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    r = json.loads(line)
                    done.add((r["arm"], r["task_id"], r["rep"]))
                except Exception:
                    pass
    plan = [(arm, t, rep) for arm in arm_list for t in tasks for rep in range(1, a.reps + 1)
            if (arm, t["task_id"], rep) not in done]
    print("★ 跑批：%d 臂 × %d 题 × %d rep ｜ 已完成 %d ｜ 待跑 %d"
          % (len(arm_list), len(tasks), a.reps, len(done), len(plan)), flush=True)

    fh = units_p.open("a", encoding="utf-8")
    fc = calls_p.open("a", encoding="utf-8")
    n = 0
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(run_unit, arm, t, rep, a.model): (arm, t["task_id"], rep)
                for (arm, t, rep) in plan}
        for f in cf.as_completed(futs):
            arm, tid, rep = futs[f]
            try:
                r = f.result()
            except Exception as e:                          # noqa: BLE001
                r = {"arm": arm, "task_id": tid, "rep": rep, "ok": False,
                     "answer": "", "claims": [], "coverage": None, "n_hit": None, "n_gold": None,
                     "calls": {"n_calls": 0, "n_fail": 1, "tokens": 0},
                     "wall_s": 0, "extra": {"exception": str(e)[:200]}}
            fh.write(json.dumps(r, ensure_ascii=False) + "\n"); fh.flush()
            for c in r.get("calls", {}).get("raw", []) or []:
                fc.write(json.dumps({"arm": arm, "task_id": tid, "rep": rep, **c}, ensure_ascii=False) + "\n")
            fc.flush()
            n += 1
            print("  [%3d/%3d] %-10s %s rep%d → cov=%s hit=%s/%s claims=%d calls=%d tok=%d %.0fs"
                  % (n, len(plan), arm, tid, rep, r.get("coverage"), r.get("n_hit"), r.get("n_gold"),
                     r.get("n_claims", 0), r["calls"]["n_calls"], r["calls"]["tokens"], r["wall_s"]),
                  flush=True)
    fh.close(); fc.close()
    print("★ 跑完 %d 个单元" % n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
