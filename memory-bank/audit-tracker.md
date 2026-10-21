# 审计追踪

> 记录每轮审计覆盖的文件和结论，避免重复踩坑。
> 状态: ✅ 已审查无新问题 | 🔧 发现问题已修复 | ⚠️ 发现问题未修复 | ⬜ 未审计

## 核心数据路径（按文件）

| 文件 | 状态 | 最后审计轮次 | 备注 |
|------|------|-------------|------|
| `Player.py` | ⬜ | - | 主入口，未审计 |
| `src/__init__.py` | ⬜ | - | 未审计 |
| `src/data_manager/__init__.py` | ⬜ | - | 未审计 |
| `src/data_manager/config_manager.py` | ⬜ | - | 配置管理，未审计 |
| `src/data_manager/position_manager.py` | ⬜ | - | 窗口位置管理，未审计 |
| `src/data_manager/sqlite3_client.py` | ⬜ | - | SQLite 客户端，未审计 |
| `src/layout/__init__.py` | ⬜ | - | 未审计 |
| `src/layout/custom_slider.py` | ⬜ | - | 自定义滑块，未审计 |
| `src/layout/custom_title_bar.py` | ⬜ | - | 自定义标题栏，未审计 |
| `src/layout/floating_control_panel.py` | ⬜ | - | 浮动控制面板，未审计 |
| `src/layout/pic_input_layout.py` | ⬜ | - | 图片输入布局，未审计 |
| `src/layout/pic_show_layout.py` | ⬜ | - | 图片展示布局，未审计 |
| `src/layout/range_slider.py` | ⬜ | - | 范围滑块，未审计 |
| `src/layout/video_cut_thread.py` | ⬜ | - | 视频裁剪线程，未审计 |
| `src/layout/video_show_layout.py` | ⬜ | - | 视频展示布局，未审计 |
| `src/utils/__init__.py` | ⬜ | - | 未审计 |
| `src/utils/utils.py` | ⬜ | - | 工具函数，未审计 |

## 脚本层

| 文件 | 状态 | 最后审计轮次 | 备注 |
|------|------|-------------|------|
| `scripts/build.bat` | 🔧 | R0 | `chcp 65001` 编码问题 + `rd /s/q` 语法已修（见 ISSUE-001） |
| `scripts/push_release.bat` | ✅ | R0 | gh CLI 推送逻辑 OK |
| `scripts/build_mac.sh` | ⬜ | - | macOS 构建，未审计 |
| `scripts/start.sh` | ⬜ | - | 启动脚本，未审计 |

## 配置文件

| 文件 | 状态 | 最后审计轮次 | 备注 |
|------|------|-------------|------|
| `.gitignore` | ✅ | R0 | 覆盖 build/dist/__pycache__/tmp OK |
| `requirement.txt` | ⬜ | - | Windows 依赖，未审计 |
| `requirement_mac.txt` | ⬜ | - | macOS 依赖，未审计 |
| `VERSION` | ✅ | R0 | 单行版本号 OK |
| `README.md` | ⬜ | - | 未审计 |

## 已知未修复问题

*（无）*

---

最后更新: 2026-10-21 R0（项目初始化）