# 批量对比删除/迁移工具

一个强大的文件夹对比、删除和迁移工具，支持桌面图形界面和命令行两种使用方式。

## 功能特性

### 核心功能
- **删除重复内容**：从副目录中删除与主目录重复的文件/文件夹
- **双向迁移**：在主目录和副目录之间移动或复制内容
- **三种对比模式**：
  - **name 模式**：只对比根目录下第一层的同名项
  - **structure 模式**：按相对路径对比整个目录结构
  - **deep-name 模式**：递归遍历所有层级的同名项（威力最强）

### 安全特性
- ✅ 预览功能：执行前查看所有将要处理的项
- ✅ 二次确认：防止误操作
- ✅ 嵌套检测：自动防止主副目录相互包含
- ✅ 详细日志：可选的操作日志记录
- ✅ 智能错误处理：文件占用等问题会给出明确提示

### 界面特点
- 🎨 现代化图形界面（PySide6/Qt）
- 📊 表格预览待处理项目
- 🔄 实时进度显示
- 💡 智能提示：根据选择动态显示操作说明

## 快速开始

### 安装依赖

### 创建虚拟环境（Windows）

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install "PySide6>=6.6"
python gui_app.py
```

如果不想使用虚拟环境，也可以先安装依赖，再运行：

```powershell
python -m pip install "PySide6>=6.6"
python gui_app.py
```



## 使用指南

### 图形界面使用

#### 删除重复内容

1. **选择目录**
   - 主目录：参考目录（保留）
   - 副目录：将从中删除重复内容

2. **配置选项**
   - 功能：选择"删除副目录中重复内容"
   - 对比模式：
     - `name`：只对比第一层同名（推荐日常使用）
     - `structure`：对比整个目录结构（更彻底）
     - `deep-name`：递归所有层级同名（最彻底，需谨慎）
   - 删除设置：
     - ✅ 也删除目录（同名文件夹也会删除）— **默认勾选**
     - 删除后清理副目录空文件夹

3. **执行操作**
   - 点击"预览结果" → 查看表格确认
   - 点击"执行" → 二次确认后开始删除

**示例场景**：
- 主目录：`D:/照片/已整理`
- 副目录：`E:/备份/照片`
- 目的：删除备份中与已整理重复的照片

#### 迁移文件

1. **选择目录**（同上）

2. **配置选项**
   - 功能：选择"迁移（主↔副）"
   - 对比模式：`name` 或 `structure`
   - 迁移设置：
     - 方向：主 → 副 或 副 → 主
     - 方式：移动（迁移）或复制（不删除源）
     - 目标已存在时覆盖（默认跳过）
     - 迁移全部（不检查是否存在）— 强制迁移所有文件
     - 完成后清理源目录空文件夹

3. **执行操作**（同删除流程）

**示例场景**：
- 从临时文件夹迁移新照片到主库
- 方向：副 → 主
- 方式：移动（节省空间）

### 命令行使用

#### 删除命令

```bash
# 基础用法（name 模式，预览）
python compare_and_delete.py delete "主目录" "副目录" --dry-run

# 删除同名项（包括文件夹）
python compare_and_delete.py delete "主目录" "副目录" --include-dirs

# 结构模式删除（更彻底）
python compare_and_delete.py delete "主目录" "副目录" --mode structure --include-dirs

# 深度同名模式（最彻底，危险）
python compare_and_delete.py delete "主目录" "副目录" --mode deep-name --include-dirs

# 跳过确认（危险）
python compare_and_delete.py delete "主目录" "副目录" --include-dirs --yes

# 带日志
python compare_and_delete.py delete "主目录" "副目录" --include-dirs --log "操作日志.txt"
```

#### 迁移命令

```bash
# 预览迁移（主 → 副）
python compare_and_delete.py migrate "主目录" "副目录" \
    --direction main-to-sub --dry-run

# 移动文件（副 → 主）
python compare_and_delete.py migrate "主目录" "副目录" \
    --direction sub-to-main

# 复制而非移动
python compare_and_delete.py migrate "主目录" "副目录" \
    --direction main-to-sub --copy

# 覆盖已存在的文件
python compare_and_delete.py migrate "主目录" "副目录" \
    --direction main-to-sub --overwrite

# 结构模式迁移 + 清理源空目录
python compare_and_delete.py migrate "主目录" "副目录" \
    --direction sub-to-main --mode structure --clean-source-empty-dirs

# 迁移全部文件（不检查是否存在）
python compare_and_delete.py migrate "主目录" "副目录" \
    --direction main-to-sub --migrate-all
```

## 对比模式详解

### name 模式（同名对比）

只对比**根目录下第一层**的同名文件和文件夹。

**适用场景**：
- 文件夹名称有意义（如：项目名、日期分类）
- 只需要处理顶层重复
- 快速清理备份

**示例**：
```
主目录/
  ├─ 项目A/
  ├─ 项目B/
  └─ 文档.txt

副目录/
  ├─ 项目A/        ← 会被删除（同名）
  ├─ 项目C/        ← 保留（主目录没有）
  └─ 文档.txt      ← 会被删除（同名）
```

### structure 模式（结构对比）

按**相对路径**对比整个目录树中的文件。

**适用场景**：
- 需要彻底清理重复文件
- 目录结构相似但不完全相同
- 精确的文件级对比

**示例**（删除-structure）：
```
主目录/
  └─ 照片/
      └─ 2024/
          └─ IMG001.jpg

副目录/
  └─ 照片/
      ├─ 2024/
      │   └─ IMG001.jpg    ← 会被删除（相对路径相同）
      └─ 2025/
          └─ IMG002.jpg    ← 保留（主目录没有这个路径）
