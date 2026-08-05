"""Disposable previews of the real recurring-leaderboard image.

Renders ``helpers.recurring_leaderboard_image`` with fake-but-consistent data:
every ticker moves the same amount for everyone, and each player starts at
$10,000 split evenly across 10 picks, so the panel stats derive from the chips.

Delete this file and ``temp_leaderboard_previews/`` when finished.
"""

from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from helpers.recurring_leaderboard_image import RecurringLeaderboardImageGenerator

OUTPUT_DIR = Path(__file__).with_name("temp_leaderboard_previews")
TOP_N_VALUES = (5, 10, 15, 20, 25, 30)
PICKS_PER_PLAYER = 10
STARTING_MONEY = 10_000.0

GAME_NAME = "Stonks Monthly"

# One market for everyone: ticker -> (company, percent change).
MARKET = {
    "NVDA": ("NVIDIA", 34.2),
    "META": ("Meta Platforms", 27.9),
    "AAPL": ("Apple", 19.4),
    "MSFT": ("Microsoft", 15.1),
    "GOOGL": ("Alphabet", 12.6),
    "AMZN": ("Amazon", 9.8),
    "COST": ("Costco", 6.3),
    "JPM": ("JPMorgan Chase", 4.1),
    "UNH": ("UnitedHealth Group", 1.7),
    "NFLX": ("Netflix", -0.9),
    "JNJ": ("Johnson & Johnson", -3.4),
    "TSLA": ("Tesla", -7.2),
    "UAL": ("United Airlines", -11.5),
    "MRNA": ("Moderna", -15.8),
    "GME": ("GameStop Corp.", -22.6),
}

USERNAMES = (
    "nje331", "toaster.exe", "blep", "xX_Sn1per_Xx", "moonshotmike",
    "gg_ez", "vibecheck", "pixelpanda", "not_a_bot", "sussybaka",
    "lowkey_broke", "chungus", "d1amondhands", "bagholder", "ratio'd",
    "skibidi_stonks", "cheeseburger", "yeetcapital", "npc_energy", "grillmaster",
    "404_gains", "buythedip", "smol_bean", "wumpus", "certified_goober",
    "papercut", "tendies", "big_yikes", "goblin_mode", "afk_forever",
)


def fake_players(count: int) -> list[dict]:
    """Players with picks drawn from one shared market, ranked by resulting value."""
    rng = random.Random(20260805)
    tickers = list(MARKET)
    per_pick = STARTING_MONEY / PICKS_PER_PLAYER

    players = []
    for index in range(count):
        chosen = rng.sample(tickers, k=PICKS_PER_PLAYER)
        picks = [
            {"ticker": t, "company": MARKET[t][0], "change_percent": MARKET[t][1]}
            for t in chosen
        ]
        gain = sum(per_pick * MARKET[t][1] / 100 for t in chosen)
        players.append(
            {
                "user_id": 10_000 + index,
                "display_name": USERNAMES[index],
                "current_value": STARTING_MONEY + gain,
                "change_dollars": gain,
                "change_percent": gain / STARTING_MONEY * 100,
                "picks": picks,
            }
        )

    players.sort(key=lambda p: p["current_value"], reverse=True)
    # Days in first only accrue for players who have actually led at some point.
    for rank, player in enumerate(players):
        player["days_in_first"] = max(0, 12 - rank * 4)
    return players


def game_for(top_n: int) -> dict:
    rng = random.Random(top_n)
    game_id = "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(5))
    return {"name": GAME_NAME, "id": game_id}


def label_card(path: Path, label: str, target_width: int) -> Image.Image:
    with Image.open(path) as source:
        image = source.convert("RGB")
    height = round(image.height * target_width / image.width)
    scaled = image.resize((target_width, height), Image.Resampling.LANCZOS)
    card = Image.new("RGB", (target_width, height + 30), (30, 31, 34))
    card.paste(scaled, (0, 30))
    ImageDraw.Draw(card).text((10, 9), label, fill="white", font=ImageFont.load_default())
    return card


def contact_sheet(cards: list[Image.Image], columns: int = 2, gutter: int = 18) -> Image.Image:
    card_w = cards[0].width
    rows = [cards[i : i + columns] for i in range(0, len(cards), columns)]
    sheet_w = card_w * columns + gutter * (columns - 1)
    sheet_h = sum(max(c.height for c in row) for row in rows) + gutter * (len(rows) - 1)
    sheet = Image.new("RGB", (sheet_w, sheet_h), (17, 18, 20))
    y = 0
    for row in rows:
        for col, card in enumerate(row):
            sheet.paste(card, (col * (card_w + gutter), y))
        y += max(c.height for c in row) + gutter
    return sheet


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    # Raise the budget so every size renders in full instead of being trimmed.
    generator = RecurringLeaderboardImageGenerator(max_height=10_000)
    cards = []
    for top_n in TOP_N_VALUES:
        buffer = generator.create_image(game_for(top_n), fake_players(top_n), target_n=top_n)
        path = OUTPUT_DIR / f"top_{top_n}.png"
        path.write_bytes(buffer.getvalue())
        cards.append(label_card(path, f"top {top_n}", 520))
    contact_sheet(cards).save(OUTPUT_DIR / "all_top_n_comparison.png")
    print(f"Wrote {len(cards)} previews + contact sheet to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
