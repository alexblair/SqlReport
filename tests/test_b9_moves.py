"""B9-1：render.py 七个大常量外移到 ui_assets.py 的字节护栏测试。

纯搬移任务：符号取值与 vendor hash 必须逐字节不变。
"""
import hashlib
import unittest


class TestAssetsByteIdentical(unittest.TestCase):
    """B9-1：常量外移是纯搬移，取值与 vendor hash 必须逐字节不变。"""

    BASELINE = {
        "_BASE_CSS": ("ae3a4bbd0272f2a2", 9055),
        "_COMMON_CSS": ("bb7ec576421bc83e", 79531),
        "_COMMON_JS": ("5bcbeaccdfb1c635", 21412),
        "_MD_CSS": ("c352588586b20dc3", 2492),
        "_SQL_HIGHLIGHT_JS": ("b747870a03686a41", 1343),
        "_SQL_FORMATTER_JS": ("b46730d48db26945", 3116),
        "_API_TEMPLATE_JS": ("d59b15d3f972c38e", 7611),
        "_EXCL_EDITOR_JS": ("acd4d5e83cde6b4a", 7434),
    }

    def test_render_constants_match_baseline(self):
        import render
        for name, (want_h, want_len) in self.BASELINE.items():
            val = getattr(render, name, None)
            self.assertIsInstance(val, str, f"render.{name} 不在了")
            self.assertEqual(len(val), want_len, f"{name} 长度变了")
            self.assertEqual(hashlib.sha256(val.encode()).hexdigest()[:16], want_h,
                             f"{name} 字节变了")

    def test_vendor_hash8_unchanged(self):
        """vendor 目录名 self@{hash8} 必须不变（否则静态资源 URL 变化）。"""
        import render
        self.assertEqual(
            render.content_hash8(render._COMMON_CSS + "\n;;;\n" + render._COMMON_JS),
            "72429792")

    def test_ui_assets_exists_and_render_reexports(self):
        """外移后 render 必须继续导出这些名字（config/report 从 render 导入）。"""
        import render
        import ui_assets
        self.assertTrue(hasattr(ui_assets, "COMMON_CSS")
                        or hasattr(ui_assets, "_COMMON_CSS"),
                        "ui_assets 未提供 COMMON_CSS")
        # config / report 的导入路径必须仍可用
        from render import _MD_CSS, _SQL_FORMATTER_JS, _SQL_HIGHLIGHT_JS  # noqa: F401


