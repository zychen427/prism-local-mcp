# Prism Local MCP

Windows 本机 GraphPad Prism 的 stdio MCP 和 Codex skill。统一的 `prism_local` 提供 Excel 原始重复值整理、Prism 原生数据导入与核验、图形导出、剂量反应以及 3×2 因子实验工作流。Prism 必须安装并可以在当前 Windows 交互桌面使用；本项目不是 GraphPad 官方产品，不包含 Prism 或其许可证。

## 安装与更新

需要 Windows、GraphPad Prism、Python 3.11+ 和 Codex。在下载或克隆的仓库根目录执行：

```powershell
python -X utf8 .\scripts\install.py
# 如果 Codex 使用自定义配置目录：
python -X utf8 .\scripts\install.py --codex-home '<Codex配置目录>'
```

安装器备份现有 skill 和配置，在独立环境安装 `requirements-mcp.txt`，注册 `prism_local`；如果旧的 `prism_factorial_local` 已启用，会将其停用以避免重复入口。若已存在不一致的 `prism_local` 配置，安装器停止并提示检查，不覆盖其他设置。重新加载 MCP 或重启 Codex 后，打开 Prism 项目并调用 `prism_list_sessions`、`prism_connect` 和 `prism_get_capabilities`。`prism_doctor` 可检查 Python、SDK、依赖和版本；窗口可见并不保证窗口操作权限可用。

## Excel 与双因素绘图

`prism_discover_factorial_excel` 只读扫描 `.xlsx`/`.xlsm` 的列、数值文本、直接颜色和合并单元格，返回 SHA-256 和候选信息；它不会猜测实验设计。`prism_prepare_flexible_factorial_excel` 根据明确的 3×2 映射，处理纵向记录或六组横向列，保留原始重复值和来源单元格，生成每指标 TSV、每组 n、均值和 SEM 审计。可选全部数值或明确的字体/填色 RGB；条件格式颜色、无缓存公式和含单位的数字文本不会被静默猜测。空值不补零。源表必须含原始重复值，不能把汇总的均值和 SEM 还原为观测值。

`prism_execute_grouped_graph_batch` 接受该审计和一个已保存、未带分析、数据链接明确的 grouped Prism ZIP 模板，先在独立副本中批量导入，再保存、核对原始值、重新打开并逐图导出；它保留日志和图像差异。图形类型、颜色和误差棒继承模板：使用前需在 Prism 中检查模板确为所需的柱图及 mean ± SEM，使用后仍需目视检查每张图。项目会保留参考模板及其图表。出错后检查 journal、日志、窗口和部分输出，不要盲目重跑。路径使用 ASCII 工作目录是目前经过测试的稳妥方式；特定非 ASCII 脚本路径曾失败。

`prism_prepare_factorial_data`、`prism_build_factorial_script` 和相关验证工具另支持符合明确条件的独立、平衡 3×2 设计和 Tukey；仅要求绘图时不会自动进行统计检验。按设计确认独立性、缺失、重复数和排除规则，不能把汇总图当成统计检验。详情见 [因子工作流](references/factorial-workflow.md)、[版本选择](references/version-routing.md) 和 [SKILL.md](SKILL.md)。

## IC20 与兼容性

`prism_native_ic20_excel_auto` 使用合成模板和 Prism ECanything F=80 拟合下降型相对 IC20：浓度为线性 μM、响应为百分比、每个浓度恰好 3 个原始重复值。零浓度参与拟合，但不显示在对数横轴。该模板导出均值 ± SD；拟合后需检查图形。相对效应的定义见 [GraphPad ECanything 文档](https://www.graphpad.com/guides/prism/latest/curve-fitting/reg_ecanything.htm)。独立 SciPy 拟合、批量拟合、Bootstrap 与独立组比较是独立计算，不称为 Prism 原生分析。

使用 `prism_check_compatibility` 检查当前 Prism 版本、项目和具体功能；`prism_preview_compatibility` 的传入版本仅为模拟。普通绘图不要求 CLD；未知或未经验证不等于必须更新。Prism 10.1.2、旧版本及其他语言界面需要在目标电脑实测。

## 已验证范围

- 20 项自动测试通过，覆盖版本路由、安装迁移、数据整理和计划等；可在仓库执行 `python -m unittest discover -s tests -p "test_*.py"`。
- 中文 Prism 11.0.0 (84)：使用合成数据完成 16 个指标、3×2 组合、每组 4 个重复值的分组柱状图；在模板中选择均值 ± SEM，逐图导出，保存并重开，项目内原始数值与审计核对一致。
- 本仓库清理元数据后的合成 IC20 模板经中文 Prism 11 原生拟合、数值核对、保存重开导图及工作窗口清理回归；其余版本和模板不因此自动获得验证。
- 发现重开后标题布局可能改变；批量工具输出以重开后重新导出的图片为准，保留首次导出和差异记录。每张图的外观、误差棒、分组和单位仍需检查。

Windows 原生控件与 Prism `.pzc` 脚本会操作桌面窗口。连接时指定唯一项目，使用副本并保留原始文件；出现未知对话框时停止并检查，不自动丢弃用户更改。故障排查和 MCP 连接见 [troubleshooting.md](references/troubleshooting.md) 与 [connection.md](references/connection.md)。
