"""Unit tests for the FFmpeg drawtext filter and command builder."""

from pathlib import Path

from bot.database.db import UserSettings
from bot.services.ffmpeg import (
    build_drawtext_filter,
    build_ffmpeg_cmd,
    escape_drawtext,
)


def test_escape_drawtext_special_characters() -> None:
    raw = "Channel: @Test's 100% Free\\Video\nLine2"
    escaped = escape_drawtext(raw)
    assert r"\:" in escaped
    assert r"\'" in escaped
    assert r"\%" in escaped
    assert "\n" not in escaped


def test_build_drawtext_filter_static_positions() -> None:
    cfg = UserSettings(
        user_id=123,
        watermark_text="MyBrand",
        position="top-right",
        font_size=32,
        color="yellow",
        opacity=0.5,
        moving=False,
    )
    vf = build_drawtext_filter(cfg, font_path="")
    assert vf.startswith("drawtext=")
    assert "text='MyBrand'" in vf
    assert "fontsize=32" in vf
    assert "fontcolor=yellow@0.50" in vf
    assert "x=w-tw-24" in vf
    assert "y=24" in vf


def test_build_drawtext_filter_moving_mode() -> None:
    cfg = UserSettings(
        user_id=456,
        watermark_text="MovingText",
        moving=True,
    )
    vf = build_drawtext_filter(cfg, font_path="")
    assert "x=w-mod(t*90\\,w+tw)" in vf
    assert "sin(t*0.8)" in vf


def test_build_ffmpeg_cmd_structure() -> None:
    cfg = UserSettings(user_id=789, watermark_text="Hello")
    cmd = build_ffmpeg_cmd(
        input_path=Path("/tmp/in.mp4"),
        output_path=Path("/tmp/out.mp4"),
        user_settings=cfg,
        font_path="",
    )
    assert "-c:v" in cmd and "libx264" in cmd
    assert "-preset" in cmd and "veryfast" in cmd
    assert "-c:a" in cmd and "copy" in cmd
    assert "-progress" in cmd and "pipe:1" in cmd
    assert cmd[-1] == "/tmp/out.mp4"
