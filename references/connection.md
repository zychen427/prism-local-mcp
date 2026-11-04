# Prism MCP 连接接口

本包提供实际可运行的本机 stdio MCP server：`scripts/prism_mcp_server.py`，注册名推荐 `prism_local`。它将已验证的原生窗口操作封装为工具，不宣称 Prism 有官方 MCP 或 COM API。

## 安装到另一台电脑

需要 Windows、已打开的 Prism、可访问交互桌面的 Codex。本机运行环境示例为 `C:/example/codex/runtimes/prism-local-mcp/Scripts/python.exe`，源文件是 `C:/example/codex/skills/prism-local-plotting/scripts/prism_mcp_server.py`。另一台电脑必须修改路径。

推荐 Python 3.11+，可直接执行 `scripts/install.py` 自动安装、备份及注册；命令见 README。手动部署时创建独立 venv，并安装技能包的 `requirements-mcp.txt`。服务只通过 stdio 通信，Codex 按需启动，不开放 HTTP 端口，也不安装 Windows 服务。服务没有 OpenAI API 调用，不需要 API key。

```powershell
python -X utf8 -m venv 'C:/example/codex/runtimes/prism-local-mcp'
& 'C:/example/codex/runtimes/prism-local-mcp/Scripts/python.exe' -m pip install -r 'C:/example/codex/skills/prism-local-plotting/requirements-mcp.txt'
```

Codex 配置表的例子：

```toml
[mcp_servers.prism_local]
command = 'C:/example/codex/runtimes/prism-local-mcp/Scripts/python.exe'
args = ['-X', 'utf8', 'C:/example/codex/skills/prism-local-plotting/scripts/prism_mcp_server.py']
cwd = 'C:/example/codex/skills/prism-local-plotting'
startup_timeout_sec = 20
tool_timeout_sec = 90
enabled = true

[mcp_servers.prism_local.env]
PYTHONUTF8 = '1'
```

以实际 `CODEX_HOME/config.toml` 为准。添加前解析已有 TOML、备份、仅新增此服务器表，不覆盖其他 MCP 或认证设置。已注册不等于当前聊天已经拥有新工具；重新加载 MCP 或新会话后调用 `prism_list_sessions` 验证。连接进程若在非交互桌面/沙箱内看不到窗口，报告这个具体边界，不重装服务碰运气。

官方配置依据：[OpenAI Codex MCP 文档](https://developers.openai.com/codex/mcp/)。本地 transport 与 SDK 依据：[MCP transports](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)、[MCP Python SDK v1.x](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x)。配置字段来自本次读取的官方页面；UI 控件则来自本次本机实测。

## 最少调用路径

1. `prism_list_sessions()`：得到窗口标题、PID 和 frame HWND。
2. `prism_connect(project_title="目标项目.prism", output_dir="允许写入的工作目录")`：得到 `session_id`。有两个同名窗口时显式用 frame HWND。
   随后 `prism_get_capabilities(session_id, project_file)` 检测版本、语言、菜单与原生格式。项目扩展名可以是实际 `.prism/.pzf/.pzfx`，不检查固定 Prism 版本号。
3. `prism_snapshot_project` 保存物理备份和 before.json；`prism_survey_excel` 读取输入结构。
4. `prism_prepare_data(session_id, config)` 生成 audit/TSV。输出目录固定为此会话目录。
5. `prism_build_import_script` 生成经过结构检查的导入脚本；`prism_run_script` 一次执行。保存副本改了项目名后，按新名称 reconnect，不猜活动窗口。
6. `prism_get_dialogs` / `prism_get_controls` 发现真实控件；`prism_apply_controls` 每个对话框一次批量设置。必要时 `prism_capture_window` → `prism_click_window(double=true)` 打开柱形或轴格式。
7. `prism_verify_data` 一次核验全部原始数值、排除、均值和 baseline。运行纯导出脚本保存最终 PNG，视觉检查；保存重开后再检查。

旧版/非 ZIP 格式使用 `prism_verify_export` 核对软件原生 TSV 导出，并按 GUI 记录保护原图。此模式不声称读到了内部 UID。若软件的导出精度不足，工具会报差异，不能绕过。

需要检查已有 audit 时调用只读 `prism_read_audit(audit_file, metric)`，返回组映射、排除数量、mean/SD/SEM 与两位小数标签，避免重新读取全部原始格。该工具不证明当前源文件未改变。`prism_inspect_project` 只返回被图引用的数据集 UID，另提供 dataset_count，减少空列开销；该清单不代表所有实际数据列。

`inspect_project` 看的是已保存文件，不代表内存中未保存的表。物理备份也不自动保存用户未保存的修改；开始前确认项目状态，必要时把内存状态另存工作副本。

## 批量操作示例

已打开“设置坐标轴格式”，从当前控件核实 ID 后，使用同一次调用提交尺寸：

```json
{
  "session_id": "上一步真实session_id",
  "dialog_title": "设置坐标轴格式",
  "steps": [
    {"action":"tab","id":1431,"index":0},
    {"action":"combo","id":1455,"text":"自定义"},
    {"action":"edit","id":201,"value":"21.59"},
    {"action":"edit","id":202,"value":"12"},
    {"action":"button","id":2360},
    {"action":"read","id":202,"class":"Edit"},
    {"action":"button","id":1,"expect_closed":true}
  ]
}
```

这是本次版本的示例参数。`combo` 优先传真实文字，字号和布局按数据决定。每一步都重新定位控件；页签切换后不复用失效 HWND。下一步进入新对话框时可在 step 中覆盖 `dialog_title`。

`prism_apply_controls` 最多 40 个串行步骤；遇到错误返回 `passed:false`、失败步骤、已执行动作和当前 dialogs，不再执行后续步骤，也不承诺事务回滚。恢复时从真实回读状态继续。

## 接口限制

- 所有 UI 操作共用锁，不并发操作桌面。
- 连接检查 HWND/PID、主窗口类和项目身份；意外切换项目或窗口关闭后明确重连。
- 不锁定 Prism 版本。脚本打开入口按当前菜单文字发现，中英文脚本窗口按当前标题/Run 按钮识别；其他语言先检查当前 GUI。控件写入使用实时发现的 ID 和下拉文字。未知版本/命令明确返回需要探测/后备，而不是保证任意版本一键兼容。
- 写入与 Save/Export 只能落到会话输出目录；Import 可以读取外部源文件。没有任意 shell 工具。
- `prism_run_script` 仅接受本工作流已记录的命令白名单。`ClearTable` 有删除数据的效果，只有新表或明确获授权的表可使用，工具标注为有破坏可能。
- 不默认点击保存/不保存提示，不默认安装其他软件，也不自动删除原图。复核仍需要 Codex 的视觉判断。
- screenshot 返回本地 PNG 的原生 MCP 图像；完整文件路径由调用参数确定。目标被其他应用覆盖时拒绝截图，防止把别的软件截进产物。
