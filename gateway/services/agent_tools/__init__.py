# FloodMind Agent Tools — 按类别拆分的子模块，统一注册表
__all__ = ["TOOLS_REGISTRY", "TOOL_DESCRIPTIONS",
           "data_tools", "warning_tools", "forecast_tools", "report_tools",
           "file_tools", "schedule_tools", "system_tools", "alert_tools",
           "_safe_sync", "_get_cached_records", "_filter_by_time"]

from ._helpers import _safe_sync, _get_cached_records, _filter_by_time
from . import data_tools, warning_tools, forecast_tools, report_tools
from . import file_tools, schedule_tools, system_tools, alert_tools
from . import system_state_tools

# ── 工具注册表（供 AgentService 使用） ──

TOOLS_REGISTRY = {
    # 数据查询 (7)
    "query_water_level": (data_tools.QueryWaterLevelArgs, data_tools.query_water_level),
    "query_flow": (data_tools.QueryFlowArgs, data_tools.query_flow),
    "query_latest": (data_tools.QueryLatestArgs, data_tools.query_latest),
    "list_stations": (data_tools.ListStationsArgs, data_tools.list_stations),
    "compare_stations": (data_tools.CompareStationsArgs, data_tools.compare_stations),
    "query_devices": (data_tools.QueryDevicesArgs, data_tools.query_devices),
    "query_video_status": (data_tools.QueryVideoStatusArgs, data_tools.query_video_status),

    # 预警处置 (5)
    "list_warnings": (warning_tools.ListWarningsArgs, warning_tools.list_warnings),
    "generate_disposal": (warning_tools.GenerateDisposalArgs, warning_tools.generate_disposal),
    "update_warning_standard": (warning_tools.UpdateWarningStandardArgs, warning_tools.update_warning_standard),
    "get_station_thresholds": (warning_tools.GetStationThresholdsArgs, warning_tools.get_station_thresholds),
    "update_station_threshold": (warning_tools.UpdateStationThresholdArgs, warning_tools.update_station_threshold),

    # 预测趋势 (2)
    "run_forecast": (forecast_tools.RunForecastArgs, forecast_tools.run_forecast),
    "analyze_trend": (forecast_tools.AnalyzeTrendArgs, forecast_tools.analyze_trend),

    # 报告 (2)
    "generate_report": (report_tools.GenerateReportArgs, report_tools.generate_report),
    "query_reports": (report_tools.QueryReportsArgs, report_tools.query_reports),

    # 文件检索 (2)
    "Glob": (file_tools.GlobArgs, file_tools.glob_search),
    "Grep": (file_tools.GrepArgs, file_tools.grep_search),

    # 定时任务 (3)
    "CreateScheduledTask": (schedule_tools.CreateScheduledTaskArgs, schedule_tools.create_scheduled_task),
    "ListScheduledTasks": (schedule_tools.ListScheduledTasksArgs, schedule_tools.list_scheduled_tasks),
    "CancelScheduledTask": (schedule_tools.CancelScheduledTaskArgs, schedule_tools.cancel_scheduled_task),

    # 系统运维 (2)
    "diagnose_system": (system_tools.DiagnoseSystemArgs, system_tools.diagnose_system),
    "retry_failed_reports": (system_tools.RetryFailedReportsArgs, system_tools.retry_failed_reports),

    # 通知告警 (4)
    "send_notification": (alert_tools.SendNotificationArgs, alert_tools.send_notification),
    "list_active_alerts": (alert_tools.ListActiveAlertsArgs, alert_tools.list_active_alerts),
    "acknowledge_alert": (alert_tools.AcknowledgeAlertArgs, alert_tools.acknowledge_alert),
    "resolve_alert": (alert_tools.ResolveAlertArgs, alert_tools.resolve_alert),

    # 系统历史查询 (4)
    "list_alert_history": (system_state_tools.ListAlertHistoryInput, system_state_tools.list_alert_history),
    "get_threshold_changes": (system_state_tools.GetThresholdChangesInput, system_state_tools.get_threshold_changes),
    "get_system_diagnosis": (system_state_tools.GetSystemDiagnosisInput, system_state_tools.get_system_diagnosis),
    "get_recent_events": (system_state_tools.GetRecentEventsInput, system_state_tools.get_recent_events),
}

TOOL_DESCRIPTIONS = {
    "query_water_level":
        "查询测站水位历史数据（含流速，本地累积缓存）。",
    "query_flow":
        "查询测站流量历史数据（含流速，本地累积缓存）。",
    "query_latest":
        "获取测站最新水位/流量/流速/视频地址（实时快照）。",
    "list_stations":
        "列出全部已接入测站及编码。",
    "compare_stations":
        "多站水位/流量统计对比（最大/最小/平均）。",
    "query_devices":
        "查询测站设备清单及在线状态（从实时数据解析）。",
    "query_video_status":
        "查询测站摄像头实时状态及视频流播放地址。",
    "list_warnings":
        "列出当前预警和系统告警（含水位/流量阈值判定）。",
    "generate_disposal":
        "根据预警级别生成分级处置建议。",
    "update_warning_standard":
        "修改全局默认预警阈值或变化率阈值（不区分站点）。如需修改某站专属阈值，请使用 update_station_threshold。",
    "get_station_thresholds":
        "查询指定站点的水位+流量预警阈值。输入测站编码，返回该站专属配置，未配置时显示回退默认值。",
    "update_station_threshold":
        "修改指定站点的水位或流量预警阈值，立即生效并持久化。参数：station_code(测站编码)、category(level/flow)、level(blue/yellow/orange/red)、value(新阈值数值)。",
    "run_forecast":
        "Chronos-2 时序预测。支持单变量(univariate)、历史协变量(past_covariates)、未来协变量(future_covariates)三种模式。可用水位和流量互为协变量。",
    "analyze_trend":
        "水位/流量线性趋势分析（最小二乘法）。",
    "generate_report":
        "生成 Word 水文报告（日报/周报/月报）。",
    "query_reports":
        "列出已生成的报告文件列表。",
    "Glob":
        "按文件名模式搜索项目文件。",
    "Grep":
        "按正则表达式搜索文件内容。",
    "CreateScheduledTask":
        "创建定时任务（日报/周报/系统巡检）。",
    "ListScheduledTasks":
        "列出所有定时任务。",
    "CancelScheduledTask":
        "取消指定定时任务。",
    "diagnose_system":
        "全系统诊断：检查站点缓存、数据时效、判断故障范围。",
    "retry_failed_reports":
        "重试失败的报告生成。",
    "send_notification":
        "向钉钉或企业微信推送一条通知/告警消息（支持加签）。",
    "list_active_alerts":
        "列出当前未解除的值守告警事件。",
    "acknowledge_alert":
        "确认一条告警（表示已收到并正在处理）。",
    "resolve_alert":
        "解除一条告警并记录处置结果。",
    "list_alert_history":
        "查询历史告警记录（含已解除、已确认），可按小时数和站点过滤。回答'之前有过什么告警'类问题前务必调用。",
    "get_threshold_changes":
        "查询阈值变更日志，包含站点阈值和全局默认值的修改记录、变更前后的值、操作者。回答'阈值什么时候改的'类问题前务必调用。",
    "get_system_diagnosis":
        "获取最近的系统健康诊断记录（采集器、缓存、API、Chronos 状态）。回答'系统最近怎么样'类问题前务必调用。",
    "get_recent_events":
        "查询最近 N 小时内的所有系统事件（全类别时间线），可按类别过滤。回答需要系统状态全景的问题时调用。",
}
