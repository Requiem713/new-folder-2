"""学习辅导 AI 助教 · 界面入口（维护人：D）。

分层红线（硬性，见 AGENTS.md 第四节第 8 条）：
🔴 本文件不含业务逻辑、不发网络请求、不写 SQL、不引 HTML/CSS/JS 或前端框架。
   它只做三件事：调函数拿数据 → 用 Streamlit 渲染 → 把用户输入回传给函数。

换桩的唯一位置是下面的 IMPORT 区块：
    现在   from app.stubs import ...
    将来   from app.qa import answer；from app.profile import mastery_table …
🔴 换桩判据只有一条：**能 pull 到实现，且函数签名与 docs/interfaces.md 一致**。
   两条缺一就继续用桩，不许猜别人的签名。

状态约定（Streamlit 每次交互都会从头重跑本文件，所以状态一律放 session_state）：
    messages     对话历史。🔴 开场白只做渲染、不进这里（否则 messages 以 assistant
                 开头，模型的 chat template 会报 "No user query found in messages"）
    style        讲解风格（简洁 / 详细）
    intake_draft ②页识别出来、尚未确认入库的草稿
"""

from __future__ import annotations

import sys

import streamlit as st

# ---------------------------------------------------------------------------
# IMPORT 区块 —— 换桩时只改这一块
# ---------------------------------------------------------------------------
from app.stubs import (
    all_knowledge_points,
    analyze_image,
    analyze_text,
    answer,
    commit,
    is_configured,
    list_subject_topics,
    missing_config_keys,
    recent_wrong_questions,
)

# ---------------------------------------------------------------------------

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

APP_TITLE = "学习辅导 AI 助教 · 高等数学"
APP_CAPTION = "把做错的题沉淀成知识点画像，再按薄弱环节讲解与练习。"

# 🔴 开场白：只做页面渲染，绝不写进 session_state["messages"]
OPENING = (
    "你好，我是**高等数学**学习助手。\n\n"
    "- 想弄懂概念：直接问我，例如「洛必达法则什么时候能用」\n"
    "- 想整理错题：去「② 错题录入」，手输或拍照都行\n"
    "- 想看看薄弱点：去「③ 掌握度分析」\n\n"
    "本系统只覆盖高等数学范围内的内容。"
)

# 展示层映射：数据库与 JSON 里永远存英文值，只有这里转中文（契约第七节要求）
DIFFICULTY_CN = {"easy": "易", "medium": "中", "hard": "难"}
DIFFICULTY_EN = {v: k for k, v in DIFFICULTY_CN.items()}
ERROR_TYPE_CN = {
    "concept_confusion": "概念混淆",
    "calculation_error": "计算失误",
    "method_wrong": "方法选错",
    "incomplete": "审题不全",
    "unknown": "判不出",
}
ERROR_TYPE_EN = {v: k for k, v in ERROR_TYPE_CN.items()}


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------


def _init_state() -> None:
    """初始化会话状态。只在键不存在时写入，避免覆盖用户当前输入。"""
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("style", "简洁")
    st.session_state.setdefault("intake_draft", None)


def _draft_to_dict(draft) -> dict:
    """把 IntakeDraft 统一成 dict。

    🔴 契约没规定 IntakeDraft 是 dataclass 还是 dict，B 两种都可能给。
       这里两种都吃，换真实现时表单代码不用改。
    """
    if draft is None:
        return {}
    if isinstance(draft, dict):
        return dict(draft)
    if hasattr(draft, "__dict__"):
        return dict(draft.__dict__)
    fields = (
        "question_text",
        "student_answer",
        "correct_answer",
        "solution_steps",
        "knowledge_ids",
        "new_concepts",
        "difficulty",
        "error_type",
        "confidence",
        "source",
        "degraded",
        "note",
    )
    return {name: getattr(draft, name, None) for name in fields}


def _kp_name_to_id() -> dict:
    """知识点 名字 → id。下拉框只显示名字，回传时换成 id（🔴 界面不自由输入新名字）。"""
    return {kp["name"]: kp["id"] for kp in all_knowledge_points()}


def _kp_id_to_name() -> dict:
    return {kp["id"]: kp["name"] for kp in all_knowledge_points()}


def _pick(mapping: dict, *keys, default=0):
    """指标卡的容错取值：桩用英文键，未来实现可能改成中文键，两种都认。"""
    for key in keys:
        if key in mapping:
            return mapping[key]
    return default


# ---------------------------------------------------------------------------
# 侧边栏
# ---------------------------------------------------------------------------


def render_sidebar() -> None:
    with st.sidebar:
        st.header("设置")
        st.radio(
            "讲解风格",
            options=["简洁", "详细"],
            key="style",
            horizontal=True,
            help="详细版会补充适用条件与更多推导；两版都保持四段结构。",
        )

        st.divider()
        st.subheader("模型配置")
        missing = missing_config_keys()
        if missing:
            st.warning("缺少配置：" + "、".join(missing) + "\n\n在项目根目录 `.env` 里填写后重启应用。")
        else:
            st.success("模型配置已就绪")

        st.divider()
        if st.button("清空对话", width="stretch"):
            st.session_state["messages"] = []
            st.rerun()

        with st.expander("本系统覆盖的知识点（桩数据）"):
            for topic in list_subject_topics():
                st.write("- " + topic)


