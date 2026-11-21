"""桩函数：队友实现未就绪时，让界面先跑起来（维护人：D）。

🔴 本文件归 D 所有。这里每个函数都与 docs/interfaces.md 里的契约**同名同形状**。
   将来只改 streamlit_app.py 顶部那一个 import 区块，界面代码一行不动。

本文件的三条自律：
- 只返回数据：不读写数据库、不发网络请求、不写磁盘
- 假数据刻意做出「未掌握 / 基本掌握 / 已掌握 / 样本不足」四档，
  好让第③页看到的效果与真实实现一致
- 函数签名必须抄契约，不许自创参数名（否则换真实现时界面要跟着改）

当前仍是桩的函数清单同步维护在 docs/interfaces.md 第九节。
"""

from __future__ import annotations

import json
import os
import random

__all__ = [
    # 模型配置
    "is_configured",
    "missing_config_keys",
    # 问答
    "answer",
    "list_subject_topics",
    # 章节与知识点
    "chapter_candidates",
    "all_knowledge_points",
    # 错题录入
    "analyze_text",
    "analyze_image",
    "commit",
    "recent_wrong_questions",
    "wrong_question_count",
    # 掌握度
    "mastery_table",
    "summary_text",
    "weak_points",
    # 练习
    "build_practice_session",
    "grade",
    "record_result",
]

# ---------------------------------------------------------------------------
# 内部假数据
# ---------------------------------------------------------------------------

_CHAPTERS_FALLBACK = [
    {"id": "ch_function_limit", "name": "函数与极限", "brief": "函数性质、极限、连续性"},
    {"id": "ch_indefinite_integral", "name": "不定积分", "brief": "原函数、换元与分部积分"},
    {"id": "ch_series", "name": "无穷级数", "brief": "审敛法、幂级数、傅里叶级数"},
]

_CHAPTER_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "chapters.json")

_DOTENV_LOADED = False


def _load_chapters() -> list[dict]:
    """读 15 个抽屉。读不到就用 3 条兜底，保证界面永远能起。"""
    try:
        with open(_CHAPTER_FILE, "r", encoding="utf-8") as fh:
            rows = json.load(fh)
        return [{"id": r["id"], "name": r["name"], "brief": r.get("brief", "")} for r in rows]
    except Exception:
        return list(_CHAPTERS_FALLBACK)


_FAKE_KPS = [
    {"id": "kp_001", "name": "洛必达法则", "chapter_id": "ch_mean_value"},
    {"id": "kp_002", "name": "分部积分法", "chapter_id": "ch_indefinite_integral"},
    {"id": "kp_003", "name": "定积分的换元法", "chapter_id": "ch_definite_integral"},
    {"id": "kp_004", "name": "泰勒公式", "chapter_id": "ch_mean_value"},
    {"id": "kp_005", "name": "正项级数审敛法", "chapter_id": "ch_series"},
    {"id": "kp_006", "name": "偏导数的几何意义", "chapter_id": "ch_multivariable_diff"},
    {"id": "kp_007", "name": "格林公式", "chapter_id": "ch_line_surface_integral"},
]

# 假入库存储：只活在进程内存里，重启即清空。真实实现由 intake.commit() 落库。
_STORE: list[dict] = [
    {
        "id": 3,
        "question_text": "求 lim(x->0) (sin x - x) / x^3",
        "knowledge_ids": ["kp_001", "kp_004"],
        "error_type": "calculation_error",
        "difficulty": "medium",
        "created_at": "2026-11-20 21:14",
    },
    {
        "id": 2,
        "question_text": "计算 ∫ x·cos x dx",
        "knowledge_ids": ["kp_002"],
        "error_type": "method_wrong",
        "difficulty": "hard",
        "created_at": "2026-11-20 20:02",
    },
    {
        "id": 1,
        "question_text": "判断级数 Σ 1/(n^2+n) 是否收敛",
        "knowledge_ids": ["kp_005"],
        "error_type": "concept_confusion",
        "difficulty": "easy",
        "created_at": "2026-11-20 19:31",
    },
]


# ---------------------------------------------------------------------------
# 模型配置
# ---------------------------------------------------------------------------


def is_configured() -> bool:
    """三项必填环境变量是否齐全（桩：只看环境变量，不发请求）。"""
    return not missing_config_keys()


def missing_config_keys() -> list[str]:
    """缺哪几项。返回空列表表示齐全。

    真实现（app/llm_client.py）会自己 load_dotenv；这里是桩，也照做一次，
    这样用户只填了 .env、没有导出环境变量时，侧边栏的状态也是准的。
    """
    _load_dotenv_once()
    keys = ["LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"]
    return [k for k in keys if not (os.environ.get(k) or "").strip()]


def _load_dotenv_once() -> None:
    """读项目根目录的 .env（不覆盖已有环境变量）。缺 python-dotenv 或文件时静默跳过。"""
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True
    try:
        from dotenv import load_dotenv

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        load_dotenv(os.path.join(root, ".env"), override=False)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 问答
# ---------------------------------------------------------------------------


