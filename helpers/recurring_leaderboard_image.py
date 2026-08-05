"""Rich recurring-leaderboard image + height-budget helpers."""

from __future__ import annotations

import math
from datetime import date, datetime
from io import BytesIO
from typing import Any, Dict, List, Optional, Sequence, Union

from PIL import Image, ImageDraw, ImageFont

from helpers.views import LeaderboardImageGenerator

LEADERBOARD_N_CANDIDATES = (5, 10, 15, 20, 25, 30)
DEFAULT_MAX_IMAGE_HEIGHT = 3500
CHIPS_PER_ROW = 10


def estimate_recurring_leaderboard_height(
    n_players: int,
    picks_per_player: Union[Sequence[int], int],
    *,
    base_height: int = 120,
    header_row_height: int = 50,
    chip_row_height: int = 50,
    chips_per_row: int = CHIPS_PER_ROW,
    title_block: int = 60,
    footer_block: int = 40,
) -> int:
    """Estimate PNG height for N players given pick counts (list or uniform int)."""
    if isinstance(picks_per_player, int):
        picks = [max(0, picks_per_player)] * max(0, n_players)
    else:
        picks = list(picks_per_player)[:n_players]
        while len(picks) < n_players:
            picks.append(0)
    height = base_height + title_block + footer_block
    for count in picks:
        chip_rows = math.ceil(count / chips_per_row) if count > 0 else 0
        height += header_row_height + chip_rows * chip_row_height
    return height


def select_leaderboard_n(
    picks_per_player: Sequence[int],
    *,
    max_height: int = DEFAULT_MAX_IMAGE_HEIGHT,
    candidates: Sequence[int] = LEADERBOARD_N_CANDIDATES,
    target: int = 10,
    **kwargs: Any,
) -> int:
    """Pick largest N in candidates that fits height budget; prefer ``target`` when it fits."""
    available = len(picks_per_player)
    if available <= 0:
        return 0
    fitting: list[int] = []
    for n in candidates:
        use = min(n, available)
        h = estimate_recurring_leaderboard_height(use, list(picks_per_player)[:use], **kwargs)
        if h <= max_height:
            fitting.append(use)
    if not fitting:
        return min(int(candidates[0]), available)
    preferred = min(target, available)
    if preferred in fitting:
        return preferred
    at_or_below = [f for f in fitting if f <= preferred]
    if at_or_below:
        return max(at_or_below)
    return max(fitting)


