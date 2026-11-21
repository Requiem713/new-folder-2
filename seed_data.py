"""演示数据一键灌入（维护人：D）。

用法：python seed_data.py

做四件事：
  1. 建表（db.init_db）
  2. 灌入 15 个归类抽屉（data/chapters.json）
  3. 灌入 30 条错题，并通过 knowledge.find_or_create 让具体知识点"长出来"
     🔴 不人工穷举知识点库 —— 每个知识点都是被错题带出来的
  4. 灌入练习记录，让掌握度分布刻意有规律（排行榜才看得出效果）

⚠️ 分层规矩：本文件不写 SQL、不碰 sqlite3，一律调 app/db.py 与 app/knowledge.py。

分布设计（对应 PROJECT_PLAYBOOK 第九节与 issues.md 第 11 条）：
    2 个知识点落在 ~31%（未掌握）
    2 个知识点落在 57%~60%（基本掌握）
    2 个知识点落在 75%~92%（已掌握）
    1 个知识点只练 2 次（样本不足，用来验证"不霸占最薄弱榜首"）
"""

from __future__ import annotations

import json
import os
import random
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

CHAPTER_FILE = os.path.join(ROOT, "data", "chapters.json")
RANDOM_SEED = 42

# (知识点, 章节, 难度, 错因, 题干, 学生答案, 正确答案)
DEMO_WRONG_QUESTIONS = [
    # --- 洛必达法则（刻意做得差：未掌握）---
    ("洛必达法则", "ch_mean_value", "medium", "calculation_error",
     "求 lim(x→0) (sin x - x)/x^3", "0", "-1/6"),
    ("洛必达法则", "ch_mean_value", "medium", "calculation_error",
     "求 lim(x→0) (e^x - 1 - x)/x^2", "0", "1/2"),
    ("洛必达法则", "ch_mean_value", "easy", "concept_confusion",
     "求 lim(x→∞) x/sin x", "1", "不存在（|x/sin x| 无界，不满足洛必达前提）"),
    ("洛必达法则", "ch_mean_value", "easy", "calculation_error",
     "求 lim(x→0) (1 - cos x)/x^2", "0", "1/2"),
    ("洛必达法则", "ch_mean_value", "easy", "calculation_error",
     "求 lim(x→1) ln x/(x - 1)", "0", "1"),
    # --- 分部积分法（也差：未掌握）---
    ("分部积分法", "ch_indefinite_integral", "medium", "method_wrong",
     "计算 ∫ x·e^x dx", "x·e^x + C", "x·e^x - e^x + C"),
    ("分部积分法", "ch_indefinite_integral", "medium", "method_wrong",
     "计算 ∫ x·cos x dx", "x·sin x + C", "x·sin x + cos x + C"),
    ("分部积分法", "ch_indefinite_integral", "medium", "concept_confusion",
     "计算 ∫ ln x dx", "1/x + C", "x·ln x - x + C"),
    ("分部积分法", "ch_indefinite_integral", "hard", "calculation_error",
     "计算 ∫ x^2·ln x dx", "x^3/3 · 1/x + C", "x^3/3·ln x - x^3/9 + C"),
    ("分部积分法", "ch_indefinite_integral", "hard", "method_wrong",
     "计算 ∫ e^x·sin x dx", "e^x·sin x/2 + C", "e^x(sin x - cos x)/2 + C"),
    # --- 泰勒公式（中等：基本掌握）---
    ("泰勒公式", "ch_mean_value", "medium", "incomplete",
     "求 e^x 在 x=0 处的三阶泰勒展开", "1 + x + x^2",
     "1 + x + x^2/2 + x^3/6 + o(x^3)"),
    ("泰勒公式", "ch_mean_value", "hard", "calculation_error",
     "用泰勒公式求 lim(x→0) (cos x - 1 + x^2/2)/x^4", "0", "1/24"),
    ("泰勒公式", "ch_mean_value", "easy", "incomplete",
     "求 ln(1+x) 在 x=0 处展开到 x^3", "x - x^2/2",
     "x - x^2/2 + x^3/3 + o(x^3)"),
    ("泰勒公式", "ch_mean_value", "easy", "concept_confusion",
     "泰勒展开的余项有什么作用", "表示误差可以忽略",
     "控制截断误差、判断展开精度与收敛阶"),
    # --- 定积分的换元法（中等偏上）---
    ("定积分的换元法", "ch_definite_integral", "medium", "calculation_error",
     "计算 ∫(0→1) x·e^{x^2} dx", "e - 1", "(e - 1)/2"),
    ("定积分的换元法", "ch_definite_integral", "medium", "calculation_error",
     "计算 ∫(0→π/2) sin^3 x dx", "1", "2/3"),
    ("定积分的换元法", "ch_definite_integral", "easy", "concept_confusion",
     "计算 ∫(0→2) |x - 1| dx", "0", "1"),
    ("定积分的换元法", "ch_definite_integral", "medium", "calculation_error",
     "计算 ∫(1→e) ln x / x dx", "1", "1/2"),
    # --- 正项级数审敛法（最好：已掌握）---
    ("正项级数审敛法", "ch_series", "easy", "concept_confusion",
     "判断级数 Σ 1/n^(3/2) 的敛散性", "发散", "收敛（p 级数，p = 3/2 > 1）"),
    ("正项级数审敛法", "ch_series", "easy", "concept_confusion",
     "判断级数 Σ 1/n 的敛散性", "收敛", "发散（调和级数）"),
    ("正项级数审敛法", "ch_series", "medium", "method_wrong",
     "判断级数 Σ 1/(n^2 + n) 的敛散性", "发散",
     "收敛（拆成 1/n - 1/(n+1)，部分和为 1 - 1/(n+1)）"),
    ("正项级数审敛法", "ch_series", "hard", "method_wrong",
     "判断级数 Σ (n/(2n+1))^n 的敛散性", "发散", "收敛（根值法，极限为 1/2 < 1）"),
    ("正项级数审敛法", "ch_series", "medium", "method_wrong",
     "判断级数 Σ sin(1/n) 的敛散性", "收敛", "发散（与 Σ 1/n 同阶）"),
    ("正项级数审敛法", "ch_series", "hard", "method_wrong",
     "判断级数 Σ 1/(n·ln n) 的敛散性", "收敛", "发散（积分判别法）"),
    # --- 偏导数的几何意义（好：已掌握）---
    ("偏导数的几何意义", "ch_multivariable_diff", "easy", "calculation_error",
     "z = x^2 + y^2 在点 (1,1) 处对 x 的偏导数", "4", "2"),
    ("偏导数的几何意义", "ch_multivariable_diff", "medium", "calculation_error",
     "f(x,y) = x^2·y + sin y，求 f_xy", "2x", "2x + cos y"),
    ("偏导数的几何意义", "ch_multivariable_diff", "medium", "concept_confusion",
     "偏导数存在是否一定可微", "一定可微", "不一定，还需增量比极限为零"),
    # --- 格林公式（只练过 2 次：样本不足）---
    ("格林公式", "ch_line_surface_integral", "medium", "method_wrong",
     "用格林公式计算 ∮(x dy - y dx)，L 为单位圆正向", "0", "2π"),
    ("格林公式", "ch_line_surface_integral", "easy", "incomplete",
     "格林公式成立需要什么条件", "任意闭曲线都成立",
     "L 为分段光滑闭曲线、P/Q 在闭区域上有连续偏导、L 取正向"),
    ("格林公式", "ch_line_surface_integral", "hard", "method_wrong",
     "计算 ∮(x^2 - y)dx + (x + y^2)dy，L 为单位圆正向", "0", "2π"),
]

