"""Render a solved.ac profile and streak calendar as a PNG."""

import argparse
import json
import re
import ssl
from calendar import SUNDAY, day_abbr, month_abbr
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
PROXY_ENTRY = re.compile(
    r"""\s*(?:export\s+)?SOLVED_PROXY\s*=\s*"""
    r"""(?:"([^"]*)"|'([^']*)'|([^#\s]*))\s*(?:#.*)?"""
)

# https://help.solved.ac/ko/stats/ac-rating
TIER_RATINGS = (
    0,
    30, 60, 90, 120, 150,
    200, 300, 400, 500, 650,
    800, 950, 1100, 1250, 1400,
    1600, 1750, 1900, 2000, 2100,
    2200, 2300, 2400, 2500, 2600,
    2700, 2800, 2850, 2900, 2950,
    3000,
)
TIER_STYLES = (
    ("Bronze", "#f3b889", "#3b2b23"),
    ("Silver", "#c6d7e9", "#2b3945"),
    ("Gold", "#ffd780", "#3e3525"),
    ("Platinum", "#8fdfbc", "#203b32"),
    ("Diamond", "#a5d9ff", "#263948"),
    ("Ruby", "#ffafc6", "#432a36"),
)
DIVISIONS = ("V", "IV", "III", "II", "I")
CARD_BACKGROUND = "#101716"
PROFILE_BACKGROUND = "#17211e"
TEXT_COLOR = "#edf4f0"
MUTED_TEXT_COLOR = "#a8bcb1"
DIVIDER_COLOR = "#2e3d37"
SOLVED_COLORS = (
    (0, "#26332e"),
    (1, "#1b653e"),
    (2, "#278954"),
    (4, "#3eb96e"),
    (8, "#77df9b"),
)
STATUS_MARKERS = (
    ("freezeUsed", "#74baff"),
    ("streakRepaired", "#d396ee"),
    ("onVacation", "#f2bd70"),
)


def load_proxy(path):
    proxy = ""
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            match = PROXY_ENTRY.fullmatch(line)
            if match:
                proxy = next(value for value in match.groups() if value is not None).strip()

    url = urlsplit(proxy)
    if url.scheme not in ("http", "https") or not url.hostname or url.query or url.fragment:
        raise ValueError(".env의 SOLVED_PROXY에 프록시 기본 URL을 설정해 주세요.")
    return url.geturl().rstrip("/")


def tls_context():
    try:
        import truststore
    except ImportError:
        raise RuntimeError("truststore가 필요합니다. python3 -m pip install truststore") from None
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def fetch_json(proxy, endpoint, context, query=None):
    url = proxy + endpoint
    if query:
        url += "?" + urlencode(query)
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "boj-streak/1.0"})
    try:
        with urlopen(request, timeout=20, context=context) as response:
            return json.load(response)
    except HTTPError as error:
        with error:
            if error.code == 400 and endpoint == "/api/solved-streak" and query:
                raise RuntimeError("스트릭 API가 요청한 날짜 범위를 허용하지 않습니다 (HTTP 400).") from None
            raise RuntimeError(f"{endpoint} 요청에 실패했습니다 (HTTP {error.code}).") from None
    except OSError as error:
        raise RuntimeError(f"{endpoint}에 연결하지 못했습니다. {error}") from None
    except ValueError:
        raise RuntimeError(f"{endpoint}에서 유효한 JSON을 읽지 못했습니다.") from None


def tier_style(tier):
    if 1 <= tier <= 30:
        group, division = divmod(tier - 1, 5)
        name, ink, background = TIER_STYLES[group]
        return f"{name} {DIVISIONS[division]}", ink, background
    if tier == 31:
        return "Master", "#d5bcff", "#39314b"
    name = "Unrated" if tier == 0 else "Unknown tier"
    return name, MUTED_TEXT_COLOR, DIVIDER_COLOR


