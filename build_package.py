#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ build_package.py —— 打包本实验（★ 自包含、★ 可解压后独立重算出表 ★）★★
★ ★ 纪律：★ 包内不写死自己的 sha/大小（★ 非循环 ⇒ 用 SHA256SUMS.txt 自身作锚 ★）★
★ ★ 纪律：★ 写入器 ≠ 检查器 ⇒ ★ 打包后另跑 tools 复算一遍 ★★
"""
import hashlib, json, pathlib, shutil, subprocess, sys, zipfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent                      # worktree 根
DELIV = pathlib.Path("/workspace/deliver")
NAME = "七臂同量纲对照_工作流_vs_skill_2026-10-29"

FILES = [
    # (源, 包内路径)
    (HERE / "七臂同量纲对照_工作流_vs_skill_2026-10-29.md", "REPORT.md"),
    (HERE / "PREREG.md", "PREREG.md"),
    (HERE / "llm.py", "code/llm.py"),
    (HERE / "arms.py", "code/arms.py"),
    (HERE / "run.py", "code/run.py"),
    (HERE / "metric.py", "code/metric.py"),
    (HERE / "judge.py", "code/judge.py"),
    (HERE / "inputs/devset.json", "inputs/devset.json"),
    (HERE / "vendor/thirdgrp/workflow.py", "vendor/thirdgrp/workflow.py"),
    (HERE / "vendor/thirdgrp/anchor_out.py", "vendor/thirdgrp/anchor_out.py"),
    (HERE / "vendor/thirdgrp/judge/u1_lib.py", "vendor/thirdgrp/judge/u1_lib.py"),
    (HERE / "vendor/thirdgrp/judge/measure.py", "vendor/thirdgrp/judge/measure.py"),
    (HERE / "vendor/thirdgrp/space.py", "vendor/thirdgrp/space.py"),
    (HERE / "vendor/thirdgrp/run_dev.py", "vendor/thirdgrp/run_dev.py"),
    (HERE / "vendor/l0/agent.py", "vendor/l0/agent.py"),
    (HERE / "vendor/l0/run_l0.py", "vendor/l0/run_l0.py"),
    (HERE / "out/units_ab1.jsonl", "out/units_ab1.jsonl"),
    (HERE / "out/units_ab2.jsonl", "out/units_ab2.jsonl"),
    (HERE / "out/calls_ab2.jsonl", "out/calls_ab2.jsonl"),
    (HERE / "out/results_ab2.md", "out/results_ab2.md"),
    (HERE / "out/results_ab2.json", "out/results_ab2.json"),
    (HERE / "out/results_ab1.md", "out/results_ab1.md"),
    (HERE / "out/results_ab1.json", "out/results_ab1.json"),
]
SKILL_DIR = pathlib.Path("/run/csi/mount-root/nas/eab0d61a99b6696edb3d2aff87b585e8/.skills")


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    stage = HERE / "_stage"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    for src, rel in FILES:
        if not src.exists():
            print("!! 缺文件: %s" % src)
            return 1
        dst = stage / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    # skill 资产
    for name, rel in [("thinking-surface", "vendor/skill/thinking-surface"),
                       ("thinking-surface-v3", "vendor/skill/thinking-surface-v3")]:
        local = HERE / "vendor" / "skill" / name
        d = local if local.exists() else (SKILL_DIR / name)
        if d.exists():
            shutil.copytree(d, stage / rel, dirs_exist_ok=True)
        else:
            print("!! 缺 skill 资产: %s" % d)
    # 可读样本：每题每臂 rep1 的答案
    samp = stage / "samples"
    samp.mkdir()
    units = [json.loads(l) for l in (HERE / "out/units_ab2.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    for r in units:
        if r["rep"] != 1:
            continue
        body = "## %s / %s\n\n%s\n" % (r["arm"], r["task_id"], r.get("answer") or "(空)")
        (samp / ("%s__%s.md" % (r["task_id"], r["arm"]))).write_text(body, encoding="utf-8")
    # README
    (stage / "README.md").write_text(
        "# 七臂同量纲对照（工作流 + skill + 直调）· 交付包\n\n"
        "- **先读 `REPORT.md`**（唯一入口，含结论、判决、局限）\n"
        "- `PREREG.md` 预注册（早于任何批量调用）\n"
        "- `code/` 本实验代码；`vendor/` 被跑的第三方代码与 skill 资产；`inputs/` 任务与金标\n"
        "- `out/` 两遍跑批的逐单元产出、逐调用记录与出表结果\n"
        "- `samples/` 每题每臂 rep1 的原始答案（人肉可读）\n"
        "- `SHA256SUMS.txt` 非循环锚（用 `sha256sum SHA256SUMS.txt` 核）\n\n"
        "★ 复算：解压后 `python3 code/judge.py ab2`（★ 零改动、★ 只读 `out/units_ab2.jsonl`、★ 不调 API ★）\n",
        encoding="utf-8")
    # SHA256SUMS.txt（★ 不含自身 ⇒ 非循环 ★）
    lines = []
    for p in sorted(stage.rglob("*")):
        if p.is_file() and p.name != "SHA256SUMS.txt":
            lines.append("%s  %s" % (sha(p), p.relative_to(stage).as_posix()))
    (stage / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    DELIV.mkdir(parents=True, exist_ok=True)
    zp = DELIV / (NAME + ".zip")
    if zp.exists():
        zp.unlink()
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(stage.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(stage).as_posix())
    shutil.rmtree(stage)
    print("✔ 打包: %s （%d 字节、%d 成员）" % (zp, zp.stat().st_size, len(zipfile.ZipFile(zp).namelist())))
    print("  sha256: %s" % sha(zp))
    return 0


if __name__ == "__main__":
    sys.exit(main())
