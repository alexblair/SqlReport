"""test_sql_formatter.py — SQL 格式化 JS（_SQL_FORMATTER_JS / fmt）契约测试

需求：fmt 格式化 SQL 关键字换行时，不得破坏注释（-- 行注释、/* */ 块注释）
与字符串/反引号字面量的完整性——注释内关键字被拆出等于把被注释代码"脱注释"
投入运行（危险：可能执行被注释的 DELETE/UPDATE/SELECT）。

实现位置：render.py 的 _SQL_FORMATTER_JS。
测试方式：通过 node 子进程执行 fmt 函数本体，断言输出结构。
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

import render as render_mod

_FORMATTER_JS = render_mod._SQL_FORMATTER_JS


def _comments(sql):
    """提取 SQL 中的注释片段（-- 行注释 / /* */ 块注释），trim 并容忍末尾分号。"""
    out = []
    i, n = 0, len(sql)
    while i < n:
        if sql[i:i + 2] == "--":
            j = sql.find("\n", i)
            if j == -1:
                j = n
            seg = sql[i:j].strip()
            if seg.endswith(";"):
                seg = seg[:-1].rstrip()
            out.append(seg)
            i = j
        elif sql[i:i + 2] == "/*":
            j = sql.find("*/", i)
            if j == -1:
                seg = sql[i:].strip()
                j = n
            else:
                seg = sql[i:j + 2].strip()
                j = j + 2
            if seg.endswith(";"):
                seg = seg[:-1].rstrip()
            out.append(seg)
            i = j
        else:
            i += 1
    return out


@unittest.skipUnless(shutil.which("node"), "需要 node 执行格式化 JS")
class TestSqlFormatter(unittest.TestCase):
    """fmt 格式化不得破坏注释与字面量。"""

    def _run_fmt(self, sqls):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(_FORMATTER_JS)
            f.write("\nvar __in = %s;\n" % json.dumps(sqls, ensure_ascii=False))
            f.write("console.log(JSON.stringify(__in.map(function(s){ return fmt(s); })));")
            js_path = f.name
        try:
            proc = subprocess.run(
                ["node", js_path],
                capture_output=True, text=True, check=True,
                encoding="utf-8", timeout=30,
            )
            return json.loads(proc.stdout.strip())
        finally:
            os.unlink(js_path)

    def _assert_comments_preserved(self, sql):
        out = self._run_fmt([sql])[0]
        out_comments = _comments(out)
        for c in _comments(sql):
            self.assertIn(c, out_comments,
                          "注释被拆分脱注释：%r\n输入=%r\n输出=%r" % (c, sql, out))
        return out

    def test_user_case_commented_select_stays_commented(self):
        """用户案例：整段被注释的 SELECT 不得被格式化脱注释。"""
        sql = ("WHERE 1 = 1 -- 2 项目部 3 处置商    -- AND t.user_source = 3\n"
               "    AND dcat.`code` = 'material_category' -- 出库变更的订单\n"
               "    -- AND out_change.order_no Is NOT null\n"
               "    AND t.status <> 36 -- AND  t.order_no='PT62291177492861611870511';\n"
               "    -- SELECT * FROM t_store_order t WHERE t.order_no='JP21104177503593929757139';\n"
               "GROUP BY t.order_no;")
        out = self._assert_comments_preserved(sql)
        self.assertNotIn("\nSELECT * FROM t_store_order", out,
                         "被注释的 SELECT 被脱注释为可执行语句")

    def test_inline_comment_keyword_not_split(self):
        sql = "WHERE 1 = 1 -- AND t.user_source = 3\nAND t.status <> 36;"
        out = self._assert_comments_preserved(sql)
        self.assertIn("-- AND t.user_source = 3", out)

    def test_block_comment_keyword_not_split(self):
        sql = "SELECT 1 /* AND foo = 'x' */ , 2 FROM t;"
        out = self._assert_comments_preserved(sql)
        self.assertIn("/* AND foo = 'x' */", out)

    def test_string_literal_not_split(self):
        sql = "SELECT 'from where and' AS x, \"select\" AS y FROM t;"
        out = self._run_fmt([sql])[0]
        self.assertIn("'from where and'", out)
        self.assertIn('"select"', out)

    def test_backtick_identifier_not_split(self):
        sql = "SELECT `where` FROM `order`;"
        out = self._run_fmt([sql])[0]
        self.assertIn("`where`", out)
        self.assertIn("`order`", out)

    def test_comment_containing_quote(self):
        sql = "-- WHERE name = 'a' AND b = 'c'\nSELECT 1;"
        out = self._assert_comments_preserved(sql)
        self.assertIn("-- WHERE name = 'a' AND b = 'c'", out)

    def test_string_with_sql_escape(self):
        sql = "SELECT 'it''s' AS x;"
        out = self._run_fmt([sql])[0]
        self.assertIn("'it''s'", out)


if __name__ == "__main__":
    unittest.main()