```

**注意**：默认只删除文件，不删除目录（更安全）。如需删除目录，需勾选"也删除目录"。

### deep-name 模式（深度同名对比）

递归遍历主目录**所有层级**的文件/文件夹名称，在副目录中查找任何深度的同名项。

**适用场景**：
- 清理分散在不同层级的重复文件
- 文件名有意义，但位置混乱
- 需要最彻底的同名清理

**示例**（删除-deep-name）：
```
主目录/
  └─ 项目/
      └─ 子目录/
          └─ report.pdf

副目录/
  ├─ report.pdf           ← 会被删除（同名）
  └─ 备份/
      └─ 旧文件/
          └─ report.pdf   ← 也会被删除（同名，不管深度）
```

**⚠️ 警告**：deep-name 模式威力很强！只要名字相同就会删除，不管文件在哪个路径。**强烈建议先预览结果**。

## 常见问题

### ❓ 为什么明明相同但没删除？

**最常见原因**：没有勾选"也删除目录（同名文件夹也会删除）"

- 现在 GUI 已**默认勾选**此选项
- 如果用命令行，需要加 `--include-dirs` 参数

### ❓ 删除失败：WinError 5 拒绝访问

**原因**：文件正被其他程序占用或权限不足（只读属性）

**自动处理**：程序已内置强制删除机制：
- 自动移除只读属性
- 失败后自动重试 3 次（每次间隔 0.5 秒）
- 递归处理目录内的所有文件

**仍然失败？手动解决**：
1. 关闭可能占用文件的程序：
   - 视频播放器（VLC、PotPlayer 等）
   - 图片查看器
   - Office 文档（Word、Excel）
   - Windows 资源管理器的预览窗格
2. 如果还不行，重启资源管理器：
   - `Ctrl+Shift+Esc` 打开任务管理器
   - 找到"Windows 资源管理器" → 右键 → 重新启动
3. 最后手段：重启电脑

### ❓ 迁移时目标已存在怎么办？

**默认行为**：跳过已存在的项（安全）

**如需覆盖**：
- GUI：勾选"目标已存在时覆盖"
- CLI：加 `--overwrite` 参数

### ❓ structure 模式会合并目录吗？

**不会**。structure 模式**只迁移缺失的文件**，不会合并/覆盖整个目录结构。

这是出于安全考虑，避免意外覆盖重要文件。

### ❓ 为什么迁移时显示 0 个项目？

**原因**：目标目录中已经存在所有文件

**解决方法**：
- **方法 1**：勾选"目标已存在时覆盖"— 只覆盖已存在的文件
- **方法 2**：勾选"迁移全部（不检查是否存在）"— 强制迁移所有文件，无论是否存在

**区别**：
- "覆盖"：只处理已存在的文件，不存在的会跳过
- "迁移全部"：处理所有文件，存在的会覆盖，不存在的会创建

## 安全提示

### ⚠️ 危险操作

- **structure + 删除目录**：可能删除目录内的额外文件
- **--yes 跳过确认**：无二次确认，操作不可撤销
- **迁移 + 覆盖**：会强制覆盖已存在文件

### ✅ 推荐做法

1. **必做**：先用 `--dry-run`（CLI）或点"预览结果"（GUI）
2. **必做**：确认预览表格/列表无误
3. **建议**：重要数据先备份
4. **建议**：使用日志记录操作（`--log`）

## 技术细节

### 项目结构

```
批量对比删除/
├── compare_and_delete.py   # 核心逻辑 + CLI
├── gui_app.py              # 图形界面
├── README.md               # 本文档
└── .venv/                  # Python 虚拟环境
```

### 核心 API

```python
from compare_and_delete import plan_delete, plan_migrate, execute_plan

# 规划删除
plan = plan_delete(main_dir, sub_dir, mode="name", include_dirs=True)

# 规划迁移
src, dst, plan = plan_migrate(
    main_dir, sub_dir, 
    direction="main-to-sub", 
    mode="structure", 
    op="move"
)

# 执行计划
result = execute_plan(
    plan, 
    overwrite=False,
    on_progress=lambda done, total, item: print(f"{done}/{total}")
)
```

### 系统要求

- Python 3.10+
- Windows / macOS / Linux
- PySide6 6.6+

## 更新日志

### v1.1.0 (2026-01-03)

**新功能**
- ✅ 新增 deep-name 模式：递归遍历所有层级的同名项
- ✅ 迁移全部选项：不检查文件是否存在，强制迁移所有内容
- ✅ 强制删除机制：自动移除只读属性 + 3 次重试（解决 WinError 5）

**用户体验**
- ✅ 根据模式动态更新帮助文本
- ✅ 更清晰的错误提示和解决建议

### v1.0.0 (2026-01-02)

**核心功能**
- ✅ 删除重复内容（name / structure 两种模式）
- ✅ 双向迁移（主↔副，移动/复制）
- ✅ 图形界面（PySide6/Qt）
- ✅ 命令行工具

**安全改进**
- ✅ 修复迁移时 overwrite 逻辑不一致
- ✅ 修复空目录清理范围不准确
- ✅ 增强文件占用错误提示
- ✅ GUI 默认勾选"删除目录"避免困惑

**用户体验**
- ✅ 根据选择动态显示操作说明
- ✅ 智能识别权限/占用错误并给出建议
- ✅ 预览表格显示详细操作计划

## 许可证

MIT License

## 支持

遇到问题或有建议？欢迎反馈！