class RecurringLeaderboardImageGenerator:
    """Rich leaderboard with stock chips for recurring channel pushes."""

    def __init__(
        self,
        width: int = 1100,
        theme: str = "discord_dark",
        header_row_height: int = 50,
        chip_row_height: int = 50,
        chips_per_row: int = CHIPS_PER_ROW,
        max_height: int = DEFAULT_MAX_IMAGE_HEIGHT,
    ):
        self.width = width
        self.theme = theme
        self.header_row_height = header_row_height
        self.chip_row_height = chip_row_height
        self.chips_per_row = chips_per_row
        self.max_height = max_height
        self._simple = LeaderboardImageGenerator(width=width, theme=theme)
        self.colors = dict(self._simple.colors)
        self.colors["chip_bg"] = (64, 68, 75)
        self.fonts = dict(self._simple.fonts)
        self.font_sizes = {
            "title": 22,
            "header": 14,
            "text": 13,
            "small": 10,
            "ticker": 12,
        }
        self._load_extra_fonts()

    def _load_extra_fonts(self) -> None:
        font_paths = [
            "arial.ttf",
            "Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
        for name, size in self.font_sizes.items():
            loaded = False
            for path in font_paths:
                try:
                    self.fonts[name] = ImageFont.truetype(path, size)
                    loaded = True
                    break
                except (OSError, IOError):
                    continue
            if not loaded and name not in self.fonts:
                self.fonts[name] = ImageFont.load_default()

    def create_image(
        self,
        game_data: Dict[str, Any],
        players: List[Dict[str, Any]],
        *,
        target_n: int = 10,
    ) -> BytesIO:
        picks_counts = [len(p.get("picks") or []) for p in players]
        n = select_leaderboard_n(
            picks_counts,
            max_height=self.max_height,
            target=target_n,
            header_row_height=self.header_row_height,
            chip_row_height=self.chip_row_height,
            chips_per_row=self.chips_per_row,
        )
        players = players[:n]
        height = estimate_recurring_leaderboard_height(
            len(players),
            [len(p.get("picks") or []) for p in players],
            header_row_height=self.header_row_height,
            chip_row_height=self.chip_row_height,
            chips_per_row=self.chips_per_row,
        )
        img = Image.new("RGB", (self.width, height), self.colors["bg"])
        draw = ImageDraw.Draw(img)
        y = 20
        title = f"{game_data.get('name', 'Game')} (ID: {game_data.get('id', 'N/A')})"
        y = self._simple._draw_centered_text(draw, title, y, self.fonts["title"], self.colors["text"])
        y += 10
        y = self._draw_column_header(draw, y)
        for idx, player in enumerate(players):
            y = self._draw_player_block(draw, player, idx, y)
        draw.text(
            (20, height - 28),
            "StockBot · recurring leaderboard",
            fill=self.colors["footer"],
            font=self.fonts["small"],
        )
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    def _draw_column_header(self, draw: ImageDraw.ImageDraw, y: int) -> int:
        draw.rectangle([0, y, self.width, y + 36], fill=self.colors["header"])
        cols = [
            (16, "Rank"),
            (70, "Investor"),
            (280, "Portfolio"),
            (420, "$"),
            (520, "%"),
            (620, "Days #1"),
            (720, "Joined"),
        ]
        for x, label in cols:
            draw.text((x, y + 8), label, fill=self.colors["text"], font=self.fonts["header"])
        return y + 36

    def _draw_arrow(self, draw: ImageDraw.ImageDraw, x: int, y: int, up: bool) -> None:
        color = self.colors["positive"] if up else self.colors["negative"]
        if up:
            points = [(x + 5, y), (x, y + 10), (x + 10, y + 10)]
        else:
            points = [(x, y), (x + 10, y), (x + 5, y + 10)]
        draw.polygon(points, fill=color)

    def _draw_player_block(
        self,
        draw: ImageDraw.ImageDraw,
        player: Dict[str, Any],
        idx: int,
        y: int,
    ) -> int:
        row_bg = self.colors["row_bg_1"] if idx % 2 == 0 else self.colors["row_bg_2"]
        draw.rectangle([0, y, self.width, y + self.header_row_height], fill=row_bg)
        rank_color = self._simple._get_rank_color(idx)
        draw.text((16, y + 15), f"{idx + 1}.", fill=rank_color, font=self.fonts["text"])
        name = str(player.get("display_name") or f"ID({player.get('user_id')})")
        if len(name) > 18:
            name = name[:17] + "~"
        draw.text((70, y + 15), name, fill=self.colors["text"], font=self.fonts["text"])
        value = float(player.get("current_value") or 0)
        draw.text((280, y + 15), f"${value:,.2f}", fill=self.colors["text"], font=self.fonts["text"])
        d_chg = float(player.get("change_dollars") or 0)
        d_color = self.colors["positive"] if d_chg >= 0 else self.colors["negative"]
        draw.text((420, y + 15), f"${d_chg:+,.2f}", fill=d_color, font=self.fonts["text"])
        p_chg = float(player.get("change_percent") or 0)
        p_color = self.colors["positive"] if p_chg >= 0 else self.colors["negative"]
        draw.text((520, y + 15), f"{p_chg:+.2f}%", fill=p_color, font=self.fonts["text"])
        days = int(player.get("days_in_first") or 0)
        draw.text((620, y + 15), str(days), fill=self.colors["text"], font=self.fonts["text"])
        joined = player.get("joined")
        if isinstance(joined, (datetime, date)):
            joined_s = joined.strftime("%Y-%m-%d")
        else:
            joined_s = str(joined or "")[:10]
        draw.text((720, y + 15), joined_s, fill=self.colors["text"], font=self.fonts["text"])
        y += self.header_row_height

        picks = list(player.get("picks") or [])
        for row_i in range(0, len(picks), self.chips_per_row):
            row_picks = picks[row_i : row_i + self.chips_per_row]
            draw.rectangle([0, y, self.width, y + self.chip_row_height], fill=row_bg)
            chip_w = (self.width - 24) // self.chips_per_row
            for ci, pick in enumerate(row_picks):
                x0 = 12 + ci * chip_w
                self._draw_chip(draw, x0, y + 4, chip_w - 6, self.chip_row_height - 8, pick)
            y += self.chip_row_height
        return y

    def _draw_chip(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        w: int,
        h: int,
        pick: Dict[str, Any],
    ) -> None:
        draw.rounded_rectangle([x, y, x + w, y + h], radius=6, fill=self.colors["chip_bg"])
        ticker = str(pick.get("ticker") or pick.get("stock_ticker") or "?")[:8]
        company = str(pick.get("company") or pick.get("company_name") or "")[:14]
        pct = float(pick.get("change_percent") or 0)
        draw.text(
            (x + 6, y + 4),
            ticker,
            fill=self.colors["text"],
            font=self.fonts.get("ticker", self.fonts["small"]),
        )
        if company:
            draw.text((x + 6, y + 18), company, fill=self.colors["footer"], font=self.fonts["small"])
        self._draw_arrow(draw, x + w - 36, y + 8, up=pct >= 0)
        pct_color = self.colors["positive"] if pct >= 0 else self.colors["negative"]
        draw.text((x + w - 24, y + 6), f"{pct:+.1f}", fill=pct_color, font=self.fonts["small"])
