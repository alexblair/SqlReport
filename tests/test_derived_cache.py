"""
tests/test_derived_cache.py — 派生态缓存（C-3）

问题（基线 spec §10.2 第 1 条）：
    L1/L2 缓存的都是**全量未筛选未排序**的数据，`execute_report` 末尾的
    transform 循环因此在**每次请求**都对全量 N 行重跑 filter + sort。
    实测「排序后翻页」P50 73ms、「筛选后翻页」P50 100.8ms（10 万行）。

设计（spec §5 C-3）：
    派生态挂在 `CachedResult` 实例上，**零失效逻辑**——L1 每次 set 新建
    CachedResult，旧对象连同派生态一起回收；L1 TTL 过期或逐出，派生态随之
    消失。派生态绝不会比 L1 活得久，严格保持现有语义。

    只缓存 filter+sort 的有序全量行列表，**分页切片每次现算**：
    排序是 O(N log N)、切片是 O(page_size)，且翻页时 filters/sorts 不变
    只有 page 变 → 命中率接近 100%。

本文件最关键的两个用例是 `test_l1_expiry_discards_derived` 与
`test_force_rebuild_serves_new_data`：派生态若跨数据版本存活，用户会看到
过期行序，而**不报错**。
"""

import unittest
from unittest.mock import patch, MagicMock

import redis_cache
import report
from report import QueryCache, execute_report


POOL = {"host": "h", "port": 3306, "user": "u",
        "password": "p", "database": "d"}

REPORT_CFG = {"prefer_cache": 0, "cache_ttl_hours": 0, "pool_id": 1,
              "sql_query": "SELECT * FROM t", "name": "报表C", "memo": "",
              "allow_write": 1, "allow_all_output": 1, "max_rows": 0}

ROWS = [{"columns": ["id", "v"],
         "rows": [(i, f"v{i:03d}") for i in range(1, 51)]}]


def _counting_transforms():
    """把 filter_rows / sort_rows 包成带调用计数的版本（走真实实现）。"""
    calls = {"filter": 0, "sort": 0}
    real_filter, real_sort = report.filter_rows, report.sort_rows

    def counting_filter(*a, **kw):
        calls["filter"] += 1
        return real_filter(*a, **kw)

    def counting_sort(*a, **kw):
        calls["sort"] += 1
        return real_sort(*a, **kw)

    return calls, counting_filter, counting_sort


class DerivedCacheTestBase(unittest.TestCase):
    def setUp(self):
        report._query_cache.clear()
        self.cache = QueryCache()
        self.calls, self.cfilter, self.csort = _counting_transforms()

    def _run(self, **kw):
        """跑一次 execute_report，transform 调用被计数。"""
        params = dict(report=REPORT_CFG, cache=self.cache, page_size=10)
        params.update(kw)
        with patch("report.db.execute_mysql_query", return_value=ROWS), \
             patch("report.db.create_mysql_connection", return_value=MagicMock()), \
             patch("report.filter_rows", self.cfilter), \
             patch("report.sort_rows", self.csort):
            return execute_report(1, "SELECT * FROM t", POOL, **params)


class TestDerivedCacheHit(unittest.TestCase):
    """核心：重复的相同筛选/排序不再重跑 transform。"""

    def setUp(self):
        report._query_cache.clear()
        self.cache = QueryCache()
        self.calls, self.cfilter, self.csort = _counting_transforms()

    def _run(self, **kw):
        params = dict(report=REPORT_CFG, cache=self.cache, page_size=10)
        params.update(kw)
        with patch("report.db.execute_mysql_query", return_value=ROWS), \
             patch("report.db.create_mysql_connection", return_value=MagicMock()), \
             patch("report.filter_rows", self.cfilter), \
             patch("report.sort_rows", self.csort):
            return execute_report(1, "SELECT * FROM t", POOL, **params)

    def test_second_page_request_skips_filter_and_sort(self):
        """✅ Positive: 换页但筛选/排序不变 → transform 只跑一次。"""
        r1 = self._run(page=1, sorts=[("v", "asc")])
        self._run(page=2, sorts=[("v", "asc")])
        self.assertEqual(self.calls["sort"], 1,
                         "翻页不该重跑排序——这是 C-3 的核心收益")

        r2 = self._run(page=2, sorts=[("v", "asc")])
        self.assertEqual(self.calls["sort"], 1,
                         "第三次请求仍应命中派生态")
        self.assertEqual(len(r1.results[0]["rows"]), 10)
        self.assertEqual(r2.results[0]["rows"], ROWS[0]["rows"][10:20],
                         "第 2 页应是第 11~20 行")
        self.assertEqual(r2.results[0]["total"], 50)

    def test_different_sorts_use_different_entry(self):
        """✅ Positive: 排序不同 → 不同条目，各自算一次。"""
        self._run(page=1, sorts=[("v", "asc")])
        self._run(page=1, sorts=[("v", "desc")])
        self.assertEqual(self.calls["sort"], 2)

    def test_different_filters_use_different_entry(self):
        """✅ Positive: 筛选不同 → 不同条目。"""
        self._run(page=1, filters=[("v", "contains", "v01")])
        self._run(page=1, filters=[("v", "contains", "v02")])
        self.assertEqual(self.calls["filter"], 2)

    def test_pagination_results_are_correct(self):
        """✅ Positive: 命中派生态时分页切片仍正确。"""
        r1 = self._run(page=1, sorts=[("v", "asc")], page_size=10)
        r2 = self._run(page=3, sorts=[("v", "asc")], page_size=10)
        r3 = self._run(page=5, sorts=[("v", "asc")], page_size=10)
        self.assertEqual(len(r1.results[0]["rows"]), 10)
        self.assertEqual(r2.results[0]["rows"], ROWS[0]["rows"][20:30])
        self.assertEqual(r3.results[0]["rows"], ROWS[0]["rows"][40:50])
        self.assertEqual(r3.results[0]["total"], 50)


