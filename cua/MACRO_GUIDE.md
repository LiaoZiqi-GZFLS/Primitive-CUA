# 宏录制与播放指南

## 概述

宏是完整任务操作序列的快照，录制后可一键重放，无需 AI 模型参与。

三种获取宏的方式：
- **自动录制**：`python cua/cli.py --record "任务"` —— Agent 执行任务时自动采集
- **人工录入**：`python cua/macro_editor.py record` —— 手动逐步骤录制
- **导入轨迹**：成功的回放轨迹自动保存为宏

---

## 一、人工录入

### 基本用法

```bash
python cua/macro_editor.py record <宏名称> <任务描述>
```

示例：
```bash
python cua/macro_editor.py record "微信搜索" "打开微信搜索火眼审阅"
```

中文名称和任务描述直接输入即可，多语言嵌入模型原生支持中文。

### 录入流程

进入录制后，终端显示：
```
Recording macro: 微信搜索
Task: 打开微信搜索火眼审阅

Instructions:
  1. Move mouse to the target element
  2. Press Enter in this terminal to capture
  3. Enter tool type and parameters
  4. Type 'done' to finish, 'skip' to cancel
```

每一步的操作：
1. **把鼠标放到目标位置上**（按钮、输入框等）
2. **切回终端按回车**
3. **输入工具类型和参数**
4. 重复上述步骤直到完成，输入 `done` 结束

### 支持的工具类型

#### `click` —— 鼠标点击（默认）

```
--- Step 1 ---
Mouse at: (523, 418) = (0.2724, 0.3870) normalized
Tool: click
  ✓ Captured: WeChatMainWndForPC_click_a1b2c3d4_1700000000000
```

按回车即使用默认值 `click`。录制时自动裁剪按钮图并提取 OCR 文字。

#### `paste_text` —— 文本输入

```
--- Step 2 ---
Mouse at: (600, 80)
Tool: paste_text
  Text: 你好世界
  ✓ Captured: ...
```

回放时通过剪贴板粘贴（`Ctrl+V`），支持中文、emoji、长文本。

#### `type_keys` —— 键盘快捷键

```
--- Step 3 ---
Mouse at: (200, 150)
Tool: type_keys
  Keys: ctrl+a
  ✓ Captured: ...
```

仅用于快捷键，不要用于输入文字。多键组合用 `+` 连接：`ctrl+c`、`alt+tab`、`win+r`。

#### `launch_app` —— 启动应用

```
--- Step 4 ---
Tool: launch_app
  App name: 微信
  ✓ Captured: ...
```

回放时通过 Win 键 → 粘贴应用名 → Enter 启动。

#### `wait` —— 等待

```
--- Step 5 ---
Tool: wait
  Seconds: 2
  ✓ Captured: ...
```

回放时 `sleep(2)`。范围 0.5~10 秒。

#### `skip` —— 跳过当前步

```
Tool: skip
```

不采集，回到上一步状态，重新定位。

### 结束录制

```
Tool: done
Finishing...

✓ Macro saved: cua/data/macros/微信搜索.json (4 steps)
```

---

## 二、宏管理

### 列出所有宏

```bash
python cua/macro_editor.py list
```

输出：
```
Name                                     Steps  Task
──────────────────────────────────────── ────── ──────────────────────
微信搜索                                   4     打开微信搜索火眼审阅
打开记事本输入hello world                     3     打开记事本输入hello world
```

### 查看宏详情

```bash
python cua/macro_editor.py show "微信搜索"
```

输出每一步的工具类型、OCR 文字、ROI 坐标、模板图片是否完整：

```
Name:    微信搜索
Task:    打开微信搜索火眼审阅
Window:  WeChatMainWndForPC
Created: 1700000000000
Steps:   4

   1. [launch_app  ] launch: 微信
   2. [click       ] 搜索                                   roi=(680,72 48x24)  img=✓
   3. [click       ] 火眼审阅                               roi=(200,300 80x30) img=✓
   4. [paste_text  ] 你好                                   roi=(500,400 100x30) img=✗
```

`img=✓` 表示按钮模板图存在（可用于 L0 像素匹配），`img=✗` 表示文本类步骤无模板图。

### 删除宏

```bash
python cua/macro_editor.py delete "微信搜索"
```

---

## 三、人工播放

### 全自动播放

```bash
python cua/macro_editor.py play "微信搜索"
```

流程：
1. AI 校验宏是否适合当前桌面状态
2. 如需清桌面 → 自动 `Win+D`
3. 绑定目标窗口
4. 逐步执行：L0 像素匹配 → L1 特征匹配 → L2 K3 降级
5. 输出执行报告

### 单步确认播放

```bash
python cua/macro_editor.py play --step "微信搜索"
```

每一步暂停，显示详情后等你选择：

```
─────────────────────────
Step 2/4
  Tool: click
  Text: 搜索
  ROI:  (680,72 48x24)
Execute? [Y=execute / s=skip / q=quit]:
```

| 按键 | 效果 |
|------|------|
| `Y` / 回车 | 执行当前步（L0 像素匹配 + OCR 校验） |
| `s` | 跳过，继续下一步 |
| `q` | 退出，剩余步骤不执行 |

适用场景：
- 调试新录制的宏
- 不确定桌面状态是否匹配
- 只想执行宏的部分步骤

### 通过主 CLI 播放

```bash
# 自动匹配：同名任务优先走宏回放
python cua/cli.py --replay "微信搜索"

# 或者直接用宏名
python cua/cli.py --replay "打开微信搜索火眼审阅"
```

CLI 会自动检测：先尝试嵌入匹配宏 → 命中则走宏回放 → 否则走模板搜索回放。

---

## 四、宏匹配规则

`--replay "任务文本"` 的匹配流程：

```
任务文本 → MiniLM 嵌入(384-dim)
  │
  ├─ 对所有已保存宏的 task 文本做余弦相似度
  │   微信搜索 → vs "打开微信搜索火眼审阅并发送消息" = 0.82 ✓
  │   微信搜索 → vs "在Word里写文章并导出PDF"         = 0.05 ✗
  │
  ├─ best_sim ≥ 0.15 → K3 AI 校验
  │   ├─ approved=true → 执行宏
  │   └─ approved=false → 退回模板匹配 / K3 Agent
  │
  └─ best_sim < 0.15 → 无匹配宏，走模板搜索回放
```

所以任务描述尽量贴近实际意图，匹配效果最好。用简短的别名（如"微信搜索"）也能匹配到完整描述的宏。

---

## 五、存储结构

```
cua/data/
├── templates/                    # 按钮模板库
│   └── WeChatMainWndForPC/
│       ├── WeChatMainWndForPC_click_a1b2c3d4_1700000000000.png
│       └── WeChatMainWndForPC_click_a1b2c3d4_1700000000000.json
├── macros/                       # 宏文件
│   └── 微信搜索.json
└── chroma/                       # 嵌入向量库
    └── ...
```

每个宏 JSON 包含：
- `name`：宏名称
- `task`：原始任务描述
- `embedding_384`：任务文本的 MiniLM 嵌入向量
- `window_class`：目标窗口类名
- `steps`：步骤数组（每步包含 tool、args、ocr_text、roi、image_path）