def answer(question: str, subject: str, style: str, history=None) -> str:
    """假回答：四段结构，风格差异只体现在第二段长短。"""
    detailed = "详细" in (style or "")
    body = (
        "**【一句话定义】** 这是用来求极限的一条重要法则。\n\n"
        "**【通俗解释】** 当分子分母都趋于 0（或都趋于无穷）时，"
        "可以把两者分别求导后再取极限，用导数之比的极限替代原极限。\n\n"
    )
    if detailed:
        body += (
            "补充：使用前必须确认满足三个条件 —— ① 属于 0/0 或 ∞/∞ 型；"
            "② 分子分母在去心邻域内可导；③ 求导后比值的极限存在（或为无穷）。"
            "缺一条就可能得出错误结论，比如把不该用的题目硬套上去。\n\n"
        )
    body += (
        "**【具体例子】** 求 lim(x→0) sin x / x：分子分母都趋于 0，"
        "求导后得到 lim(x→0) cos x / 1 = 1。\n\n"
        "**【常见误区】** 只在 0/0、∞/∞ 型才能用；求导后极限震荡不存在时不能反推原极限不存在。\n\n"
        f"> 这是桩函数的固定回答（问题：{question}；风格：{style or '简洁'}）。"
    )
    return body


def list_subject_topics() -> list[str]:
    """界面展示"本系统覆盖哪些知识点"。"""
    return [kp["name"] for kp in _FAKE_KPS]


# ---------------------------------------------------------------------------
# 章节与知识点
# ---------------------------------------------------------------------------


def chapter_candidates() -> list[dict]:
    """15 个章节的 id / name / brief —— 唯一允许挂靠的层级（桩：直接读数据文件）。"""
    return _load_chapters()


def all_knowledge_points() -> list[dict]:
    """现有全部知识点，供录入表单的下拉选项。"""
    return [dict(kp) for kp in _FAKE_KPS]


# ---------------------------------------------------------------------------
# 错题录入
# ---------------------------------------------------------------------------


def _fake_draft(question_text: str, student_answer: str, correct_answer: str = "") -> dict:
    return {
        "question_text": question_text or "求 lim(x→0) (sin x - x) / x^3",
        "student_answer": student_answer or "0",
        "correct_answer": correct_answer or "-1/6",
        "solution_steps": [
            "判断类型：分子分母同时趋于 0，属于 0/0 型",
            "对分子分母分别求导：得 (cos x - 1) / (3x^2)",
            "仍为 0/0 型，继续求导：得 -sin x / (6x)",
            "再用一次等价无穷小 sin x ~ x，得到 -1/6",
        ],
        "knowledge_ids": ["kp_001"],
        "new_concepts": [],
        "difficulty": "medium",
        "error_type": "calculation_error",
        "confidence": 0.82,
        "source": "text",
        "degraded": False,
        "note": "桩函数返回的假草稿",
    }


def analyze_text(question_text: str, student_answer: str, correct_answer: str = "") -> dict:
    """文本路径：返回符合契约的假草稿（IntakeDraft 字段）。"""
    return _fake_draft(question_text, student_answer, correct_answer)


def analyze_image(image_bytes: bytes, extra_note: str = "") -> dict:
    """拍照路径：桩不真的识图，按契约返回 degraded 草稿，界面转人工填写。"""
    draft = _fake_draft("", "")
    draft.update(
        {
            "degraded": True,
            "confidence": 0.0,
            "source": "image",
            "note": "桩函数：图片路径未真实现，界面应显示空表单让人手工填"
            + (f"；备注：{extra_note}" if extra_note else ""),
        }
    )
    return draft


def commit(draft, image_path=None) -> int:
    """🔴 用户确认后才落库。桩：写入内存列表并返回新 id。"""
    data = draft if isinstance(draft, dict) else dict(getattr(draft, "__dict__", {}))
    _STORE.insert(
        0,
        {
            "id": max([r["id"] for r in _STORE] or [0]) + 1,
            "question_text": data.get("question_text", ""),
            "knowledge_ids": list(data.get("knowledge_ids") or []),
            "error_type": data.get("error_type", "unknown"),
            "difficulty": data.get("difficulty", "medium"),
            "created_at": _now_text(),
        },
    )
    return _STORE[0]["id"]


def recent_wrong_questions(limit: int = 20) -> list[dict]:
    """最近录入的错题（新→旧）。"""
    return [dict(row) for row in _STORE[:limit]]


def wrong_question_count() -> int:
    """错题总数。"""
    return len(_STORE)


def _now_text() -> str:
    import datetime

    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------------------
# 掌握度
# ---------------------------------------------------------------------------

MASTERY_COLUMNS = [
    "知识点",
    "所属章节",
    "练习数",
    "做对数",
    "基础正确率",
    "难度加权",
    "时间衰减",
    "掌握度",
    "状态",
]


