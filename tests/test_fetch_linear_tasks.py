import fetch_linear_tasks as linear


def test_linear_overlay_height_scales_with_rows():
    # 4 cards/row at the default 1540px overlay width.
    assert linear.linear_overlay_height(0) == linear.EMPTY_HEIGHT
    assert linear.linear_overlay_height(1) == 138
    assert linear.linear_overlay_height(4) == 138
    assert linear.linear_overlay_height(5) == 268
    assert linear.linear_overlay_height(12) == 398
    assert linear.linear_overlay_height(13) == 528
    assert linear.linear_overlay_height(16) == 528
    assert linear.linear_overlay_height(17) == 658


def test_linear_overlay_height_uses_window_width():
    # Narrower window packs fewer cards per row, so needs more height.
    assert linear.linear_overlay_height(4, window_width=700) > linear.linear_overlay_height(
        4, window_width=1540
    )