def draw_profile(draw, profile, height, label_font):
    left, right = 46, 330
    value_font = label_font.font_variant(size=30)

    draw.rounded_rectangle((20, 22, 356, height - 22), radius=22,
                           fill=PROFILE_BACKGROUND, outline=DIVIDER_COLOR, width=2)

    handle = profile["handle"]
    handle_font = label_font.font_variant(size=44)
    handle_width = draw.textlength(handle, font=handle_font)
    if handle_width > right - left:
        handle_font = label_font.font_variant(size=int(44 * (right - left) / handle_width))
    draw.text((left, 65), handle, font=handle_font, fill=TEXT_COLOR, anchor="lm")

    tier = profile["tier"]
    tier_label, tier_ink, tier_background = tier_style(tier if tier is not None else -1)
    pill_width = round(draw.textlength(tier_label, font=label_font)) + 32
    draw.rounded_rectangle((left, 98, left + pill_width, 135), radius=18, fill=tier_background)
    draw.text((left + 16, 117), tier_label, font=label_font, fill=tier_ink, anchor="lm")

    rating = profile["rating"]
    class_decoration = "+" if profile["classPlus"] else ""
    stats = (
        ("Rating", f"{rating:,}"),
        ("Solved", f"{profile['solvedCount']:,}"),
        ("CLASS", f"{profile['level']}{class_decoration}"),
    )
    stats_top, stats_bottom = 153, height - 128
    row_height = (stats_bottom - stats_top) // len(stats)
    for index, (label, value) in enumerate(stats):
        y = stats_top + row_height * index
        draw.line((left, y, right, y), fill=DIVIDER_COLOR, width=2)
        center = y + row_height // 2
        draw.text((left, center), label, font=label_font, fill=MUTED_TEXT_COLOR, anchor="lm")
        draw.text((right, center), value, font=value_font, fill=TEXT_COLOR, anchor="rm")

    if tier is None or not 0 <= tier < len(TIER_RATINGS) - 1:
        return
    tier_floor, next_rating = TIER_RATINGS[tier:tier + 2]
    if not tier_floor <= rating < next_rating:
        return

    target, _, _ = tier_style(tier + 1)
    progress = (rating - tier_floor) / (next_rating - tier_floor)
    bar_y = height - 83
    draw.line((left, stats_bottom, right, stats_bottom), fill=DIVIDER_COLOR, width=2)
    draw.text((left, bar_y - 20), "Next tier", font=label_font, fill=TEXT_COLOR, anchor="lm")
    draw.text((right, bar_y - 20), f"{int(progress * 100)}%", font=label_font, fill=tier_ink, anchor="rm")
    draw.rounded_rectangle((left, bar_y, right, bar_y + 9), radius=4, fill=DIVIDER_COLOR)
    bar_width = round((right - left) * progress)
    if bar_width:
        draw.rounded_rectangle((left, bar_y, left + bar_width, bar_y + 9), radius=4, fill=tier_ink)
    draw.text((left, bar_y + 21), f"{target} · {next_rating - rating:,} points to go",
              font=label_font, fill=MUTED_TEXT_COLOR, anchor="lt")


