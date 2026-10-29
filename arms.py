#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ arms.py —— ★ 七个臂（★ 直调 / 等预算 / 层2 / 层3 / L0 / skill v1.1 / skill v3 ★）

★ ★ ★ 全部臂的共同契约 ★ ★ ★
   ① **同一批题**（D01–D09）★ ② **同一个模型**（MiniMax-M3 ＋ 关推理）★
   ③ **同一套输出规格**（③组的 _OUT_SPEC：3–6 条、行首「- 」）★
   ④ **同一个抽结论器**（③组 `_extract_claims`）★ ⑤ **同一把尺**（coarse_cover）★★
   ⇒ ★ 臂之间只差【怎么组织这次回答】、★ 不差【别的任何东西】 ★

★ ★ 臂的来源（★ 一律用【原作者的代码】、★ 我只做适配 ★）★★
| 臂 | 来源 | 我改了什么 |
|---|---|---|
| direct | ③组 `run_dev.arm_direct` | 抄 12 行（★ 原样口径 ★） |
| bestof3 | ③组 `anchor_out.best_of_n_direct` | ★ 零改动 ★ |
| w_layer2 | ③组 `workflow.CollapseFixWorkflow(evolve=False)` | ★ 零改动 ★ |
| w_layer3 | ③组 `workflow.CollapseFixWorkflow(evolve=True)` | ★ 零改动 ★ |
| l0_expand | L0 `agent.ProblemSpaceAgent` | ★ 只换 llm 适配器（★ 返回值形状 ★）★★ |
| skill_v1 | thinking-surface v1.1 | ★ 我按 SKILL.md 写的适配（★ 轴→分支→合流 ★）★★ |
| skill_v3 | thinking-surface v3 | ★ 同上 ★ |
"""
import json, os, pathlib, re, sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
REPRO = REPO / "来源与底稿" / "第三组_治塌缩层3" / "cmp8repo" / "repro"
NAS = pathlib.Path("/run/csi/mount-root/nas/eab0d61a99b6696edb3d2aff87b585e8/.skills")

# ★ 路径解析：★ 【包内 vendor 优先】→ 【worktree 原件】→ 【NAS skill】★★
# ★ 三级查找的意义：★ 仓被单独 clone 下来时（★ 没有 worktree 上下文 ★）也能跑 ★
_V = HERE / "vendor"
if (_V / "thirdgrp" / "workflow.py").exists():
    THIRD_SRC = _V / "thirdgrp"          # ★ 包内副本（★ 自包含 ★）
    L0_AGENT = _V / "l0" / "agent.py"
    SKILL_ROOT = _V / "skill"
else:
    THIRD_SRC = REPRO / "src"            # ★ 回落：worktree 里的原件 ★
    L0_AGENT = REPO / "l0" / "agent.py"
    SKILL_ROOT = NAS if NAS.exists() else _V / "skill"

sys.path.insert(0, str(THIRD_SRC))
import workflow as W            # noqa: E402  ★ ③组的治塌缩工作流 ★
import anchor_out as AO          # noqa: E402  ★ ③组的对照臂与装配 ★
# ★ L0 的 agent.py 按【文件路径】导入（★ 不把 l0/ 放进 sys.path、★ 否则它的 llm.py 会抢同名模块 ★）
import importlib.util as _ilu
_sp = _ilu.spec_from_file_location("l0_agent", str(L0_AGENT))
_agent = _ilu.module_from_spec(_sp); _sp.loader.exec_module(_agent)
ProblemSpaceAgent = _agent.ProblemSpaceAgent

MODEL = "MiniMax-M3"

def _sk(name, rel):
    """★ skill 资产路径：★ 先试包内 vendor、★ 再试 NAS ★"""
    for root in (SKILL_ROOT, NAS):
        if not root:
            continue
        cand = root / name / rel
        if cand.exists():
            return cand
    return SKILL_ROOT / name / rel


SKILL_PKG = {
    "skill_v1": {"skill": _sk("thinking-surface", "SKILL.md"),
                 "refs": [_sk("thinking-surface", "references") / "path-recipes.md",
                          _sk("thinking-surface", "references") / "absence-check.md",
                          _sk("thinking-surface", "references") / "fork-map.md",
                          _sk("thinking-surface", "references") / "signature-rules.md",
                          _sk("thinking-surface", "references") / "merge-rules.md"]},
    "skill_v3": {"skill": _sk("thinking-surface-v3", "SKILL.md"),
                 "refs": [_sk("thinking-surface-v3", "references") / "path-recipes.md",
                          _sk("thinking-surface-v3", "references") / "mechanism-slots.md",
                          _sk("thinking-surface-v3", "references") / "fork-map.md",
                          _sk("thinking-surface-v3", "references") / "signature-rules.md",
                          _sk("thinking-surface-v3", "references") / "merge-rules.md"]},
}
N_BRANCH = 4


def read(p):
    return pathlib.Path(p).read_text(encoding="utf-8", errors="replace")


def skill_ctx(arm):
    pkg = SKILL_PKG[arm]
    parts = [read(pkg["skill"])]
    for r in pkg["refs"]:
        parts.append("\n\n【参考文件：%s】\n%s" % (r.name, read(r)))
    return "\n".join(parts)


# ───────────────────────── 通用：抽结论（★ 所有臂同一个抽法 ★）─────────────────────────

def uniform_claims(llm, answer, model=MODEL, cap=12):
    """★ 统一抽结论（★ 直接用③组的 `_extract_claims`、★ 零改动 ★）"""
    return W._extract_claims(llm, answer or "", model=model, cap=cap)


# ───────────────────────── 臂 1：直调 ─────────────────────────

def arm_direct(llm, task, model=MODEL):
    prompt = "问题：%s\n\n%s" % (task["ask"], W._OUT_SPEC)
    out, _bi = W._chat(llm, prompt, purpose="B0_direct", model=model, temp=0.7,
                       max_tokens=0, min_ok=20)
    return {"answer": out or "", "extra": {"n_calls": len(getattr(llm, "rec", []))}}


# ───────────────────────── 臂 2：等预算对照（★ ③组原码 ★）─────────────────────────

def arm_bestof3(llm, task, model=MODEL):
    r = AO.best_of_n_direct(llm, task, model, n=3, seed=0)
    return {"answer": r.get("answer", ""), "extra": {"ops": r.get("ops")}}


# ───────────────────────── 臂 3/4：③组工作流（层2 / 层3）─────────────────────────

def arm_workflow(llm, task, model=MODEL, evolve=True, layer="L3"):
    wf = W.CollapseFixWorkflow(llm, n_slots=4, seed=0, frame_seed=None,
                               model=model, judge_model=model, max_rounds=2,
                               evolve=evolve, layer=layer, action_mode="lookup", policy=None)
    # ★★ 【vendored 代码的缺陷】★★ workflow.py:1088 读 `self.frame_seed`、★ 而 __init__ 从不设它
    #   ⇒ AttributeError ⇒ **这条 W 臂照现状跑不起来**。★ 他们的仓是【沙箱重置后的快照】、★ runs/ 不在里面 ★
    #   ⇒ 修法：★ 补一行赋值、★ **值仍是 None**（★ 与作者 run_dev.py 的默认值一致 ★）
    #   ⇒ ★ **算法一行未改**（★ select_frames(seed=C["seed"], frame_seed=None) ★ 本来就是这个语义 ★）★★
    wf.frame_seed = None
    r = wf.run(task["ask"])
    return {"answer": r.get("answer", ""),
            "extra": {"frames": r.get("frames"), "failures": r.get("failures"),
                      "archive": r.get("archive"), "illum": r.get("illum"),
                      "rounds": r.get("rounds"), "layer": r.get("layer")}}


# ───────────────────────── 臂 5：L0 Agent（自主建问题空间）─────────────────────────

class _TupleLLM:
    """★ L0 的 agent 要 `llm.chat(...)` 返回【(txt, ok)】★ ——★ ③组的要【字符串】★
    ★ ⇒ 这里给 L0 单独套一层（★ 同一个底层通道、★ 同一套记账 ★）★★"""

    def __init__(self, base):
        self._b = base

    def chat(self, prompt, **kw):
        txt = self._b.chat(prompt, **kw)
        return txt, bool((txt or "").strip())

    def __getattr__(self, name):
        return getattr(self._b, name)


def arm_l0_expand(llm, task, model=MODEL):
    goal = "题目：%s\n问题：%s" % (task["title"], task["ask"])
    ag = ProblemSpaceAgent(_TupleLLM(llm), goal)
    ag.explore()
    rep = ag.report()
    answer = "\n".join("- " + c for c in rep.get("claims", []))
    return {"answer": answer,
            "extra": {"n_angles": rep.get("n_angles"), "n_claims": rep.get("n_claims"),
                      "stopped_reason": rep.get("stopped_reason"),
                      "self_reported_no_new_dimension": rep.get("self_reported_no_new_dimension"),
                      "trail": rep.get("trail"), "diagnostics": rep.get("diagnostics")}}


# ───────────────────────── 臂 6/7：skill ─────────────────────────

AX_FMT = """【只输出这个 JSON、★ 不要别的文字 ★】
{"axes":[{"id":"A1","name":"轴名（≤12字）","approach":"这条轴在本题的具体做法（★ 必须含一个可执行/可观察的动作 ★）","cost":"这条轴的代价、谁会不满意","sign_pos":["正签名1","正签名2"],"sign_neg":"这条路上不该出现的东西"}]}"""


def _parse_axes(txt):
    m = re.search(r"\{.*\}", txt or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except Exception:
        return None
    ax = d.get("axes")
    if not isinstance(ax, list) or not ax:
        return None
    out = []
    for a in ax:
        if isinstance(a, dict) and str(a.get("name") or "").strip():
            out.append({"id": str(a.get("id") or len(out) + 1),
                        "name": str(a["name"]).strip(),
                        "approach": str(a.get("approach") or "").strip(),
                        "cost": str(a.get("cost") or "").strip(),
                        "sign_pos": [str(x) for x in (a.get("sign_pos") or [])][:3],
                        "sign_neg": str(a.get("sign_neg") or "").strip()})
    return out or None


def arm_skill(llm, task, model=MODEL, arm="skill_v1"):
    """★ 按该 skill 的 SKILL.md 走：★ 选轴 → ★ 隔离生成 N 条 → ★ 保留分歧合流 ★"""
    ctx = skill_ctx(arm)
    if arm == "skill_v1":
        step = ("请按本规程的【第 1–3 步】处理下面这道题：\n"
                "第 1 步 列出这道题里的【可核验对象类别】（每类给 2–3 个具体例子）；\n"
                "第 2 步 双轨取轴：轨 A 从【参考文件 path-recipes.md】的轴库挑（过程轴），"
                "轨 B 从第 1 步的对象类别里挑（实体域轴），合并去重后【总共 3–5 条】；\n"
                "第 3 步 对每条轴做落地性闸门（必须能落到第 1 步的某个对象类别上），"
                "并写下正签名（2 个具体名词/动作）、反签名、代价。\n"
                "★ 本题有唯一正确答案、★ 没有「决策点」可写 ⇒ ★ 不要硬造决策点；★ 代价就写这条角度的代价。\n"
                "★ 签名只用于事后核对、★ 不要当成生成约束。★ 只输出 3–5 条轴。\n\n" + AX_FMT)
    else:
        step = ("请按本规程的【第 1–4 步】处理下面这道题：\n"
                "第 1 步 先判断【有没有真分叉点】（★ 本题若有唯一结论、★ 就明说并只给 1–3 条轴 ★）；\n"
                "第 2 步 拿到任务专属的分叉轴（★ 优先从【上下文/题面】找、★ 其次自测绘、★ 通用库只做查漏 ★），共 3–5 条；\n"
                "第 3 步 把每条轴写成【五槽机制句】（谁/对谁/做什么/得到/代价）；\n"
                "第 4 步 为每条路线派生 2 个正签名（★ 取自五槽里的具体名词 ★）＋ 1 个反签名。\n"
                "★ 本题有唯一正确答案、★ 没有「决策点」可写 ⇒ ★ 「做什么」槽就写这条角度的具体核查动作。\n"
                "★ 只输出 3–5 条轴。\n\n" + AX_FMT)
    goal = "题目：%s\n问题：%s" % (task["title"], task["ask"])
    ax_txt, _ = W._chat(llm, step + "\n\n" + goal, purpose="skill_axes", model=model,
                         temp=0.7, max_tokens=0, min_ok=20)
    axes = _parse_axes(ax_txt)
    if not axes:
        ax_txt2, _ = W._chat(llm, step + "\n\n" + goal, purpose="skill_axes_retry", model=model,
                             temp=0.7, max_tokens=0, min_ok=20)
        axes = _parse_axes(ax_txt2)
    if not axes:
        return {"answer": "", "extra": {"fail": "axes_parse_failed", "axes": []}}
    axes = axes[:N_BRANCH]
    while len(axes) < N_BRANCH:
        axes.append(dict(axes[-1], id="dup"))
    branches = []
    for k, ax in enumerate(axes, 1):
        brief = ("你负责第 %d 条轴（共 %d 条）。★ 只走这一条、★ 不要提及其他轴。\n"
                 "轴名：%s\n本题的具体做法：%s\n这条路的代价：%s\n"
                 % (k, N_BRANCH, ax["name"], ax["approach"] or "（规程未给出、★ 请自己落成本题的具体做法）",
                    ax["cost"] or "（规程未给出、★ 请自己写出代价）"))
        if arm == "skill_v3":
            brief += "★ 正签名要点（★ 必须真的体现在正文里 ★）：%s\n" % ("、".join(ax["sign_pos"]) or "（无）")
            brief += "★ 反签名（这条路上不该出现的东西）：%s\n" % (ax["sign_neg"] or "（无）")
        else:
            brief += "★ 签名不在这里给（★ 本规程规定签名只用于事后核对 ★）。\n"
        brief += ("\n★ 请只输出【这一条角度】的核查结论，★ 并按下面的输出规格给。\n"
                  + W._OUT_SPEC)
        b, _ = W._chat(llm, brief + "\n\n" + goal, purpose="skill_branch%d" % k, model=model,
                       temp=0.7, max_tokens=0, min_ok=20)
        branches.append(b or "")
    if arm == "skill_v1":
        merge_fmt = ("【合流】保留分歧、★ 不要取交集、不要投票。输出：每条路径的结论 ＋ 它们之间的冲突点。\n"
                     "★ 最后做【缺席自检】：哪些可核验对象类别一条都没碰、★ 显式说出来。")
    else:
        merge_fmt = ("【合流·逐条】每条路线的做法 ＋ 它的代价\n"
                     "【合流·冲突点】哪两条路在哪个点直接对立\n"
                     "【合流·待拍板】需要取舍的地方\n"
                     "★ 不许投票、不许取交集。")
    body = "\n\n".join("【路径 %d：%s】\n%s" % (i + 1, axes[i]["name"], b)
                       for i, b in enumerate(branches))
    merged, _ = W._chat(llm, "下面是同一道题下 %d 条独立路径各自的产出。\n%s\n\n%s\n\n%s"
                         % (len(branches), body, merge_fmt, W._OUT_SPEC),
                         purpose="skill_merge", model=model, temp=0.7, max_tokens=0, min_ok=20)
    return {"answer": merged or "",
            "extra": {"axes": [a["name"] for a in axes], "n_branches": len(branches),
                      "branches_chars": [len(b) for b in branches]}}


ARMS = {
    "direct": lambda llm, t, m: arm_direct(llm, t, m),
    "bestof3": lambda llm, t, m: arm_bestof3(llm, t, m),
    "w_layer2": lambda llm, t, m: arm_workflow(llm, t, m, evolve=False, layer="L2"),
    "w_layer3": lambda llm, t, m: arm_workflow(llm, t, m, evolve=True, layer="L3"),
    "l0_expand": lambda llm, t, m: arm_l0_expand(llm, t, m),
    "skill_v1": lambda llm, t, m: arm_skill(llm, t, m, "skill_v1"),
    "skill_v3": lambda llm, t, m: arm_skill(llm, t, m, "skill_v3"),
}
ARM_NAME = {
    "direct": "直调（1 次）",
    "bestof3": "等预算对照（3 次独立直调）",
    "w_layer2": "③组工作流 · 层2（固定动作集）",
    "w_layer3": "③组工作流 · 层3（动作空间演化）",
    "l0_expand": "L0 Agent（自主建问题空间）",
    "skill_v1": "thinking-surface v1.1",
    "skill_v3": "thinking-surface v3",
}
