# CUA 脚本引擎 (Script Engine)

## 概述

脚本引擎是 CUA 的第三层执行机制，与快速回放、K3 Agent 并存：

```
执行速度         AI 依赖
─────────       ────────
脚本引擎  >  快速回放  >  K3 Agent
(纯文本)     (L0/L1/L2)   (完整工具调用)
```

脚本引擎是文本 DSL 解释器。脚本文件 (.cua) 包含动作、变量、条件分支和循环，由 `ScriptEngine` 逐行解释执行。不依赖 LLM（除 `if kimi` / `while kimi` 条件）。

---

## 运行机制

### 执行流程

```
脚本文件 (.cua)
  │
  ├─ 1. validate() — 语法检查（不通过则拒绝执行）
  │     ├─ 未知命令
  │     ├─ 块匹配 (if/endif, repeat/endrepeat, while/endwhile)
  │     ├─ goto 目标存在性
  │     └─ return 码合法性
  │
  ├─ 2. _parse() — 解析为指令列表
  │     ├─ tokenize（引号字符串、变量引用）
  │     ├─ expand repeat 块展开
  │     └─ label 注册
  │
  └─ 3. _execute() — 逐行解释执行
        │
        ├─ 变量展开 ($VAR → 值)
        ├─ 块控制 (if_stack, while_stack)
        ├─ 命令分发 (动作 / 控制流 / 感知)
        └─ return 退出 (code 0/1/2)
```

### 执行模型

- **指令指针 (IP)**：从 0 开始，逐行递增，goto 跳转
- **变量作用域**：全局（`set` 设置，`$name` 引用）
- **条件栈**：嵌套 if/else/endif，支持多层嵌套
- **循环栈**：while/endwhile 入栈，每次迭代重新评估条件
- **repeat 展开**：解析时 `repeat N { ... }` 直接展开为 N 份副本

### 变量展开

所有参数在执行前经过变量展开：`$name` → `vars["name"]`。未定义变量保持原样不展开。

内置变量：
| 变量 | 含义 | 示例值 |
|------|------|--------|
| `$screen_w` | 屏幕宽度 (px) | `1920` |
| `$screen_h` | 屏幕高度 (px) | `1080` |
| `$ocr_result` | 最近一次 `ocr` 的文本输出 | `"微信 搜索 火眼审阅"` |
| `$last_result` | 最近一次命令的输出 | 文件路径或文本 |
| `$now` | 当前时间戳 (ms) | `1700000000000` |

---

## 语法规范

### 基本规则

- 每行一条命令，`#` 开头为注释
- 缩进控制块结构（4 空格 = 1 级）
- 包含空格的参数用双引号或单引号包裹
- `$VAR` 在任何参数中引用变量

### 命令全集

#### 动作类

```
click [target]            模板匹配按钮并点击，target 为元件 OCR 文字
uia_click [name]          UIA Invoke 点击控件
web_click [text]          Playwright 点击网页元素
type [text]               剪贴板粘贴文本（Ctrl+V）
keys [combo]              键盘快捷键（如 ctrl+c, alt+tab）
launch [name]             Start 菜单搜索启动应用
wait [seconds]            等待秒数（0.1-120）
scroll [dir] [amount]     滚动（dir=up/down, amount=像素）
navigate [url]            浏览器导航到 URL
drag [fx] [fy] [tx] [ty]  鼠标拖拽（归一化坐标 0-1）
move [x] [y]              移动鼠标到归一化坐标
screenshot [path]         保存当前屏幕截图
ocr [path]                屏幕 OCR，结果存 $ocr_result
```

#### 变量

```
set [name] [value]        设置变量 $name = value
print [text]              打印到终端，支持 $VAR
```

#### 控制流

```
if [condition] [args]     条件分支
  ...
else                      （可选）
  ...
endif

repeat [N]                循环 N 次（解析时展开）
  ...
endrepeat

while kimi [question]     条件循环（每次迭代调 K3）
  ...
endwhile

goto [label]              无条件跳转
label [name]              跳转目标
wait_until [cond] [args] [timeout=N]  条件等待
exec [macro_name]         内联执行另一个宏
fail [reason]             终止脚本（code=1）
return [code] [summary]   退出脚本（code: 0/1/2）
```

#### 条件类型

| 条件 | 语法 | 感知方式 | 需 API |
|------|------|---------|--------|
| `kimi` | `if kimi question` | 截图 → K3 视觉问答 | 是 |
| `see` | `if see target_text` | 元件库模板匹配 | 否 |
| `ocr` | `if ocr text` | 屏幕 OCR 文字匹配 | 否 |
| `window` | `if window title_part` | 枚举所有可见窗口 | 否 |
| `url` | `if url url_part` | 浏览器当前 URL | 否 |

### 块语法规则

```
# 正确
if kimi Is it visible?
    click Button A
    type hello
else
    click Button B
endif

# 错误 — 缩进不一致
if kimi question
  click Button     # 2 空格，应 4 空格
endif

# repeat 展开（解析时）
repeat 3
    click OK
    wait 1
endrepeat

# 等价于
click OK
wait 1
click OK
wait 1
click OK
wait 1
```

### return 码