class TestDerivedCacheLifecycle(unittest.TestCase):
    """派生态必须与 L1 同生共死——否则会看到过期行序且不报错。"""

    def setUp(self):
        report._query_cache.clear()
        self.cache = QueryCache()
        self.calls, self.cfilter, self.csort = _counting_transforms()

    def _run(self, **kw):
        params = dict(report=REPORT_CFG, cache=self.cache, page_size=10)
        params.update(kw)
        with patch("report.db.execute_mysql_query", return_value=ROWS), \
             patch("report.db.create_mysql_connection", return_value=MagicMock()), \
             patch("report.filter_rows", self.cfilter), \
             patch("report.sort_rows", self.csort):
            return execute_report(1, "SELECT * FROM t", POOL, **params)

    def test_l1_expiry_discards_derived(self):
        """✅ Review Focus：L1 条目过期后，派生态必须一起消失。"""
        self._run(page=1, sorts=[("v", "asc")])
        self.assertEqual(self.calls["sort"], 1)

        entry = self.cache._cache[1]
        entry.timestamp -= (self.cache._ttl + 1)   # 强制过期

        self._run(page=1, sorts=[("v", "asc")])
        self.assertEqual(self.calls["sort"], 2,
                         "L1 过期后必须重算，派生态不得比 L1 活得久")

    def test_refresh_discards_derived(self):
        """✅ refresh=True（先删后查）必须重算。"""
        self._run(page=1, sorts=[("v", "asc")])
        self._run(page=1, sorts=[("v", "asc")], refresh=True)
        self.assertEqual(self.calls["sort"], 2)

    def test_force_rebuild_discards_derived(self):
        """✅ force_rebuild=True（保活先算后换）必须重算并回填。"""
        self._run(page=1, sorts=[("v", "asc")])
        self._run(page=1, sorts=[("v", "asc")], force_rebuild=True)
        self.assertEqual(self.calls["sort"], 2)

    def test_force_rebuild_serves_new_data(self):
        """✅ 最关键：数据源换了内容后，派生态不得返回旧行序。"""
        r1 = self._run(page=1, sorts=[("v", "desc")])
        self.assertEqual(r1.results[0]["rows"][0], (50, "v050"))

        new_rows = [{"columns": ["id", "v"],
                     "rows": [(i, f"n{i:03d}") for i in range(900, 950)]}]
        with patch("report.db.execute_mysql_query", return_value=new_rows), \
             patch("report.db.create_mysql_connection", return_value=MagicMock()), \
             patch("report.filter_rows", self.cfilter), \
             patch("report.sort_rows", self.csort):
            r2 = execute_report(1, "SELECT * FROM t", POOL,
                                report=REPORT_CFG, cache=self.cache,
                                page=1, page_size=10,
                                sorts=[("v", "desc")], force_rebuild=True)

        # 旧数据按 v 降序首行是 (50,'v050')，新数据是 (949,'n949')。
        # 断言拿到新数据的首行，即证明派生态没有返回跨版本的旧结果。
        self.assertEqual(r1.results[0]["rows"][0], (50, "v050"))
        self.assertEqual(r2.results[0]["rows"][0], (949, "n949"),
                         "保活重建后必须返回新数据，不能命中旧派生态")

    def test_lru_is_bounded(self):
        """✅ 派生态条目数有上限，防止乱点筛选撑爆内存。"""
        for i in range(report._DERIVED_CACHE_MAX + 4):
            self._run(page=1, filters=[("v", "contains", f"v{i:03d}")])
        entry = self.cache._cache[1]
        self.assertLessEqual(len(entry.derived), report._DERIVED_CACHE_MAX)

    def test_write_report_never_uses_derived(self):
        """✅ 含写语句的报表本就不走缓存，每次都必须真跑。"""
        cfg = dict(REPORT_CFG, allow_write=1)
        for _ in range(2):
            with patch("report.db.execute_mysql_query", return_value=ROWS), \
                 patch("report.db.create_mysql_connection",
                       return_value=MagicMock()), \
                 patch("report.filter_rows", self.cfilter), \
                 patch("report.sort_rows", self.csort):
                execute_report(1, "DELETE FROM t", POOL, report=cfg,
                               cache=self.cache, page_size=10,
                               sorts=[("v", "asc")])
        self.assertEqual(self.calls["sort"], 2,
                         "写报表禁缓存短路，每次都应真实执行")


class TestSnapshotFormatUnchanged(unittest.TestCase):
    """Global Constraint #2 的兜底：派生态绝不能泄漏进 Redis 快照。"""

    def test_snapshot_json_excludes_derived(self):
        """✅ 快照 JSON 不含 derived 字段。"""
        snap = redis_cache.ReportSnapshot(
            ROWS, "SELECT * FROM t", 100.0, "v1", truncated=False)
        payload = snap.to_json()
        self.assertNotIn("derived", payload)
        self.assertEqual(redis_cache._SNAPSHOT_VERSION, 2)

    def test_cached_result_derived_not_serialized_anywhere(self):
        """✅ CachedResult 带 derived 字段，但它不参与任何序列化。"""
        self.assertIn("derived", report.CachedResult.__slots__,
                      "CachedResult 应带 derived 字段")
        entry = report.CachedResult(ROWS, "SELECT * FROM t")
        entry.derived[("k",)] = ["污染"]
        snap = redis_cache.ReportSnapshot(
            entry.results, entry.sql_query, entry.timestamp, "v1")
        payload = snap.to_json()
        self.assertNotIn("derived", payload)
        self.assertNotIn("污染", payload)


if __name__ == "__main__":
    unittest.main()
