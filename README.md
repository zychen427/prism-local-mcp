# Prism Local MCP

Windows 本机 GraphPad Prism 的 stdio MCP 和 Codex skill。它连接已打开的 Prism 项目，支持 Excel 重复值导入、原始值核验、图形导出，以及受约束的原生相对 IC20 工作流。另有独立 SciPy 剂量反应、批量拟合、加权、Bootstrap 和独立组比较；这些计算不是 Prism 原生分析。

## 安装

需要 Windows 交互桌面、GraphPad Prism、Python 3.11+ 和 Codex。下载本仓库后在仓库根目录执行：

```powershell
python -X utf8 .\scripts\install.py
# 若使用自定义 Codex 配置目录：
python -X utf8 .\scripts\install.py --codex-home '<Codex配置目录>'
```

安装器复制 skill、创建隔离环境并注册 `prism_local`，已有不同的同名配置时停止；修改配置前会备份。重启客户端或重载 MCP 后打开 Prism 项目，调用 `prism_list_sessions`、`prism_connect`、`prism_get_capabilities`。权限、具体调用和故障排查见 [connection.md](references/connection.md)。

## 原生 IC20

**当前仓库未包含该工作流所需的 Prism 模板，因此原生 IC20 自动流程暂不可用。** 独立 SciPy 剂量反应拟合不依赖此模板。


`prism_native_ic20_excel_auto` 接受明确的 Excel 长格式列与行：线性浓度（μM）、响应（%），每个浓度恰好 3 个原始重复值。该流程从合成模板创建副本，以 Prism ECanything F=80 拟合下降型相对 IC20，导出均值 ± SD 图、审计和可编辑项目，验证导入数值及重开导图。零浓度参与拟合但不显示于对数横轴。拟合后应目视检查图形。相对 20% 效应以拟合上下平台差为基准；参见 [GraphPad ECanything](https://www.graphpad.com/guides/prism/latest/curve-fitting/reg_ecanything.htm)。

该流程仅在中文 Prism 11.0.0 上实机验证；不能将此结果推广到其他版本、语言、重复数或绝对 IC20。旧版 Prism 的通用数据导出核验和 GUI 路径与原生 IC20 自动流程不同。独立组 bootstrap 要求独立实验单位，不能用于配对或聚类数据。操作前保存原项目，不自动重试部分完成的写操作；检查日志和活动窗口。该项目不是 GraphPad 官方产品，不包含 Prism 软件或许可证。

详细工具、统计定义及限制见 [SKILL.md](SKILL.md)。
