#!/usr/bin/env bash
# C-004 FR-002：query_executor.md 与 result_transform.md 逐函数契约覆盖
for kw in execute_mysql_query sql_contains_write create_mysql_connection _split_sql_statements; do
  grep -q "$kw" .adocs/specs/modules/query_executor.md || exit 1
done
for kw in filter_rows sort_rows calc_total_pages select_columns invalid_numeric_filters; do
  grep -q "$kw" .adocs/specs/modules/result_transform.md || exit 1
done
exit 0