# (知识点, 练习总数, 做对次数, 难度配比)
# 掌握度 = 基础正确率 × 难度加权 × 时间衰减（截断 100）
DEMO_PRACTICE_PLAN = [
    ("洛必达法则", 10, 3, {"easy": 8, "medium": 2}),      # 30% × 1.05 → 31.5 未掌握
    ("分部积分法", 10, 3, {"easy": 6, "medium": 4}),      # 30% × 1.05 → 31.5 未掌握
    ("泰勒公式", 10, 5, {"medium": 5, "hard": 5}),        # 50% × 1.15 → 57.5 基本掌握
    ("定积分的换元法", 10, 6, {"easy": 10}),              # 60% × 1.00 → 60.0 基本掌握
    ("正项级数审敛法", 10, 8, {"medium": 6, "hard": 4}),  # 80% × 1.15 → 92.0 已掌握
    ("偏导数的几何意义", 8, 6, {"easy": 8}),              # 75% × 1.00 → 75.0 已掌握
    ("格林公式", 2, 1, {"medium": 2}),                    # 练过 2 次 → 样本不足
]


def _load_chapters() -> list[dict]:
    with open(CHAPTER_FILE, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _difficulty_list(spec: dict) -> list[str]:
    """把 {'easy': 8, 'medium': 2} 展开成 ['easy', ...] 并按种子打乱。"""
    values: list[str] = []
    for name, count in spec.items():
        values.extend([name] * int(count))
    return values


def main() -> int:
    try:
        from app import db, knowledge
    except Exception as exc:  # 数据层还没落地时给明确指引，而不是丢一串 traceback
        print("🔴 数据层还没就绪：app/db.py 或 app/knowledge.py 不存在（C₁ 负责）。")
        print(f"   具体错误：{exc}")
        print("   等 C₁ 合并后重跑本脚本即可；界面现在用的是 app/stubs.py 的假数据。")
        return 2

    db.init_db()

    # 幂等：优先用数据层提供的 reset，避免第二次跑出 UNIQUE 冲突 / 重复数据
    reset = getattr(db, "reset_demo_data", None)
    if callable(reset):
        reset()
    elif db.wrong_question_count() > 0:
        print(f"🔴 库里已有 {db.wrong_question_count()} 条错题，为避免重复灌入已停止。")
        print("   可选做法：① 等 C₁ 提供 reset_demo_data()；② 手动删除 data/app.db 后重跑。")
        return 3

    chapters = _load_chapters()
    db.insert_chapters(chapters)
    print(f"✅ 章节：灌入 {len(chapters)} 个归类抽屉")

    # 知识点只能从错题里长出来：逐个调 find_or_create，由它查重后复用或新建
    kp_ids: dict[str, str] = {}
    for kp_name, chapter_id, *_rest in DEMO_WRONG_QUESTIONS:
        if kp_name not in kp_ids:
            kp_ids[kp_name] = knowledge.find_or_create(kp_name, chapter_id, context="seed_data 演示数据")
    print(f"✅ 知识点：{len(kp_ids)} 个（全部由错题带出，未人工穷举）")

    rng = random.Random(RANDOM_SEED)
    order = list(DEMO_WRONG_QUESTIONS)
    rng.shuffle(order)
    for kp_name, chapter_id, difficulty, error_type, question, student_answer, correct_answer in order:
        db.insert_wrong_question(
            {
                "question_text": question,
                "student_answer": student_answer,
                "correct_answer": correct_answer,
                "solution_steps": ["对照定义与适用条件", "按标准解法重算一遍", "检查符号与取限"],
                "knowledge_ids": [kp_ids[kp_name]],
                "new_concepts": [],
                "difficulty": difficulty,
                "error_type": error_type,
                "source": "seed",
            }
        )
    print(f"✅ 错题：灌入 {len(order)} 条（知识点已挂载）")

    practice_total = 0
    for kp_name, total, correct, mix in DEMO_PRACTICE_PLAN:
        kp_id = kp_ids.get(kp_name)
        if not kp_id:
            print(f"⚠️ 跳过练习记录：找不到知识点 {kp_name}")
            continue
        flags = [True] * correct + [False] * (total - correct)
        rng.shuffle(flags)
        difficulties = _difficulty_list(mix)
        rng.shuffle(difficulties)
        for index, is_correct in enumerate(flags):
            difficulty = difficulties[index % len(difficulties)] if difficulties else "easy"
            db.log_practice(kp_id, is_correct, difficulty=difficulty)
            practice_total += 1
    print(f"✅ 练习记录：{practice_total} 条（分布刻意安排，排名能看出规律）")

    # 收尾：报最薄弱前三，方便一眼确认分布对不对
    weakest: list = []
    for module_name in ("app.profile", "app.db"):
        try:
            module = __import__(module_name, fromlist=["weak_points"])
            weakest = module.weak_points(3) or []
            break
        except Exception:
            continue

    print("\n📊 当前最薄弱前三：")
    if not weakest:
        print("   （取不到 weak_points 结果，可能数据层还没实现该函数）")
    for index, item in enumerate(weakest, start=1):
        name = item.get("kp_name") or item.get("name") or item
        mastery = item.get("mastery", item.get("掌握度"))
        print(f"   {index}. {name}　掌握度 {mastery}")

    print("\n完成：python seed_data.py 可重复运行（内部会先清空演示数据）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