def mastery_table():
    """假掌握度表。列名就是契约里定死的那九列（见 docs/interfaces.md 第一节）。

    数值按「掌握度 = 基础正确率 × 难度加权 × 时间衰减（截断 100）」算好，
    刻意做出四档，方便界面与验收对照。
    """
    import pandas as pd

    rows = [
        # 知识点, 章节, 练习数, 做对数, 基础正确率, 难度加权, 时间衰减, 掌握度, 状态
        ("洛必达法则", "微分中值定理与导数应用", 10, 3, 30.0, 1.00, 1.00, 30.0, "未掌握"),
        ("分部积分法", "不定积分", 12, 4, 33.3, 1.05, 0.90, 31.5, "未掌握"),
        ("定积分的换元法", "定积分", 9, 5, 55.6, 1.00, 1.00, 55.6, "基本掌握"),
        ("泰勒公式", "微分中值定理与导数应用", 8, 5, 62.5, 1.05, 1.00, 65.6, "基本掌握"),
        ("正项级数审敛法", "无穷级数", 10, 8, 80.0, 1.15, 0.90, 82.8, "已掌握"),
        ("偏导数的几何意义", "多元函数微分法", 6, 5, 83.3, 1.00, 1.00, 83.3, "已掌握"),
        ("格林公式", "曲线积分与曲面积分", 2, 1, 50.0, 1.00, 1.00, 50.0, "样本不足"),
    ]
    return pd.DataFrame(rows, columns=MASTERY_COLUMNS)


def summary_text() -> dict:
    """界面顶部指标卡数据。键名固定为英文，便于换真实现时对照契约。"""
    return {
        "wrong_total": len(_STORE),
        "not_mastered": 2,
        "basic": 2,
        "mastered": 2,
        "insufficient": 1,
        "weakest": "洛必达法则",
    }


def weak_points(n: int) -> list[dict]:
    """排除样本不足后掌握度最低的 n 个（供功能④出题用）。"""
    df = mastery_table()
    df = df[df["状态"] != "样本不足"].sort_values("掌握度", ascending=True)
    return [
        {"kp_name": r["知识点"], "chapter": r["所属章节"], "mastery": float(r["掌握度"])}
        for _, r in df.head(n).iterrows()
    ]


# ---------------------------------------------------------------------------
# 练习
# ---------------------------------------------------------------------------

_FAKE_QUESTIONS = [
    {
        "id": "q_demo_01",
        "kp_id": "kp_001",
        "kp_name": "洛必达法则",
        "chapter_id": "ch_mean_value",
        "type": "single_choice",
        "difficulty": "easy",
        "question": "下列极限中，可以直接使用洛必达法则的是：",
        "options": {
            "A": "lim(x→0) sin x / x",
            "B": "lim(x→0) (x + 1) / x",
            "C": "lim(x→0) x·sin(1/x)",
            "D": "lim(x→∞) x·sin x",
        },
        "answer": "A",
        "explanation": "A 是 0/0 型且求导后极限存在；C 求导后震荡，B、D 不是 0/0 或 ∞/∞ 型。",
    },
    {
        "id": "q_demo_02",
        "kp_id": "kp_002",
        "kp_name": "分部积分法",
        "chapter_id": "ch_indefinite_integral",
        "type": "single_choice",
        "difficulty": "medium",
        "question": "计算 ∫ x·e^x dx，结果应为：",
        "options": {
            "A": "x·e^x - e^x + C",
            "B": "x·e^x + e^x + C",
            "C": "(x+1)·e^x + C",
            "D": "e^x / x + C",
        },
        "answer": "A",
        "explanation": "取 u=x, dv=e^x dx，得 x·e^x - ∫e^x dx = x·e^x - e^x + C。",
    },
    {
        "id": "q_demo_03",
        "kp_id": "kp_005",
        "kp_name": "正项级数审敛法",
        "chapter_id": "ch_series",
        "type": "single_choice",
        "difficulty": "hard",
        "question": "级数 Σ 1/n^(3/2) 的敛散性是：",
        "options": {"A": "收敛", "B": "发散", "C": "条件收敛", "D": "无法判断"},
        "answer": "A",
        "explanation": "p 级数 Σ1/n^p 当 p>1 时收敛，此处 p=3/2。",
    },
]


def build_practice_session(count: int):
    """返回 (题目列表, 来源说明)。桩：从固定小题库里循环取。"""
    rng = random.Random(42)
    pool = _FAKE_QUESTIONS * max(1, (count // len(_FAKE_QUESTIONS)) + 1)
    picked = rng.sample(pool, k=min(count, len(pool)))
    return picked, "桩数据：固定小题库（真实实现应由 profile.build_practice_session 选池）"


def grade(item, user_answer) -> bool:
    """客观判分：单项选择按选项编号比较，大小写不敏感。"""
    expected = str((item or {}).get("answer", "")).strip().upper()
    got = str(user_answer or "").strip().upper()
    return bool(expected) and expected == got


def record_result(items, answers) -> list[bool]:
    """判分 + 回写（桩：只返回对错列表，不落库）。"""
    return [grade(it, answers.get(it.get("id"))) for it in items]
