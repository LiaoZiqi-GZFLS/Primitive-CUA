# CUA 元件引擎 (Element Engine)

## 概述

元件是 CUA 自动化系统的基础数据单元——屏幕上一个可点击的 UI 控件快照。

元件 ≠ 动作。元件只描述"这里有什么"，不描述"要对它做什么"。动作（click、type、drag）属于宏步骤和脚本，不属于元件。

## 元件数据

每个元件包含 5 组核心数据，存储为 1 个 PNG + 1 个 JSON：

```
cua/data/templates/{window_class}/
├── xxx_dhash_timestamp.png       # 按钮裁剪原图
└── xxx_dhash_timestamp.json      # 元件元数据
```

### JSON 结构

```json
{
  "template_id": "WeChatMainWndForPC_a1b2c3d4e5f6g7h8_1700000000000",
  "timestamp": 1700000000000,
  "ocr_text": "微信-顶栏-搜索",
  "window": {
    "hwnd": 593370,
    "top_hwnd": 593370,
    "class": "WeChatMainWndForPC",
    "title": "微信",
    "pid": 12345,
    "rect": [100, 50, 800, 600]
  },
  "roi": {"x": 423, "y": 72, "w": 48, "h": 24},
  "click_px": [523, 122],
  "dhash": "a1b2c3d4e5f6g7h8",
  "embedding_384": "0a1b2c3d...",
  "image_path": "cua/data/templates/WeChatMainWndForPC/xxx.png"
}
```

| 字段 | 用途 | 回放时使用 |
|------|------|-----------|
| `ocr_text` | 元件名称，脚本 `click` 的目标 | L1 嵌入匹配、OCR 校验 |
| `roi` | 按钮相对窗口的偏移矩形 | L0 像素匹配搜索区域 |
| `dhash` | 64 位感知哈希 | 快速粗筛 |
| `embedding_384` | 名称的 384 维 MiniLM 向量 | 语义匹配、跨语言搜索 |
| `image_path` | 按钮裁剪 PNG 路径 | L0 模板匹配素材 |
| `window` | 窗口类名/标题/PID/HWND | 窗口绑定 |

---

## 命名规范

### 自动命名（Agent 录制时）

录制时元件名自动生成，四段式：`{应用}-{组件}-{位置}-{功能}`

| 窗口标题 | 点击位置 | OCR | 生成的名称 |
|---------|---------|-----|-----------|
| `微信` | 顶栏 | 搜索 | `微信-顶栏-搜索` |
| `火眼审阅 – 微信` | 底部 | 发送 | `微信-火眼审阅-底部-发送` |
| `无标题 - 记事本` | 左上 | 文件 | `记事本-左上-文件` |
| `Progman` (桌面) | 中部 | (空) | `桌面-中部-图标` |

### 位置规则

| ROI 相对 Y | 位置名 |
|-----------|--------|
| < 12% | 标题栏 |
| < 22% | 顶栏 / 左上 / 右上 |
| < 35% | 上部 |
| < 65% | 中部 |
| < 80% | 下部 |
| < 92% | 底部 |
| ≥ 92% | 底栏 |

X 坐标 < 25% 且 Y < 22% → `左上`，X > 75% 且 Y < 22% → `右上`。

### 手动命名

```bash
python cua/element_manager.py add "微信-服务号-顶栏-搜索"
```

手动给的名字直接用作 `ocr_text`，跳过自动命名。

### 去重

同名元件自动加四位 dHash 后缀：`微信-顶栏-搜索_a1b2`。名称缓存实现 O(1) 去重。

---

## 元件管理工具

### 命令全集

```bash
# 列出最近 30 个元件
python cua/element_manager.py list

# 查看元件详情
python cua/element_manager.py show "微信-顶栏-搜索"

# 新增元件（5 秒倒计时定位鼠标）
python cua/element_manager.py add "微信-顶栏-搜索"

# 预览元件图像（打开系统图片查看器）
python cua/element_manager.py preview "微信-顶栏-搜索"

# 列出所有有图像的元件
python cua/element_manager.py preview

# 重命名
python cua/element_manager.py rename "搜索" "微信-顶栏-搜索"

# 删除
python cua/element_manager.py delete "微信-顶栏-搜索"

# 测试匹配（在当前屏幕上找这个元件）
python cua/element_manager.py test "微信-顶栏-搜索"

# 按文字搜索
python cua/element_manager.py search "微信"

# 导出/导入
python cua/element_manager.py export
python cua/element_manager.py import elements.json
```

---

## 录制

### 自动录制（Agent 模式）

```bash
python cua/cli.py --record "打开微信搜索"
```

Agent 执行任务时，每次 `click`/`uia_click`/`web_click` 自动调用 `record_element()`：
1. 鼠标所在位置取窗口 HWND（`WindowFromPoint`，非前台窗口）
2. OpenCV Canny 边缘检测 → 轮廓查找 → 取包含点击点的最小包围框
3. OCR 文字包围框兜底（无边框控件如 Electron 页面）
4. 最差兜底：固定 80×80 裁剪
5. 计算 dHash + MiniLM 嵌入 + ROI
6. 生成四段式名称 → 去重 → 存 PNG + JSON

非视觉动作（paste_text、launch_app、wait 等）不录入元件，直接存入宏步骤。

### 手动录制

```bash
python cua/macro_editor.py record "微信搜索" "打开微信搜索火眼审阅"
```

流程：输入工具类型 → 输入参数 → 5 秒倒计时定位鼠标 → 自动采集。

---

## 回放中的使用

### L0 像素匹配（快速回放 & 脚本 `click`）

```
click 微信-顶栏-搜索
  → 嵌入匹配找元件 → 取 PNG 模板
  → ROI±100px 区域内 OpenCV 5 档缩放匹配 (0.6x~1.4x)
  → TM_CCOEFF_NORMED ≥ 0.70 → OCR 校验 → click
```

### L1 嵌入匹配

```
L0 失败 → 取 OCR 文字嵌入向量
  → ROI 区域滑动窗口 (80×40, step=20)
  → 每个窗口 OCR → MiniLM 嵌入 → 余弦相似度
  → sim ≥ 0.60 → OCR 校验 → click
```

### 脚本 `if see`

```
if see 微信-顶栏-搜索
  → 嵌入匹配 → L0 像素验证 → bool
```

---

## 元件 vs 宏 vs 脚本

```
元件 (Element)  →  宏 (Macro)  →  脚本 (Script)
    │                  │               │
 数据单元           步骤序列         可执行逻辑
 纯视觉快照         元件+动作        动作+分支+感知
    │                  │               │
 templates/         macros/         scripts/
 PNG + JSON         JSON            .cua
```

## 存储结构

```
cua/data/
├── templates/                       # 元件库
│   └── {window_class}/              # 按窗口类名分目录
│       ├── xxx_click_hash_ts.png
│       └── xxx_click_hash_ts.json
│
├── macros/                          # 宏库
│   └── {宏名称}.json
│
└── scripts/                         # 脚本库
    └── {宏名称}.cua
```
