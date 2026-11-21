# 接口契约 · 学习辅导 AI 助教（高等数学）

## 怎么用这个文件

- **接手任务时先读这里**，再打开对应源码。不需要问原作者"你这个函数怎么调"。
- 🔴 改了函数的名字 / 参数 / 返回值 → **必须同一次改动里更新本文件**，
  并把这部分改动单独提交一条：`docs: 更新接口契约（说明变了什么）`
- 契约与代码不一致时，**以代码为准并在群里报告**，不要按错的契约继续开发。
- 🚫 禁止绕过本文件去猜测别人函数的行为；有疑问在群里问人。
- 标 `[TODO]` 的部分由各模块实现后补全；未补全前不要凭猜测调用。

---

## 一、数据层 — `app/db.py`　维护人：C

| 函数 | 说明 |
|---|---|
| `get_conn() -> sqlite3.Connection` | 返回已开启外键约束、支持字典式取值的连接。🔴 每个新连接都会执行 `PRAGMA foreign_keys = ON` |
| `init_db() -> None` | 按 schema.sql 建表。幂等，可反复调用 |
| `insert_chapters(list) -> int` | 灌入 15 个归类抽屉（不是知识点库） |
| `insert_wrong_question(data, image_path=None) -> int` | 写入错题及其知识点关联，返回新记录 id |
| `recent_wrong_questions(limit=20) -> list[dict]` | 最近录入的错题 |
| `wrong_question_count() -> int` | 错题总数 |
| `log_practice(kp_id, is_correct, question_ref=None, difficulty=None, duration_sec=None)` | 写练习记录 |
| `mastery_table() -> pandas.DataFrame` | 🔴 九列已定（D 先定义、C 照此实现）：`知识点 / 所属章节 / 练习数 / 做对数 / 基础正确率 / 难度加权 / 时间衰减 / 掌握度 / 状态`。⚠️ 本行与第七节重复：实现落在 `app/profile.py`（C₂），界面统一从 `app.profile` 导入，`db.py` 只提供底层查询 |
| `weak_points(n) -> list[dict]` | 排除样本不足后掌握度最低的 n 个 |
| `kp_error_distribution() -> list[dict]` | 错题按知识点分布 + 主要错因 |
| `cost_summary() -> dict` | 累计调用次数与 token 用量 |

### 表结构（六张，知识点是两级的）

```
chapter(id PK, name UNIQUE, brief)                    -- 15 个，一次性写死
knowledge_point(id PK, name UNIQUE, chapter_id FK,    -- 🔴 运行时自动新建
                explain, created_from, created_at)
wrong_question(id PK, question_text, student_answer, correct_answer,
               solution_steps, error_type, difficulty, source,
               image_path, created_at)
wq_kp(wq_id FK, kp_id FK)                             -- 多对多
practice_log(id PK, kp_id FK, question_ref, is_correct, difficulty,
             duration_sec, created_at)
llm_log(id PK, purpose, prompt_tokens, completion_tokens, retried,
        success, created_at)
```

---

## 二、知识点挂载 — `app/knowledge.py`　维护人：C

🔴 **这是整个"知识库从错题里长出来"设计的支点。**

| 函数 | 说明 |
|---|---|
| `chapter_candidates() -> list[dict]` | 15 个章节的 id / name / brief。唯一允许 AI 挂靠的层级 |
| `find_or_create(name_hint, chapter_id, context) -> str` | 🔴 核心：① 精确名字匹配 → ② 包含关系与关键词重叠 → ③ 命中就复用已有 id → ④ 都没命中才在该章节下新建 → ⑤ 返回知识点 id |
| `ensure_valid_chapter(chapter_id) -> bool` | 校验章节 id 合法 |
| `all_knowledge_points() -> list[dict]` | 现有全部知识点，供提示词注入候选列表 |

**为什么 find_or_create 不能跳过查重**：库里会同时出现「不定积分」「不定的积分」
「求不定积分」三条指同一件事的记录，掌握度统计算成三个不同知识点，功能③彻底作废。

---

## 三、AI 能力层 — `app/llm_client.py`　维护人：B

🔴 **全项目唯一允许发网络请求的文件。**