def render_card(profile, streak):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        raise RuntimeError("Pillow가 필요합니다. python3 -m pip install 'Pillow>=10.1'") from None

    for font_file in ("PretendardVariable.ttf", "Pretendard-Regular.otf", "Pretendard-Regular.ttf"):
        try:
            label_font = ImageFont.truetype(font_file, size=22)
            break
        except OSError:
            continue
    else:
        raise RuntimeError("Pretendard 글꼴을 찾지 못했습니다. Pretendard Variable 또는 Regular를 설치해 주세요.")

    start = date.fromisoformat(streak["from"])
    end = date.fromisoformat(streak["to"])
    if start > end:
        raise ValueError("Invalid calendar range")
    start_row = (start.weekday() - SUNDAY) % 7
    weeks = ((end - start).days + start_row) // 7 + 1
    pitch = max(34, min(52, 1280 // weeks))
    cell = pitch - 8
    grid_height = 6 * pitch + cell
    height = max(444, grid_height + 92)
    margin, grid_x = 392, 466
    month_offset = 32
    grid_y = (height - grid_height + month_offset) // 2
    width = grid_x + (weeks - 1) * pitch + cell + 42
    right = width - 42

    image = Image.new("RGB", (width, height), CARD_BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw_profile(draw, profile, height, label_font)
    for row in range(7):
        label = day_abbr[(SUNDAY + row) % 7]
        draw.text((margin, grid_y + row * pitch + cell // 2), label,
                  font=label_font, fill=MUTED_TEXT_COLOR, anchor="lm")

    month_labels = []
    for entry in sorted(streak["days"], key=lambda entry: entry["day"]):
        day = date.fromisoformat(entry["day"])
        if not start <= day <= end:
            raise ValueError("Calendar entry outside requested range")
        column, row = divmod((day - start).days + start_row, 7)
        x, y = grid_x + column * pitch, grid_y + row * pitch
        if day == start or day.day == 1:
            month_labels.append((x, month_abbr[day.month]))

        count = entry["solvedCount"]
        fill = next(color for minimum, color in reversed(SOLVED_COLORS) if count >= minimum)
        draw.rounded_rectangle((x, y, x + cell - 1, y + cell - 1), radius=5, fill=fill)
        for index, (key, color) in enumerate(STATUS_MARKERS):
            if entry[key]:
                marker_x = x + cell // 2 + (index - 1) * 8
                marker_y = y + cell // 2
                draw.ellipse((marker_x - 4, marker_y - 4, marker_x + 3, marker_y + 3),
                             fill=color, outline=CARD_BACKGROUND)

    # Prefer the next full month when the leading partial month has little room.
    label_limit = right
    for x, label in reversed(month_labels):
        label_width = draw.textlength(label, font=label_font)
        x = min(x, right - label_width)
        if x + label_width <= label_limit:
            draw.text((x, grid_y - month_offset), label, font=label_font, fill=MUTED_TEXT_COLOR, anchor="lt")
            label_limit = x - 8

    return image


def main():
    parser = argparse.ArgumentParser(description="solved.ac 프로필과 스트릭 달력을 PNG로 저장합니다.")
    parser.add_argument(
        "-o", "--output", type=Path, default=ROOT / "src" / "solvedac-streak.png",
        help="저장 경로 (기본값 저장소의 src/solvedac-streak.png)",
    )
    parser.add_argument("--range", nargs=2, type=date.fromisoformat, metavar=("FROM", "TO"),
                        help="조회 시작일과 종료일 (YYYY-MM-DD, 생략하면 API 기본 기간)")
    args = parser.parse_args()
    query = None
    if args.range:
        start, end = args.range
        if start > end:
            parser.error("조회 시작일은 종료일과 같거나 그 이전이어야 합니다.")
        query = {"from": start.isoformat(), "to": end.isoformat()}

    try:
        proxy = load_proxy(ROOT / ".env")
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")

    try:
        context = tls_context()
        profile = fetch_json(proxy, "/api/solved-profile", context)
        streak = fetch_json(proxy, "/api/solved-streak", context, query)
        image = render_card(profile, streak)
    except (KeyError, TypeError, ValueError, StopIteration):
        parser.exit(1, "API 응답에서 프로필 또는 스트릭 데이터를 읽지 못했습니다.\n")
    except RuntimeError as error:
        parser.exit(1, f"{error}\n")

    try:
        with TemporaryDirectory(dir=args.output.parent) as directory:
            temporary = Path(directory) / "streak.png"
            image.save(temporary, format="PNG", optimize=True)
            temporary.replace(args.output)
    except OSError as error:
        parser.exit(1, f"PNG를 저장하지 못했습니다. {error}\n")

    print(f"프로필과 스트릭 그래프를 저장했습니다. {args.output}")


if __name__ == "__main__":
    main()
