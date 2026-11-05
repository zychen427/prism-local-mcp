# 自动版本识别和绘图路径

## 真实环境识别

连接唯一已打开项目后调用 `prism_choose_workflow(session_id, project_file)`；`prism_get_capabilities` 也会返回 `workflow`。工具读取窗口标题，尽可能读取该进程可执行文件的版本元数据，并检查实际项目是否为受支持的 Prism ZIP。它不启动软件，不根据项目扩展名判断程序版本。文件版本不可访问时使用可解析的窗口标题；标题和文件的主版本矛盾、Prism 10 的次版本冲突或版本均无法识别时返回冲突/未知，先在 Prism“帮助→关于”核实并检查菜单。示例 `prism_preview_version_route` 只模拟输入，不是实际机器检测。

程序主窗口类以已知类为首选；对于非标准类，只有窗口标题符合 GraphPad Prism 且能核实所属进程的可执行文件名以 Prism 开头时才纳入候选。旧版窗口类、语言和权限未实机覆盖；无法识别时不能声称 Prism 没有安装。

## 分流规则

| 检测结果 | 自动选择 | 重要检查 |
|---|---|---|
| Prism 7 及以下 | `legacy_pre8` | 在当前版本新建/另存兼容项目；读取实际菜单与数据表，导入原始值；使用 `prism_verify_factorial_export` 对各指标的高精度原生 TSV 核对。使用独立统计结果时准确标明来源。字母和图内 P 文本为静态，数据变更后重新生成。 |
| Prism 8–9 | `classic_8_9` | 原生 CLD 不可用，采用上述静态标注与导出核验，不调用新版 ZIP/CLD 批量生成器。 |
| Prism 10.0–10.1 | `modern_before_cld` | 按实际格式选择可用的导入与验证，字母仍使用静态文本；动态检查控件。 |
| Prism 10.2 及以上 | `modern_cld_capable` | Prism 已引入 CLD，但要实际检查图表、分析、设置和项目格式。只有单族 ZIP 模板通过结构检查后才使用 `prism_build_factorial_script`。 |
| Prism 10 未知次版本/无法识别/冲突 | `prism10_minor_unknown` / `version_unknown` / `version_conflict` | 不假设 CLD 或任何控件可用，先核实，再执行。 |

“自动选择”是根据证据选择路径和提供下一步，不保证旧版能够无需界面干预完成绘图。Prism 11 的 `.prism` 文件不能在 Prism 9 或以前打开；不把 Prism 11 项目或 CLD 当作旧版原生模板。旧版应在其自身创建原生项目，如 `.pzf`、`.pzfx` 的具体可用格式以实际安装为准。来源：[GraphPad 项目兼容性](https://www.graphpad.com/guides/prism/latest/user-guide/compatibility_between_prism_versions.htm)，[Prism 10.2 CLD 说明](https://www.graphpad.com/updates/prism-10-2-0-release-notes)。

## 旧版统计与校验

Prism 7 手册列出了“不考虑行列比较每个单元格均值”的多重比较选项；当场确认是否能选 Tukey 和全部 15 对，读取分析结果核对因子主效应、交互作用和成对比较。不同旧版本不保证提供相同菜单：不具备该方案时，使用本 MCP 基于已确认的平衡独立设计计算的统计作为独立计算结果，在图中明示来源，不能称为 Prism 原生统计。参考：[Prism 7 双因素多重比较](https://www.graphpad.com/guides/prism/7/statistics/stat_multiple_comparisons_tab_2way.htm)。

逐指标从 Prism 原生导出完整 grouped TSV，保留两组列标题、三组行标题、原始重复值和排除标记；调用 `prism_verify_factorial_export`。工具检查标题、原始数值、标记和来源哈希；低精度导出导致差异时报告失败，不能只用显示均值声称通过。此工具不证明图、统计结果或项目 UID；统计结果与 `factorial_audit.json`、字母分组和 P 值需另行核对，并导出图片、保存、重开查看。

无 CLD 版本中，`prism_factorial_annotation_plan` 提供逐组字母和三个 P 值供放置；这只是计算得到的**静态注释**，不是 Prism 联动功能。共享字母指所用多重比较未达到显著阈值，并不证明两组等同。