| 函数 | 说明 |
|---|---|
| `chat(messages, *, purpose, json_mode=False, schema_hint=None, validator=None, max_retry=2) -> LLMResult` | 主入口 |
| `vision(prompt_text, images, *, purpose, system=None, json_mode=False, schema_hint=None, validator=None) -> LLMResult` | 多模态 |
| `is_configured() -> bool` | 三项环境变量是否齐全 |
| `missing_config_keys() -> list[str]` | 缺哪几项 |
| `extract_json(text) -> dict \| None` | 容忍 markdown 包裹和前后废话 |

`LLMResult` 字段：`text / prompt_tokens / completion_tokens / reasoning_tokens / retried / success`
异常类型：`LLMError`（自定义，上层负责降级处理）

配置来源：环境变量 `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`（三项必填，无默认值）
可选：`LLM_TIMEOUT=120` / `LLM_MAX_TOKENS=4000` / `LLM_TEMPERATURE=0.0`

---

## 四、问答 — `app/qa.py`　维护人：B

| 函数 | 说明 |
|---|---|
| `retrieve_knowledge(question, limit=4) -> list[dict]` | 🔴 反向片段匹配。中文不能用 `split()` 切词 |
| `answer(question, subject, style, history=None) -> str` | 返回 markdown；越界问题按提示词要求拒绝 |
| `list_subject_topics() -> list[str]` | 界面展示"本系统覆盖哪些知识点" |

---

## 五、错题抽取 — `app/intake.py`　维护人：B

| 函数 | 说明 |
|---|---|
| `analyze_text(题干, 学生答案, 参考答案="") -> IntakeDraft` | 文本路径 |
| `analyze_image(image_bytes, extra_note="") -> IntakeDraft` | 拍照路径 |
| `commit(draft, image_path=None) -> int` | 🔴 用户确认后才落库 |

`IntakeDraft` 字段：`question_text / student_answer / correct_answer /
solution_steps / knowledge_ids / new_concepts / difficulty / error_type /
confidence / source / degraded / note`

`degraded=True` 表示模型没成功，界面要显示空表单让人手工填（主流程不断）。

### 抽取输出契约（模型必须严格遵守）

```json
{
  "question_text": "题干完整文字",
  "student_answer": "学生写的答案",
  "correct_answer": "正确答案",
  "solution_steps": ["推导步骤1", "推导步骤2"],
  "knowledge_ids": ["已有知识点id"],
  "new_concepts": [{"name": "建议的新知识点名", "chapter_id": "ch_xxx"}],
  "difficulty": "easy | medium | hard",
  "error_type": "枚举值之一",
  "confidence": 0.82
}
```

规则：
- `knowledge_ids` **优先复用**已有 id，最多 3 个
- `new_concepts` 只是**建议**，是否真的新建由 `find_or_create()` 决定（AI 不直接写库）
- `chapter_id` 必须是 15 个章节之一，🔴 禁止发明新章节
- `error_type` 只能是这五个值：

| 值 | 含义 | 判别 |
|---|---|---|
| `concept_confusion` | 概念混淆 | 公式/定义用错了 |
| `calculation_error` | 计算失误 | 思路对，中间算错 |
| `method_wrong` | 方法选错 | 用了不适用的解法 |
| `incomplete` | 审题不全 | 漏条件、漏解 |
| `unknown` | 判不出 | 兜底，界面转人工选择 |

---

## 六、校验器 — `app/schemas.py`　维护人：C

| 函数 | 说明 |
|---|---|
| `make_intake_validator(allowed_kp_ids) -> callable` | 输入解析后的 dict，合规返回 `None`，不合规返回错误描述字符串（会被回喂给模型重试） |
| `make_practice_validator(allowed_chapter_ids, expected_min=1) -> callable` | 校验生成的练习题 |

拦截项：不是合法 JSON / 缺必填字段 / 🔴 `knowledge_ids` 越界 / 超过 3 个 /
`new_concepts` 的 `chapter_id` 不在章节集内 / `error_type` 不在枚举 /
`solution_steps` 非空数组 / `confidence` 不在 0~1 / `difficulty` 不在三个值内

---

## 七、掌握度与练习 — `app/profile.py`　维护人：C

| 函数 | 说明 |
|---|---|
| `mastery_table() -> DataFrame` | 掌握度 = 基础正确率 × 难度加权 × 时间衰减 |
| `summary_text() -> dict` | 界面顶部指标卡数据 |
| `build_practice_session(count) -> (list[dict], str)` | 返回题目列表 + 来源说明 |
| `grade(item, user_answer) -> bool` | 客观判分 |
| `record_result(items, answers) -> list[bool]` | 判分 + 回写 + 错题回流 |

