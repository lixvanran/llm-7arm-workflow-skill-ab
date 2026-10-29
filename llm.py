#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ llm.py —— 统一通道（★ 全部臂用同一个模型、★ 同一套预算、★ 同一套记账 ★）

★ 纪律（★ 全是这轮真踩过的 ★）：
★   ① MiniMax-M3 是推理模型、★ 推理 token 会随机暴涨 ⇒ 吃光 max_tokens ⇒ 正文 0 字、★
★      而 HTTP 200、usage 正常 ⇒ 整批静默作废。★ ⇒ ★ 本通道一律 `thinking:{"type":"disabled"}` ★
★   ② 绝不加 `reasoning_split:true`（★ 实测推理暴涨到 7995、★ 正文 0 字 ★）
★   ③ `<think>` 仍然剥（★ 兜底 ★）★★
★   ④ 失败必须可计数：★ 每次调用记 ok/finish_reason/字符数/token ★ ⇒ 不许静默归零 ★
★   ⑤ 凭据只从 env 读、★ 不落盘、★ 不进任何会进 git 的文件 ★
"""
import json, os, re, time, urllib.request, urllib.error

ENDPOINT = "https://api.minimaxi.com/v1/chat/completions"
MODEL = "MiniMax-M3"
THINK_RE = re.compile(r"<think>.*?</think>", re.S)


def strip_think(t):
    if not t:
        return ""
    if "</think>" in t:
        t = t.rsplit("</think>", 1)[-1]
    t = THINK_RE.sub("", t)
    return t.strip()


class Stats:
    """★ 通道记账（★ 每次调用一行 ★）"""

    def __init__(self):
        self.calls = []
        self.tokens = 0
        self.fail = 0
        self.truncated = 0

    def add(self, rec):
        self.calls.append(rec)
        self.tokens += rec.get("total_tokens", 0) or 0
        if not rec.get("ok"):
            self.fail += 1

    def summary(self):
        return {"n_calls": len(self.calls), "n_fail": self.fail,
                "n_truncated": self.truncated, "tokens": self.tokens}


class LLMBase:
    """★ ③组风格接口：★ chat() 返回【字符串】★★"""

    def __init__(self, model=MODEL, temperature=0.7, max_tokens=6000, stats=None, retries=2):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.retries = retries
        self.stats = stats if stats is not None else Stats()
        self.rec = []

    def _post(self, prompt, max_tokens, temperature):
        body = json.dumps({
            "model": self.model, "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature, "max_tokens": max_tokens,
            "thinking": {"type": "disabled"},
        }).encode("utf-8")
        req = urllib.request.Request(
            ENDPOINT, data=body, method="POST",
            headers={"Authorization": "Bearer %s" % os.environ["MINIMAX_SUBSCRIPTION_KEY"],
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            d = json.loads(r.read().decode("utf-8"))
        ch = d["choices"][0]
        txt = strip_think(ch.get("message", {}).get("content") or "")
        usage = d.get("usage", {}) or {}
        return txt, ch.get("finish_reason"), usage

    def chat(self, prompt, system=None, max_tokens=None, temperature=None,
             model=None, temp=None, **kw):
        """★ ③组会传 model/temp/budgets/min_ok/purpose ⇒ ★ 这里全收、★ 忽略不认的 ★"""
        mt = int(max_tokens or self.max_tokens)
        tt = temperature if temperature is not None else (temp if temp is not None else self.temperature)
        last = None
        for attempt in range(1, self.retries + 2):
            t0 = time.time()
            try:
                txt, fr, usage = self._post(prompt, mt, tt)
                # ★ 【截断】与【失败】必须分开记（★ 混在一起 ⇒ 读者以为臂坏了 ★）★★
                truncated = (fr == "length")
                ok = bool(txt.strip())
                rec = {"ok": ok, "truncated": truncated, "finish_reason": fr, "chars": len(txt),
                       "total_tokens": usage.get("total_tokens", 0),
                       "wall_s": round(time.time() - t0, 2), "attempt": attempt,
                       "prompt_chars": len(prompt)}
                self.stats.add(rec)
                self.rec.append(rec)
                if ok and not truncated:
                    return txt
                # ★ 截断了但有内容 ⇒ ★ 【不算失败】★ ★ 交回去并让上层知道它被截了 ★
                if ok and truncated:
                    self.stats.truncated += 1
                    return txt
                last = "empty_or_length"
            except Exception as e:                       # noqa: BLE001
                msg = str(e)
                # ★ MiniMax 的两种 429 要分清（★ 实测 ★）：
                #   ★ 2062 = 速率限制 ⇒ 退避可过；★ 2056 = 用量上限 ⇒ 退避无用 ★
                kind = "rate_limited" if "429" in msg else "error"
                rec = {"ok": False, "error": msg[:160], "kind": kind,
                       "wall_s": round(time.time() - t0, 2),
                       "attempt": attempt, "total_tokens": 0, "chars": 0,
                       "finish_reason": "error"}
                self.stats.add(rec)
                self.rec.append(rec)
                last = msg[:120]
                if kind == "rate_limited":
                    time.sleep(8 * attempt)      # ★ 限流要多退避 ★
                    continue
            time.sleep(2 * attempt)
        return ""


class LLMChat(LLMBase):
    """★ L0 风格接口：★ chat() 返回【(txt, ok)】★★"""

    def chat(self, prompt, max_tokens=None, temperature=None, **kw):
        txt = super().chat(prompt, max_tokens=max_tokens, temperature=temperature, **kw)
        return txt, bool(txt.strip())
