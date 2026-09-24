from kitling_bigqmt.strategy_catalog_page import catalog_html


def test_strategy_page_exposes_preview_and_install_request_without_order_controls():
    page = catalog_html()
    assert "生成推送预览" in page
    assert "请求安装（不启动）" in page
    assert "/api/v1/strategy-install-request" in page
    assert "orders_enabled=false" in page
    assert "安装后不自动启动" in page