class TestConfigNamespacePreserved(unittest.TestCase):
    """B9-2：config.py 按实体拆分进 config_pages/ 后，config.<name> 兼容再导出层

    不得缺失任何符号。基线由 Lead 现查并落盘
    run-logs/b9-2-config-namespace-baseline-20261010.json：dir(config) 公开符号 139 个。
    拆分后**不允许缺失**（允许新增）。
    """

    NAMESPACE_BASELINE = (
        "ALL_KEYS", "SINGLE_KEYS", "_CONFIG_EXTRA_CSS", "_CONFIG_MD_EXTRA_CSS", "_MD_CSS",
        "_PATH_PATTERN", "_PREVIEW_MAX_ROWS", "_REPORTS_EXTRA_CSS", "_SQL_FORMATTER_JS",
        "_SQL_HIGHLIGHT_JS", "_WARN_BOX_STYLE", "_build_desc_summary_html", "_category_from_form",
        "_echo_int", "_endpoint_from_form", "_endpoint_unique_error", "_escape",
        "_estimate_result_count", "_get_depth", "_icon", "_link_btn", "_nav_badges",
        "_normalize_api_url_path", "_parse_endpoint_form", "_parse_form_data", "_parse_report_form",
        "_parse_rule_json", "_pool_from_form", "_pool_test_error_hint", "_redirect_or_render",
        "_render_branding_anchor", "_render_branding_section", "_render_cat_opts",
        "_render_category_section", "_render_category_section_parts", "_render_pool_form",
        "_render_pool_section", "_render_report_form", "_render_user_form", "_render_user_section",
        "_report_form_cat_options", "_report_form_html", "_report_form_js_editor_api",
        "_report_form_js_formatter", "_report_form_js_highlight", "_report_form_pool_options",
        "_report_from_form", "_save_or_render", "_scheduler_flash_url", "_scheduler_prefill",
        "_template_raw_for_format", "_tolerant_int", "_user_from_form", "_validate_json_template",
        "api_handler", "app_config", "auth", "branding", "build_api_endpoint_form_html",
        "build_api_endpoint_preview_help_html", "build_api_endpoints_list_html",
        "build_category_manage_section_html", "build_category_opts_html",
        "build_category_section_html",
        "build_config_filter_box_html", "build_flash_html", "build_pool_form_html",
        "build_pool_section_html", "build_report_schedule_summary_html", "build_scheduler_page_html",
        "build_scheduler_task_form_html", "build_user_form_html", "build_user_section_html",
        "config_db", "db", "handle_api_endpoint_add", "handle_api_endpoint_delete",
        "handle_api_endpoint_edit", "handle_api_endpoint_preview", "handle_api_endpoints_request",
        "handle_api_key_actions", "handle_batch_cache", "handle_batch_delete", "handle_batch_pool",
        "handle_batch_set_category", "handle_category_add", "handle_category_delete",
        "handle_category_edit", "handle_description_preview", "handle_import_test_cases",
        "handle_memo_preview", "handle_pool_add", "handle_pool_copy", "handle_pool_delete",
        "handle_pool_edit", "handle_pool_test", "handle_report_add", "handle_report_copy",
        "handle_report_delete", "handle_report_edit", "handle_report_move_category", "handle_request",
        "handle_scheduler_delete", "handle_scheduler_request", "handle_scheduler_run",
        "handle_scheduler_save", "handle_scheduler_toggle", "handle_site_branding_save",
        "handle_user_add", "handle_user_delete", "handle_user_edit", "html_mod", "json", "logging",
        "markdown_render", "parse_config_path", "parse_result_names", "preset_cases", "re",
        "redis_cache", "render_api_endpoint_form_page", "render_api_endpoints_page",
        "render_category_form_page", "render_overview", "render_page_footer", "render_page_header",
        "render_pool_form_page", "render_pools_page", "render_report_form_page",
        "render_reports_page", "render_scheduler_form_page", "render_scheduler_page",
        "render_user_form_page", "render_users_page", "sql_contains_write", "static_cache", "time",
        "urllib", "validate_template",
    )

    # 这 6 个是 config.py 自身 import 的副产物，拆分后最易丢失
    IMPORT_BYPRODUCTS = (
        "db", "json", "_escape", "_CONFIG_EXTRA_CSS", "_REPORTS_EXTRA_CSS",
        "build_api_endpoint_form_html",
    )

    # 已搬出的实体簇（config_pages.<name>）
    EXPECTED_CLUSTERS = {
        "branding": 3, "users": 8, "pools": 11, "categories": 9,
        "scheduler": 9, "api_endpoints": 14, "reports": 16,
    }

    def _submodules(self):
        import importlib
        import pkgutil
        import config_pages
        return [importlib.import_module(f"config_pages.{m.name}")
                for m in pkgutil.iter_modules(config_pages.__path__)]

    def _defined_here(self, mod):
        """该子模块中「定义于本模块」的函数（排除 import 进来的共享助手）。"""
        import inspect
        return {n: o for n, o in vars(mod).items()
                if inspect.isfunction(o) and o.__module__ == mod.__name__}

    def test_no_public_symbol_missing(self):
        """拆分后 config. 命名空间相对基线不得缺失（允许新增）。"""
        import config
        missing = sorted(set(self.NAMESPACE_BASELINE) - set(dir(config)))
        self.assertEqual(missing, [], f"config. 命名空间缺失符号: {missing}")

    def test_import_byproducts_still_available(self):
        import config
        missing = [n for n in self.IMPORT_BYPRODUCTS if not hasattr(config, n)]
        self.assertEqual(missing, [], f"config 的 import 副产物丢失: {missing}")

    def test_expected_clusters_extracted(self):
        """config.py 原有 89 个顶层函数：70 个搬入 7 个实体簇，19 个（共享助手/

        入口）留在 config.py。个数断言防止漏搬或重复搬。
        """
        import importlib
        total = 0
        for cluster, expected in self.EXPECTED_CLUSTERS.items():
            mod = importlib.import_module(f"config_pages.{cluster}")
            defined = self._defined_here(mod)
            self.assertEqual(len(defined), expected,
                             f"config_pages.{cluster} 函数数应为 {expected}，实际 {len(defined)}")
            total += len(defined)
        self.assertEqual(total, 70, "搬迁函数总数应为 70（89 - 19 留在 config.py）")

    def test_moved_symbols_reexported_same_object(self):
        """搬出的函数必须仍以同名从 config 再导出，且是同一对象。"""
        import config
        for mod in self._submodules():
            for name, obj in self._defined_here(mod).items():
                self.assertIs(getattr(config, name, None), obj,
                              f"config.{name} 未从 {mod.__name__} 再导出")
                self.assertEqual(obj.__module__, mod.__name__)

    def test_moved_definitions_no_longer_in_config_source(self):
        """证明是「搬移」而非「复制」：config.py 源码里不再有这些 def。"""
        import inspect
        import re
        import config
        src = inspect.getsource(config)
        for mod in self._submodules():
            for name in self._defined_here(mod):
                self.assertNotRegex(src, rf"(?m)^def {re.escape(name)}\(",
                                    f"{name} 仍定义在 config.py（应为纯搬移）")

if __name__ == "__main__":
    unittest.main()