| 码 | 含义 | CLI 行为 |
|----|------|----------|
| `return 0 [msg]` | 成功完成任务 | 打印结果 |
| `return 1 [msg]` | 失败，不可恢复 | 打印错误 |
| `return 2 [msg]` | 委托 K3 Agent | 调 `run_task(msg)` |

---

## 宏 (Macro)

### 定义

宏是**完整任务的执行轨迹录音**。存储为 JSON，包含元件步骤的有序序列和附加元数据。

### 录制方式

**自动录制**：Agent 执行任务时自动采集

```bash
python cua/cli.py --record "打开微信搜索火眼审阅"
```

每步 click/type/launch 等操作自动裁剪按钮 → 存元件 (PNG+JSON) → 任务结束时组装为宏。

**人工录制**：手动定位鼠标，逐步录入

```bash
python cua/macro_editor.py record "微信搜索" "打开微信搜索火眼审阅"
```

### 存储结构

```
cua/data/
├── templates/                          # 元件库
│   └── WeChatMainWndForPC/
│       ├── xxx_click_a1b2_ts.png       # 按钮截图
│       └── xxx_click_a1b2_ts.json      # 元件元数据
│
├── macros/                             # 宏库
│   └── 微信搜索.json                    # 步骤序列 + 元数据
│
└── scripts/                            # 脚本库
    └── 微信搜索.cua                     # 自动生成 + K3 改进
```

### 宏结构

```json
{
  "name": "微信搜索",
  "task": "打开微信搜索火眼审阅",
  "created": 1700000000000,
  "window_class": "WeChatMainWndForPC",
  "embedding_384": "a1b2c3...",       // 任务文本嵌入（语义匹配用）
  "steps": [
    {
      "template_id": "xxx_launch_xxx",
      "tool": "launch_app",
      "args": {"name": "微信"},
      "ocr_text": "launch: 微信",
      "roi": {"x": 245, "y": 320, "w": 100, "h": 30},
      "image_path": "cua/data/templates/...",
      "embedding_384": "...",
      "dhash": "0",
      "window": {"class": "...", "title": "...", "pid": 1234}
    }
  ]
}
```

### 宏回放

```bash
# 嵌入匹配 → K3 校验 → L0/L1/L2 执行
python cua/cli.py --replay "微信搜索"

# 单步确认
python cua/macro_editor.py play --step "微信搜索"
```

回放时 `load_macro()` 用任务嵌入向量余弦匹配所有宏，best ≥ 0.15 则命中，然后 K3 校验是否适合当前桌面状态。

---

## 脚本 vs 宏

| | 宏 | 脚本 |
|---|---|---|
| 格式 | `macros/*.json` | `scripts/*.cua` |
| 内容 | 元件的线性序列 | 文本 DSL（动作+逻辑） |
| 分支/循环 | 无 | if/else/repeat/while |
| 感知判断 | 无 | kimi/ocr/see/window/url |
| 变量 | 无 | set + $VAR |
| return 码 | 无 | 0/1/2 |
| 创建方式 | 自动/人工录制 | 手写 / 宏自动导出 |
| 执行引擎 | 快速回放 (L0/L1/L2) | ScriptEngine 解释器 |

**转换**：宏 → 脚本是单向自动的。每次 `save_macro()` 自动生成 `.cua`，录制完成后 K3 审视轨迹加上守卫。

---

## 元件管理器

独立工具管理 UI 元件（按钮模板）。

```bash
# 列出所有
python cua/element_manager.py list

# 查看元件
python cua/element_manager.py show "搜索"

# 添加元件（鼠标定位+回车）
python cua/element_manager.py add "搜索按钮"

# 测试匹配
python cua/element_manager.py test "搜索按钮"

# 搜索
python cua/element_manager.py search "微信"

# 导出/导入
python cua/element_manager.py export
python cua/element_manager.py import elements.json
```

---

## 自愈回路

两个时机触发：

**录制时**（`--record`）：宏保存后 K3 审视轨迹 → 给自动生成的 .cua 加 wait_until / if 守卫。

**回放时**（`--replay`）：有 L2 降级 → K3 分析失败点 → 生成 `_improved.cua`。

```
┌──────────────────────────────────────────────┐
│                                              │
│  录制/回放 → 失败记录 → K3分析 → 改进脚本     │
│                                              │
│  脚本越跑越健壮  ←──────────  ────────┘       │
└──────────────────────────────────────────────┘
```

---

## 完整示例

```bash
# 1. 录制任务
python cua/cli.py --record "打开微信搜索火眼审阅"

# 2. 自动产物
#    → macros/打开微信搜索火眼审阅.json
#    → scripts/打开微信搜索火眼审阅.cua  (K3 改进过的)

# 3. 检查脚本
python cua/script_runner.py scripts/打开微信搜索火眼审阅.cua --check

# 4. 回放宏
python cua/cli.py --replay "微信搜索"

# 5. 如果有 L2 降级 → 自动生成 _improved.cua
#    → scripts/打开微信搜索火眼审阅_improved.cua

# 6. 执行改进后的脚本
python cua/script_runner.py scripts/打开微信搜索火眼审阅_improved.cua
```