# ---------------------------------------------------------------------------
# ① 知识点问答
# ---------------------------------------------------------------------------


def render_qa_tab() -> None:
    st.subheader("① 知识点问答")
    st.caption("回答固定四段：一句话定义 / 通俗解释 / 具体例子 / 常见误区。")

    # 开场白：只渲染，不进历史
    with st.chat_message("assistant"):
        st.markdown(OPENING)

    for message in st.session_state["messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    question = st.chat_input("问一个高等数学概念，例如：洛必达法则什么时候能用？", key="qa_input")
    if not question:
        return

    # 先把"本轮之前"的历史取出来，再追加本轮提问 —— 传给模型的顺序才不会乱
    history = [dict(m) for m in st.session_state["messages"]]
    st.session_state["messages"].append({"role": "user", "content": question})

    if missing_config_keys():
        reply = (
            "还不能回答：模型服务还没配置。\n\n"
            "请在项目根目录 `.env` 里填好 **"
            + "、".join(missing_config_keys())
            + "** 三项后重启应用。"
        )
    else:
        try:
            with st.spinner("正在组织回答…"):
                reply = answer(question, "高等数学", st.session_state["style"], history=history)
        except Exception as exc:  # noqa: BLE001 - 界面层只负责优雅降级，不吞细节
            reply = (
                "这次没能拿到回答，但你的问题已经保留了。\n\n"
                f"- 可能原因：模型服务不可用、密钥无效或超时\n- 详情：`{exc}`"
            )

    st.session_state["messages"].append({"role": "assistant", "content": reply})
    st.rerun()


# ---------------------------------------------------------------------------
# ② 错题录入
# ---------------------------------------------------------------------------


def _flash(message: str, kind: str = "success") -> None:
    """跨 st.rerun() 的一次性提示。rerun 会清掉本次渲染的输出，所以先存后显。"""
    st.session_state["flash"] = {"message": message, "kind": kind}


def _render_flash() -> None:
    flash = st.session_state.pop("flash", None)
    if not flash:
        return
    getattr(st, flash.get("kind", "success"), st.success)(flash["message"])


def _run_intake(mode, question_text, student_answer, correct_answer, uploaded, extra_note):
    """调 B 的识别函数拿草稿。失败不抛给页面，转成 degraded 草稿让人手工填。"""
    try:
        if mode == "上传照片":
            if uploaded is None:
                st.warning("先选一张 jpg / png 图片。")
                return None
            return analyze_image(uploaded.getvalue(), extra_note)
        if not question_text.strip():
            st.warning("题干不能为空。")
            return None
        return analyze_text(question_text, student_answer, correct_answer)
    except Exception as exc:  # noqa: BLE001 - 识别失败要走降级路径，不能中断主流程
        return {
            "degraded": True,
            "source": "image" if mode == "上传照片" else "text",
            "note": f"识别失败：{exc}",
            "knowledge_ids": [],
            "solution_steps": [],
        }


def _render_recent_intake() -> None:
    """最近录入列表：编号 / 题干摘要 / 知识点 / 错因 / 时间。"""
    st.divider()
    st.markdown("**最近录入的错题**")
    rows = recent_wrong_questions(20)
    if not rows:
        st.caption("还没有记录。")
        return
    id_to_name = _kp_id_to_name()
    table = [
        {
            "编号": row.get("id"),
            "题干摘要": (row.get("question_text") or "")[:36],
            "知识点": "、".join(id_to_name.get(kp, kp) for kp in (row.get("knowledge_ids") or [])),
            "错因": ERROR_TYPE_CN.get(row.get("error_type"), row.get("error_type")),
            "难度": DIFFICULTY_CN.get(row.get("difficulty"), row.get("difficulty")),
            "录入时间": row.get("created_at"),
        }
        for row in rows
    ]
    st.dataframe(table, width="stretch", hide_index=True)


def render_intake_tab() -> None:
    st.subheader("② 错题录入")
    st.caption("识别结果只是草稿 —— **点「确认入库」才写数据库**；识别失败可以直接手工填。")
    _render_flash()

    mode = st.radio("录入方式", ["手输题干", "上传照片"], horizontal=True, key="intake_mode")

    question_text = student_answer = correct_answer = extra_note = ""
    uploaded = None

    with st.form("intake_input_form", clear_on_submit=False):
        if mode == "手输题干":
            question_text = st.text_area("题干", height=120, key="intake_q")
            student_answer = st.text_input("我的答案", key="intake_sa")
            correct_answer = st.text_input("参考答案（可选）", key="intake_ca")
        else:
            uploaded = st.file_uploader("题目照片", type=["jpg", "jpeg", "png"], key="intake_img")
            extra_note = st.text_input("补充说明（可选）", key="intake_note")
        submitted = st.form_submit_button("识别并归类", type="primary")

    if submitted:
        draft = _run_intake(mode, question_text, student_answer, correct_answer, uploaded, extra_note)
        if draft is not None:
            st.session_state["intake_draft"] = draft
            st.rerun()

    draft = _draft_to_dict(st.session_state.get("intake_draft"))
    if not draft:
        _render_recent_intake()
        return

    if draft.get("degraded"):
        st.warning(
            "模型没能给出可靠结果（" + str(draft.get("note") or "已降级") + "）。"
            "下面是空表单，请手工填写后入库。"
        )

    known_ids = _kp_id_to_name()
    kp_map = _kp_name_to_id()
    default_kps = [known_ids[kp] for kp in (draft.get("knowledge_ids") or []) if kp in known_ids]

    with st.form("intake_confirm_form"):
        st.markdown("**确认并修改识别结果**（每个字段都可以改）")
        edited_question = st.text_area("题干", value=draft.get("question_text") or "", height=120)
        edited_student = st.text_input("我的答案", value=draft.get("student_answer") or "")
        edited_correct = st.text_input("正确答案", value=draft.get("correct_answer") or "")
        edited_steps = st.text_area(
            "解题步骤（每行一步）",
            value="\n".join(draft.get("solution_steps") or []),
            height=140,
        )
        # 🔴 选项只来自数据库现有知识点，不允许自由输入新名字
        edited_kps = st.multiselect("涉及知识点", options=list(kp_map), default=default_kps)

        err_names = list(ERROR_TYPE_EN)
        diff_names = list(DIFFICULTY_EN)
        current_err = ERROR_TYPE_CN.get(draft.get("error_type"), "判不出")
        current_diff = DIFFICULTY_CN.get(draft.get("difficulty"), "中")
        col_err, col_diff = st.columns(2)
        with col_err:
            edited_err = st.selectbox(
                "错因类型", err_names, index=err_names.index(current_err) if current_err in err_names else 4
            )
        with col_diff:
            edited_diff = st.selectbox(
                "难度", diff_names, index=diff_names.index(current_diff) if current_diff in diff_names else 1
            )

        confirmed = st.form_submit_button("确认入库", type="primary")

    if confirmed:
        if not edited_question.strip():
            st.error("题干不能为空，这一次没有入库。")
            return
        payload = {
            "question_text": edited_question.strip(),
            "student_answer": edited_student.strip(),
            "correct_answer": edited_correct.strip(),
            "solution_steps": [s.strip() for s in edited_steps.splitlines() if s.strip()],
            "knowledge_ids": [kp_map[name] for name in edited_kps],
            "new_concepts": draft.get("new_concepts") or [],
            # 🔴 入库永远是英文值，中文只在展示层映射
            "difficulty": DIFFICULTY_EN[edited_diff],
            "error_type": ERROR_TYPE_EN[edited_err],
            "confidence": draft.get("confidence", 0.0),
            "source": draft.get("source", "text"),
            "degraded": bool(draft.get("degraded")),
            "note": draft.get("note"),
        }
        try:
            new_id = commit(payload)
        except Exception as exc:  # noqa: BLE001 - 入库失败要说人话，不能白屏
            st.error(f"入库失败：{exc}")
            return
        st.session_state["intake_draft"] = None
        _flash(f"已入库，编号 #{new_id}")
        st.rerun()

    _render_recent_intake()


# ---------------------------------------------------------------------------
# ③ 掌握度分析
# ---------------------------------------------------------------------------


def render_mastery_tab() -> None:
    st.subheader("③ 掌握度分析")
    st.info("⏳ 第 9 步实现：指标卡 + 最薄弱知识点 + 完整表格 + 正确率图表。")


# ---------------------------------------------------------------------------
# ④ 针对性练习
# ---------------------------------------------------------------------------


def render_practice_tab() -> None:
    st.subheader("④ 针对性练习")
    st.info("⏳ 阶段三实现（加分项）：按薄弱点出题 → 作答 → 判分 → 回写掌握度。")


# ---------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="📘", layout="wide")
    _init_state()

    render_sidebar()

    st.title(APP_TITLE)
    st.caption(APP_CAPTION)

    if not is_configured():
        st.info(
            "模型配置未完成，问答功能暂时只会给出提示。"
            "填写 `.env` 里的 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL 后重启即可。"
        )

    tab_qa, tab_intake, tab_mastery, tab_practice = st.tabs(
        ["① 知识点问答", "② 错题录入", "③ 掌握度分析", "④ 针对性练习"]
    )
    with tab_qa:
        render_qa_tab()
    with tab_intake:
        render_intake_tab()
    with tab_mastery:
        render_mastery_tab()
    with tab_practice:
        render_practice_tab()


main()