系数（写在 SQL 里，确定性可调）：

```
掌握度 = 基础正确率 × 难度加权系数 × 时间衰减系数
```

- **难度加权**：全易题 1.0 / 含中等 1.05 / 含难题 1.15
- **时间衰减**：≤7 天 1.0 / 8~30 天 0.9 / >30 天 0.75
- 🔴 **封顶对象要说清楚**：最终掌握度截断在 1.0（即 100%），
  不是"难度系数本身封顶"——否则 ×1.15 永远被截掉，"难题答对更能证明掌握"就形同虚设。
  实际效果是：难题全对的知识点会顶到 100%，而易题为主的只能到 0.9×1.0 附近。

分级阈值（🔴 **前三档都必须带"练过 ≥3 次"这个前置条件**）：

| 条件 | 状态 |
|---|---|
| 练过 ≥3 次 且 掌握度 <40% | 🔴 未掌握 |
| 练过 ≥3 次 且 掌握度 <70% | 🟡 基本掌握 |
| 练过 ≥3 次 且 掌握度 ≥70% | 🟢 已掌握 |
| 练过 <3 次 | ⚪ 样本不足（不参与"最薄弱"排名） |

⚠️ 漏掉"≥3 次"前置条件的后果：一个只练过 1 次且答错的知识点会被直接判成
"未掌握"并霸占榜首 —— 正是 PLAYBOOK 明令要避免的那个缺陷。

### 界面依赖的两个返回形状（D 已按此实现，C 请照此对齐）

`mastery_table()` 的九列，顺序固定：

```
知识点 / 所属章节 / 练习数 / 做对数 / 基础正确率 / 难度加权 / 时间衰减 / 掌握度 / 状态
```

- `基础正确率`、`掌握度` 以及两个系数都用 0~100 的百分数值
- `状态` 只能是这四个字符串：`未掌握` / `基本掌握` / `已掌握` / `样本不足`
- 🔴 必须 LEFT JOIN：从没练过的知识点也要出现在结果里

`summary_text()` 的键名（界面按这些键取指标卡，另兼容同名中文键）：

```
wrong_total / not_mastered / basic / mastered / insufficient / weakest
```

---

## 八、界面 — `streamlit_app.py`　维护人：D

只允许调用上面各节的函数。🔴 **不许出现 SQL、不许发网络请求、不许引入前端框架。**

四个标签页：① 知识点问答 ② 错题录入 ③ 掌握度分析 ④ 针对性练习

⚠️ 开场白只做页面渲染，不写进对话历史（否则发给模型的序列以 assistant 开头会报错）。

**换桩位置只有一个**：文件顶部那一个 `from app.stubs import (...)` 区块。
换真实现时把名字映射到 `app.qa` / `app.intake` / `app.profile` / `app.knowledge` / `app.db`，
函数签名不变则界面其余代码一行不用改。

⚠️ 界面自己不读 `.env`：配置状态一律问 `is_configured()` / `missing_config_keys()`，
   `.env` 由 `llm_client` 负责加载（桩函数里为保持行为一致也读了一次）。

---

## 九、桩函数 — `app/stubs.py`　维护人：D

队友代码没好时用来跑通界面。🔴 返回的数据形状必须与本文件约定的完全一致，
将来只需替换 import 来源，界面代码不动。

当前清单（换桩时把 `[ ]` 改成 `[x]`，并注明日期）：

```
[ ] is_configured() / missing_config_keys()              待 B（llm_client）
[ ] answer()                                             待 B（qa）
[ ] analyze_text() / analyze_image()                     待 B（intake）
[ ] commit()                                             待 B（intake）🔴 唯一落库入口
[ ] chapter_candidates() / all_knowledge_points()        待 C₁（knowledge）
[ ] find_or_create()                                     待 C₁（knowledge）
[ ] recent_wrong_questions() / wrong_question_count()    待 C₁（db）
[ ] mastery_table() / summary_text() / weak_points()     待 C₂（profile）
[ ] build_practice_session() / grade() / record_result() 待 C₂（profile）
```

⚠️ 桩的假数据刻意做了「未掌握 / 基本掌握 / 已掌握 / 样本不足」四档，
   验收清单第 9 条（从没练过的知识点不霸榜）现在就能在界面上看出来。
