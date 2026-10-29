"""v3 轴库（分层、带元数据）+ 选轴检索工具。

为什么做这个：v1 实测「让 Agent 自己现编分支」(覆盖 0.72) 远低于「从库里挑」(1.3-1.5)。
⇒ 框架质量取决于框架是「给定的」还是「现编的」。把「给定」工程化 = 把轴库做成可检索的资产：
每条轴带「它在问什么 / 什么时候适用 / 什么时候不成立 / 典型做法 / 典型失败」，
工具按题面检索出候选轴 + 禁忌轴，Agent 在此基础上改写成本题语言（那一步的增益已验证）。

用法：
    python3 axis_picker.py --task 为学校食堂设计一套减少浪费的机制 [--topk 6]
    python3 axis_picker.py --task ... --type 机制/制度设计
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent

TASK_TYPES = {
    "活动/方案设计": {
        "signals": ["活动", "方案", "策划", "设计一个", "怎么组织", "节目"],
        "axes": ["content", "relation", "incentive", "venue"],
        "ban": ["fallback"],
    },
    "机制/制度设计": {
        "signals": ["机制", "制度", "规则", "管理办法", "规范", "如何约束"],
        "axes": ["rule", "incentive", "price", "fallback"],
        "ban": ["content"],
    },
    "定价/商业模式": {
        "signals": ["定价", "收费", "价格", "商业模式", "盈利", "变现", "订阅"],
        "axes": ["price", "reverse", "beneficiary", "budget"],
        "ban": ["rhythm"],
    },
    "公共服务/社区": {
        "signals": ["社区", "居民", "公共服务", "政务", "养老", "小区"],
        "axes": ["budget", "matching", "rule", "beneficiary"],
        "ban": ["price"],
    },
    "内容/课程/产品": {
        "signals": ["课程", "内容", "产品", "教材", "教学", "读物", "培训"],
        "axes": ["content", "relation", "venue", "matching"],
        "ban": ["rule"],
    },
    "流程/效率问题": {
        "signals": ["效率", "流程", "耗时", "排队", "卡在", "缩短", "提速"],
        "axes": ["rhythm", "reverse", "matching", "fallback"],
        "ban": ["content"],
    },
    "治理/监督问题": {
        "signals": ["监督", "监管", "违规", "检查", "问责", "整顿", "查处"],
        "axes": ["rule", "rhythm", "budget", "fallback"],
        "ban": ["relation"],
    },
}

# ── 每条轴的判别词表（手写）──
# 为什么手写：轴的"通用语气"（asks/question/failure）里全是提问模板的措辞（核心/关键/一个），
# 用它们做匹配 ⇒ 检索结果被脚手架词主导、退化成"按类型返回固定几条"。
# 真正有判别力的是**具体词汇**：内容轴的"书目/选材/讲什么"，关系轴的"小组/结对/家长"……
# 这张表也是工具可审计性的载体：一条轴为什么被选中，能指回它命中的词。
KEYWORDS = {
    "content": "题材 素材 编排 选篇 讲义 读本 主题 内容策划 讲什么 读什么",
    "relation": "伙伴 搭档 小组 编制 值守 结对 陪伴 互动 老带新 谁和谁 同行",
    "incentive": "驱动 好处 徽章 奖券 奖赏 荣誉 评比 兑换 惩罚 计分 记分",
    "price": "费用 付费 单价 价位 分档 涨价 免单 折算 门槛 掏钱",
    "reputation": "声誉 评价 评分 口碑 红黑榜 荣誉 公布 评比 名声 可见度",
    "venue": "场地 空间 线下 动线 教室 广场 摊位 快闪 驻点 场所 位置",
    "channel": "渠道 触达 通知 短信 微信群 公众号 上门 柜台 派发 推送 电话 群消息",
    "data": "记录 统计 台账 用量 错题 量化 报表 监测 单据 计数 行为",
    "automation": "自动 机器 提醒 归集 一键 智能 自助 无人 机器人 程序化",
    "identity": "身份 权限 实名 核验 访问 账号 隐私 验证码 证件 凭证",
    "rule": "规则 约束 规范 建档 编码 准入 清单 禁止 条例 条款 硬性",
    "transparency": "透明 公开 看板 可见 公布 对外 进程公开 亮出来 晒出来",
    "accountability": "问责 负责 追责 担责 整改 复查 留痕 处罚 出事",
    "timing": "时机 提前 多久之前 节前 开学前 提前多久 时段 高峰 避开高峰",
    "rhythm": "节奏 频率 周期 每天 每周 连续 循环 每日 每期 隔天",
    "matching": "对接 配对 撮合 供需 派单 牵线 需求对齐 谁和谁 专人",
    "triage": "分诊 优先 紧急 分级 积压 候补 轻重 排序 先处理",
    "budget": "预算 经费 花费 钱从哪 出资 分摊 削减 分阶段 专项 资金 开支",
    "manpower": "人力 人手 谁来干 兼职 外包 岗位 人员 值守 人手配置",
    "scope": "范围 规模 缩小 只做 先做 限定 覆盖 部分 多少个 缩小到",
    "pilot": "试点 先试 小范围 对照组 实验 验证 试行 试运行 灰度",
    "fallback": "兜底 出错 失败 回退 止损 容错 人工 保底 应急 备用 接手",
    "exit": "退出 停止 到期 不续 免罚 终止 清算 关门 结束条件",
    "beneficiary": "受益 谁受益 弱势 沉默 边缘 真正需要 数字不熟练 开口子",
    "costbearer": "谁承担 转给 负担 谁买单 承担方 压力转移 代价 代价落在",
    "future": "未来 三个月后 长期 习惯 养成 自运转 可持续 之后 长远 形成",
    "reverse": "倒过来 先收钱 先付后用 反着来 反方向 先迈一步 反过来",
    "removal": "减法 砍掉 取消 去掉 合并 精简 拿掉 撤掉 少做 减哪个",
    "default": "默认 默选 默认开启 默认关闭 一键 免填 免操作 预先勾选 不用选",
    "precedent": "先例 已有 成熟做法 行业 复用 借鉴 现成 参考案例 照搬",
    "comparative": "比较 对比 基准 现状 公平 参照 提升幅度 绝对值 跟什么比",
}


AXES = {
    "content": {
        "name": "内容轴", "family": "对象", "asks": "事情的核心对象本身",
        "question": "把核心对象本身做到极致，能做出什么？",
        "examples": ["题材策划", "内容策展", "篇目编排", "原版教材"],
        "failure": "只换书目或主题，机制没换",
        "types": ["活动/方案设计", "内容/课程/产品"],
    },
    "relation": {
        "name": "关系轴", "family": "对象", "asks": "谁和谁发生什么关系",
        "question": "把人与人之间的关系重新安排，能变成什么？",
        "examples": ["两人搭档组", "结对陪伴", "交替值守", "以旧带新"],
        "failure": "只写建立社群，却不指定谁、怎么聚、多久一次",
        "types": ["活动/方案设计", "内容/课程/产品"],
    },
    "incentive": {
        "name": "驱动轴", "family": "交换", "asks": "什么机制让行为发生",
        "question": "把好处与代价设计成什么形式，人才会真的去做？",
        "examples": ["集章任务卡", "记分榜", "保证金退还", "服务时长计数"],
        "failure": "只说要鼓励，却没说鼓励什么、谁给、换什么",
        "types": ["活动/方案设计", "机制/制度设计"],
    },
    "price": {
        "name": "费用轴", "family": "交换", "asks": "钱怎么流",
        "question": "怎么收、谁付、买的是什么？",
        "examples": ["分档包月", "按次付费", "保金退回", "加价方式"],
        "failure": "费用变了，但没人真的会掏钱、或真会赖账",
        "types": ["机制/制度设计", "定价/商业模式"],
    },
    "reputation": {
        "name": "声誉轴", "family": "交换", "asks": "用可见的名声来驱动",
        "question": "把行为与可见的名声绑定，能产生什么？",
        "examples": ["楼栋张贴栏", "服务评价榜", "红黑榜"],
        "failure": "公示没人看，或公示引发对抗",
        "types": ["机制/制度设计", "治理/监督问题"],
    },
    "venue": {
        "name": "载体轴", "family": "场所", "asks": "事情在哪儿发生",
        "question": "换一个物理或场景载体，能产生什么差别？",
        "examples": ["中庭展台", "快闪摊位", "动线规划", "驻点服务"],
        "failure": "换了场地但流程没变",
        "types": ["活动/方案设计", "内容/课程/产品"],
    },
    "channel": {
        "name": "渠道轴", "family": "场所", "asks": "通过什么渠道触达与交付",
        "question": "换一条触达或交付渠道，能带来什么？",
        "examples": ["线下柜台", "上门服务", "群组通知", "短信提醒"],
        "failure": "渠道换了，但没人收到、收到也不行动",
        "types": ["流程/效率问题", "公共服务/社区"],
    },
    "data": {
        "name": "数据轴", "family": "数字", "asks": "用记录或统计来驱动",
        "question": "把过程记录下来，能看出什么、能改变什么？",
        "examples": ["行为记录", "用量统计", "错题统计", "台账"],
        "failure": "记了数据，但没人据此调整",
        "types": ["流程/效率问题", "治理/监督问题"],
    },
    "automation": {
        "name": "自动化轴", "family": "数字", "asks": "哪一步可以交给机器",
        "question": "把哪一步交给系统，能省掉谁的什么？",
        "examples": ["自动值守", "自动提醒", "自动归集", "一键提交"],
        "failure": "自动化了，但源头错误被放大",
        "types": ["流程/效率问题"],
    },
    "identity": {
        "name": "身份与权限轴", "family": "规则", "asks": "谁知道什么、谁能做什么",
        "question": "把身份与权限重新划一遍，能挡住什么、放出什么？",
        "examples": ["临时凭证码", "分级权限", "实名核验"],
        "failure": "只加限制不加出口，办事的人被卡住",
        "types": ["机制/制度设计", "公共服务/社区"],
    },
    "rule": {
        "name": "规则轴", "family": "规则", "asks": "靠什么约束",
        "question": "把约束写成什么可执行的形式？",
        "examples": ["编码建档", "准入条件", "操作规范", "禁用清单"],
        "failure": "规则写得像口号，执行者不知道做什么算违规",
        "types": ["机制/制度设计", "治理/监督问题"],
    },
    "transparency": {
        "name": "透明轴", "family": "规则", "asks": "让谁看见什么",
        "question": "把过程摊开给谁看，能改变什么？",
        "examples": ["结果上墙", "进度看板", "对外名单"],
        "failure": "透明了，但没人有动机去看",
        "types": ["治理/监督问题", "机制/制度设计"],
    },
    "accountability": {
        "name": "问责轴", "family": "规则", "asks": "出了事谁负责",
        "question": "把责任绑到具体的人和事上，会发生什么？",
        "examples": ["限期整改", "担责到人", "留痕复查"],
        "failure": "问责对象没有处置权，等于没人负责",
        "types": ["治理/监督问题", "机制/制度设计"],
    },
    "timing": {
        "name": "时机轴", "family": "时间", "asks": "什么时候做最有效",
        "question": "把关键动作挪到什么时候，能拿到更好的效果？",
        "examples": ["提前几天锁定名额", "开学前两周启动", "避开高峰时段"],
        "failure": "时机对了，但承接能力没跟上",
        "types": ["流程/效率问题", "治理/监督问题"],
    },
    "rhythm": {
        "name": "节奏轴", "family": "时间", "asks": "以什么频率、什么周期推进",
        "question": "把频率或周期改成什么，负担与效果会怎么变？",
        "examples": ["每周一次", "每日推进", "两周一循环", "连续三天"],
        "failure": "频率定得超过执行方的真实承载力",
        "types": ["流程/效率问题", "治理/监督问题"],
    },
    "matching": {
        "name": "对接轴", "family": "对接", "asks": "谁和谁配对才对",
        "question": "把供需撮合关系重排，能消掉多少错配？",
        "examples": ["供需撮合", "按需派单", "错时安排", "专人专岗"],
        "failure": "只撮合不筛选，需求方仍要自己试错",
        "types": ["流程/效率问题", "公共服务/社区"],
    },
    "triage": {
        "name": "分诊轴", "family": "对接", "asks": "先处理谁",
        "question": "把优先级规则改掉，谁被挡住了、谁被提前了？",
        "examples": ["按紧急程度分级", "先处理积压件", "绿色通道"],
        "failure": "分诊标准不可判，一线自己就乱了",
        "types": ["公共服务/社区", "流程/效率问题"],
    },
    "budget": {
        "name": "预算轴", "family": "资源", "asks": "钱从哪来、花在哪",
        "question": "钱和人怎么重新配，能撑住什么规模？",
        "examples": ["专项经费", "分摊出资", "削减范围", "分批启动"],
        "failure": "方案超出承载量，落地时断供",
        "types": ["公共服务/社区", "定价/商业模式"],
    },
    "manpower": {
        "name": "人力轴", "family": "资源", "asks": "谁来干、怎么排班",
        "question": "谁来承担、每人多少，能撑多久？",
        "examples": ["值班表", "兼职人手", "外包部分环节"],
        "failure": "人力安排没有备份，人一走就停",
        "types": ["机制/制度设计", "公共服务/社区"],
    },
    "scope": {
        "name": "范围轴", "family": "资源", "asks": "做多大",
        "question": "把规模缩小或挪个范围，能换来什么？",
        "examples": ["先做两个班", "限定一个楼栋", "只做一个品类"],
        "failure": "范围缩小了，但关键配套没跟着缩",
        "types": ["治理/监督问题", "活动/方案设计"],
    },
    "pilot": {
        "name": "试点轴", "family": "兜底", "asks": "怎么先小范围验证",
        "question": "先在多小的范围试、试多久、用什么判据扩？",
        "examples": ["两周试点", "一个班先试", "AB 两组对比"],
        "failure": "试点没有预先写死的推广判据",
        "types": ["治理/监督问题", "机制/制度设计"],
    },
    "fallback": {
        "name": "兜底轴", "family": "兜底", "asks": "错了怎么办",
        "question": "出问题时退到哪一步、谁来接手？",
        "examples": ["止损条件", "回退方案", "人工接手", "容错期"],
        "failure": "只有成功路径",
        "types": ["机制/制度设计", "流程/效率问题"],
    },
    "exit": {
        "name": "退出轴", "family": "兜底", "asks": "什么时候该停",
        "question": "在什么条件下承认这条路走不通并退出？",
        "examples": ["三个月无效果则停", "退出免罚", "到期不续"],
        "failure": "只写怎么开始，不写怎么结束",
        "types": ["定价/商业模式", "治理/监督问题"],
    },
    "beneficiary": {
        "name": "受益方轴", "family": "视角", "asks": "谁真正受益",
        "question": "把最容易被落下的人摆到台面上重设计，会怎么变？",
        "examples": ["给不爱发言的人开口子", "给数字不熟练的人留人工通道"],
        "failure": "只照顾最方便服务的那类人",
        "types": ["公共服务/社区", "定价/商业模式"],
    },
    "costbearer": {
        "name": "代价承担方轴", "family": "视角", "asks": "代价落在谁头上",
        "question": "把成本转嫁给谁才成立，转嫁了还成不成立？",
        "examples": ["把代价转给商家", "由服务者承担", "由机构承担"],
        "failure": "转嫁了成本，但那个承担方有否决权",
        "types": ["定价/商业模式", "机制/制度设计"],
    },
    "future": {
        "name": "未来状态轴", "family": "视角", "asks": "三个月后要变成什么样",
        "question": "以终态为目标倒推，现在该做什么？",
        "examples": ["以习惯形成为目标倒推", "以自运转为目标"],
        "failure": "终态没定，路径无从比较",
        "types": ["流程/效率问题", "活动/方案设计"],
    },
    "reverse": {
        "name": "逆向轴", "family": "反向", "asks": "能不能反着做",
        "question": "把默认做法倒过来，能得到什么？",
        "examples": ["先收钱再服务", "先不掏钱再留住", "让用户先迈一小步"],
        "failure": "逆向了，但没人愿意接受那个反直觉的代价",
        "types": ["定价/商业模式", "流程/效率问题"],
    },
    "removal": {
        "name": "减法轴", "family": "反向", "asks": "砍掉哪一步",
        "question": "去掉哪个环节，事情反而更好？",
        "examples": ["取消建档", "去掉中间转手", "合并审批"],
        "failure": "砍掉的环节其实是必要的兜底",
        "types": ["流程/效率问题", "机制/制度设计"],
    },
    "default": {
        "name": "默认选项轴", "family": "反向", "asks": "让哪个选项变成默认",
        "question": "把默认设置改成什么，不用提醒也会那样？",
        "examples": ["默认开启提醒", "默认免填单", "默认走人工"],
        "failure": "默认改了，但用户根本找不到设置在哪",
        "types": ["流程/效率问题", "机制/制度设计"],
    },
    "precedent": {
        "name": "先例轴", "family": "对照", "asks": "有没有现成的成熟做法",
        "question": "别的场景里已经跑通了什么，能不能搬过来？",
        "examples": ["抄现成的行业做法", "复用别的城市的方案"],
        "failure": "搬来的做法水土不服",
        "types": ["活动/方案设计", "公共服务/社区"],
    },
    "comparative": {
        "name": "比较轴", "family": "对照", "asks": "跟什么比才公平",
        "question": "和哪个参照物比，才能看出这方案到底好不好？",
        "examples": ["与现状比", "与隔壁楼栋比"],
        "failure": "参照物选得对自己有利",
        "types": ["治理/监督问题", "定价/商业模式"],
    },
}

TYPE_AXES = {t: v["axes"] for t, v in TASK_TYPES.items()}
TYPE_BAN = {t: v["ban"] for t, v in TASK_TYPES.items()}


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def detect_type(task: str):
    t = _norm(task)
    scores = {}
    for name, spec in TASK_TYPES.items():
        sc = 0.0
        for sig in spec["signals"]:
            if _norm(sig) in t:
                sc += 2.0
        for other, ospec in TASK_TYPES.items():
            if other == name:
                continue
            for sig in ospec["signals"]:
                if len(_norm(sig)) >= 3 and _norm(sig) in t:
                    sc -= 0.3
        scores[name] = round(sc, 2)
    order = list(TASK_TYPES.keys())
    best = max(order, key=lambda k: (scores[k], -order.index(k)))
    return best, {k: v for k, v in sorted(scores.items(), key=lambda kv: -kv[1])}


# ── 任务特异证据必须压过类型先验，否则检索会退化成"按类型返回固定几条" ──
# 中文没有分词器 ⇒ 用「字符 n-gram 重叠」做匹配：
#   ① 任务串的所有 2-4 字 n-gram，逐个看是否出现在某条轴的描述文本里
#   ② 只保留「极大匹配」（"读书节" 命中就不再单独计 "读书"）避免重复计分
#   ③ 用轴库自身 IDF 降权通用词（到处都是的"活动""设计"信息量低）
#   ④ 类型先验只作小幅加成（先验，不是结论）

# 虚词/高频功能字：中文复合词几乎不以这些字开头 ⇒ 用作 n-gram 过滤
_STOP_HEAD = set("的了和与在是把给让做要会能为对从到不也都就还很更最你我他她它这那之其所以及或等中上下里外前后时候样什么怎么如何请需要可以应该必须再又只把被过起来去成当向朝比跟同各每本该种类项条张个些么如民性地得着说做想看问给找回来去上下进出内外新大小多少高低快慢轻重真假好坏新老早晚" )


def _axis_fields(ax, aid):
    return {
        "name": _norm(ax["name"]),
        "examples": _norm("".join(ax["examples"])),
        "keywords": _norm(KEYWORDS.get(aid, "")),
    }


_FW = {"keywords": 2.4, "examples": 1.6, "name": 0.8}
_AXFIELDS = {aid: _axis_fields(ax, aid) for aid, ax in AXES.items()}


def _ngrams(s: str, lo: int = 2, hi: int = 4):
    seen = set()
    for n in range(lo, hi + 1):
        for i in range(len(s) - n + 1):
            g = s[i:i + n]
            if g in seen:
                continue
            seen.add(g)
            if g[0] in _STOP_HEAD:          # 虚词开头 ⇒ 丢掉
                continue
            yield g


_DF = {}
for _f in _AXFIELDS.values():
    for _g in set(_ngrams("".join(_f.values()))):
        _DF[_g] = _DF.get(_g, 0) + 1

# 脚手架词自曝：出现在 ≥2 条轴的【通用语气字段】(asks/question/failure) 里的词组
# 说明它是"提问模板的措辞"而不是"任务内容"，大幅降权。
_DF_GENERIC = {}
for _f in _AXFIELDS.values():
    for _g in set(_ngrams(_f["keywords"] + _f["examples"] + _f["name"])):
        _DF_GENERIC[_g] = _DF_GENERIC.get(_g, 0) + 1
_SCAFFOLD_DF = 2
SCAFFOLD_PENALTY = 0.12
_N_AXES = max(len(AXES), 1)


def _idf(g: str) -> float:
    import math
    return math.log(_N_AXES / max(_DF.get(g, 1), 1)) + 1.0


def score_axes(task: str, ttype: str):
    t = _norm(task)
    task_grams = set(_ngrams(t))
    type_axes = TYPE_AXES.get(ttype, [])
    out = []
    for aid, ax in AXES.items():
        fields = _AXFIELDS[aid]
        ev, evidence = 0.0, []
        for fname, ftext in fields.items():
            matched = [g for g in task_grams if g in ftext]
            maximal = [g for g in matched
                       if not any(g != m and g in m for m in matched)]
            if not maximal:
                continue
            w = sorted(((len(g) - 1) * _idf(g) * (SCAFFOLD_PENALTY if _DF_GENERIC.get(g, 0) >= _SCAFFOLD_DF else 1.0), g)
                       for g in maximal)[-3:]
            ev += _FW[fname] * sum(x for x, _ in w)
            evidence += [g for _, g in w]
        prior = 0.8 if aid in type_axes else 0.0
        out.append({"id": aid, "score": round(prior + ev, 2), "hits": round(ev, 2),
                    "type_prior": prior, "evidence": evidence[:6], **ax})
    out.sort(key=lambda d: (-d["score"], d["id"]))
    return out


def pick(task: str, ttype: str, topk: int = 6, ban=None):
    """家族多样性重排的 top-k：每轮先从"还没用过的家族"里挑最好的。"""
    ban = set(ban or [])
    ranked = [a for a in score_axes(task, ttype) if a["id"] not in ban]
    chosen, used_fam = [], set()
    pool = list(ranked)
    while pool and len(chosen) < topk:
        fresh = [a for a in pool if a["family"] not in used_fam]
        pickd = max(fresh or pool, key=lambda d: (d["score"], -ord(d["id"][0])))
        chosen.append(pickd)
        used_fam.add(pickd["family"])
        pool.remove(pickd)
    return chosen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--type", default="")
    ap.add_argument("--topk", type=int, default=6)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.type:
        ttype, scores = args.type, {}
    else:
        ttype, scores = detect_type(args.task)
    ranked = score_axes(args.task, ttype)
    ban = TYPE_BAN.get(ttype, [])
    top = [r for r in ranked if r["id"] not in ban][: args.topk]

    if args.json:
        print(json.dumps({"type": ttype, "ban": [{"id": b, **AXES[b]} for b in ban],
                          "candidates": [{k: r[k] for k in ("id", "name", "asks", "question", "examples", "failure", "score")} for r in top]},
                         ensure_ascii=False, indent=2))
        return 0

    print(f"# 任务类型判定：{ttype}")
    if scores:
        print("（类型信号分：" + "、".join(f"{k} {v:g}" for k, v in scores.items() if v) + "）")
    print("\n## 禁忌轴（该类型下不成立，不许用）")
    if ban:
        for b in ban:
            print(f"- **{AXES[b]['name']}**（{b}）——{AXES[b]['asks']}；典型失败：{AXES[b]['failure']}")
    else:
        print("- （无）")
    print(f"\n## 候选轴（按相关度，最多 {args.topk} 条）")
    for r in top:
        print(f"\n### {r['name']}（{r['id']}｜相关度 {r['score']}｜家族：{r['family']}）")
        print(f"- 它在问：{r['asks']}")
        print(f"- 追问：{r['question']}")
        print(f"- 典型做法：{'、'.join(r['examples'])}")
        print(f"- 典型失败：{r['failure']}")
    print("\n## 用法提醒")
    print("- 这些是起点：选中后必须改写成本题的具体动作（照抄轴名等于没改）。")
    print("- 写不出具体动作 ⇒ 这条轴在本题不成立，换一条。")
    print("- 每条轴都要写代价；没有代价的轴会互相重合。")
    print("- 判据：这条轴换到另一道题上也照样成立 ⇒ 它不是轴，是套话。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ── v3 修订版用的「体检清单」：只给**过程性/边界性**维度，不给内容性维度 ──
# 为什么不给内容性维度：内容维度（内容/关系/激励/费用/载体/规则/问责…）
# 恰好就是任务金标轴所捕捉的那些维度 ⇒ 给了等于交答案。
# 过程性维度（先小范围验证/什么时候该停/错了怎么办/代价落在谁头上…）
# 是"怎么把事做起来"的维度，与任务内容基本正交 ⇒ 查漏有价值、泄题风险低。
# ★ 词面不相交这件事由 check_axis_leak.py 机械保证（清单用的就是轴库里的词）。
PROCESS_DIMENSIONS = [
    "pilot", "exit", "fallback", "costbearer", "beneficiary", "reverse",
    "removal", "default", "precedent", "comparative", "rhythm", "timing",
]


def checklist(task: str = "", k: int = 12):
    """返回体检清单文本（维度名 + 它在问什么 + 典型失败）。

    不含关键词（keywords）与示例（examples）—— 只给"维度名 + 提问 + 失败模式"，
    因为那三样才是"提醒"，而关键词/示例会带来词面命中（= 泄题风险）。
    """
    lines = []
    for aid in PROCESS_DIMENSIONS[:k]:
        ax = AXES[aid]
        lines.append(f"- {ax['name']}（{aid}）：{ax['asks']}｜典型失败：{ax['failure']}")
    return "\n".join(lines)
