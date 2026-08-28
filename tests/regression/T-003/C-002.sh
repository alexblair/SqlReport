#!/usr/bin/env bash
# C-002 FR-002：report.md 逐函数契约覆盖关键接口
for kw in handle_request execute_report render_report_page ReportResult QueryCache _apply_max_rows; do
  grep -q "$kw" .adocs/specs/modules/report.md || exit 1
done
exit 0
