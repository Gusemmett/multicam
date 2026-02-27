"""Time formatting utilities."""


def format_time_us(t_us: int) -> str:
    """Format microseconds to ffmpeg time string HH:MM:SS.mmm"""
    if t_us < 0:
        t_us = 0
    total_ms = int(round(t_us / 1000))
    ms = total_ms % 1000
    total_s = total_ms // 1000
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = total_m // 60
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
