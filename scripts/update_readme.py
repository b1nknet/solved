"""Update the BOJ solution index and solved.ac profile statistics in README.md."""

import json
import os
import re
import stat
import sys
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SOLVED_URL = "https://solved.ac"
API_URL = f"{SOLVED_URL}/api/v4"
TIER_ICON_DIR = "src/tiers"
LANGUAGE_ICON_DIR = "src/languages"
LANGUAGE_ICONS = {
    ".c": ("C", "c"),
    ".cc": ("C++", "cplusplus"),
    ".cpp": ("C++", "cplusplus"),
    ".cxx": ("C++", "cplusplus"),
    ".cs": ("C#", "csharp"),
    ".go": ("Go", "go"),
    ".java": ("Java", "java"),
    ".js": ("JavaScript", "javascript"),
    ".kt": ("Kotlin", "kotlin"),
    ".php": ("PHP", "php"),
    ".py": ("Python", "python"),
    ".rb": ("Ruby", "ruby"),
    ".rs": ("Rust", "rust"),
    ".swift": ("Swift", "swift"),
    ".ts": ("TypeScript", "typescript"),
}
KST = timezone(timedelta(hours=9))
TIERS = ("Bronze", "Silver", "Gold", "Platinum", "Diamond", "Ruby")
DIVISIONS = ("V", "IV", "III", "II", "I")
DOTENV_ENTRY = re.compile(
    r"""\s*(?:export\s+)?(API_CLIENT_ID|API_SECRET)\s*=\s*"""
    r"""(?:"([^"]*)"|'([^']*)'|([^#\s]*))\s*(?:#.*)?"""
)


def load_credentials(path):
    file_values = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            match = DOTENV_ENTRY.fullmatch(line)
            if match:
                name, *values = match.groups()
                file_values[name] = next(value for value in values if value is not None)

    credentials = {}
    for name in ("API_CLIENT_ID", "API_SECRET"):
        value = os.environ.get(name) or file_values.get(name, "")
        if not re.fullmatch(r"[!-~]+", value):
            raise ValueError(f".env 또는 환경 변수에 올바른 {name} 값을 설정해 주세요.")
        credentials[name] = value
    return credentials


class SolvedAc:
    def __init__(self, credentials):
        self.credentials = credentials

    def get(self, path, query=None, *, allow_missing=False):
        url = API_URL + path
        if query:
            url += "?" + urlencode(query)
        request = Request(
            url, headers={"Accept": "application/json", "User-Agent": "boj-readme-updater/1.0"}
        )
        request.add_unredirected_header("x-client-id", self.credentials["API_CLIENT_ID"])
        request.add_unredirected_header("x-client-secret", self.credentials["API_SECRET"])
        try:
            with urlopen(request, timeout=20) as response:
                return json.load(response)
        except HTTPError as error:
            with error:
                if error.code == 404 and allow_missing:
                    return None
                blocked = error.headers.get("cf-mitigated") == "challenge"
                if error.code == 403 and error.headers.get_content_type() == "application/json":
                    try:
                        payload = json.load(error)
                    except ValueError:
                        payload = None
                    blocked = blocked or (isinstance(payload, dict) and "cloudflare_error" in payload)
                if blocked:
                    raise RuntimeError("solved.ac API 요청이 Cloudflare에 차단되었습니다 (HTTP 403).") from None
                raise RuntimeError(f"solved.ac API {path} 요청 실패 (HTTP {error.code}).") from None
        except (URLError, TimeoutError):
            raise RuntimeError(f"solved.ac API {path}에 연결하지 못했습니다.") from None
        except (ValueError, UnicodeError):
            raise RuntimeError(f"solved.ac API {path}가 유효한 JSON을 반환하지 않았습니다.") from None

    def boj_judge(self):
        for judge in self.get("/judges")["judges"]:
            if judge["id"] == "boj" or urlsplit(judge["homepageUrl"]).hostname in (
                "acmicpc.net", "www.acmicpc.net"
            ):
                return judge
        raise RuntimeError("solved.ac API에서 BOJ 채점 사이트 정보를 찾지 못했습니다.")

    def problem(self, number, judge):
        def matches(problem):
            return any(
                entry["ojId"] == judge["id"] and entry["problemId"].lstrip("0") == str(number)
                for entry in problem["judgeIds"]
            )

        problem = self.get(f"/problems/{number}", allow_missing=True)
        if problem is not None and matches(problem):
            return problem

        # A merged problem can have a solved.ac number different from its BOJ number.
        results = self.get("/problems", {"q": boj_problem_query(number, judge)})
        return next((problem for problem in results["problems"] if matches(problem)), None)


def boj_problem_query(number, judge):
    return f"id:{judge['prefix']}{number:0{judge['idDigits']}d}"


def solution_files(root):
    folder = root / "problems"
    if not folder.is_dir():
        raise ValueError("problems/ 폴더를 찾지 못했습니다.")

    files = {}
    for path in sorted(folder.rglob("*")):
        if re.fullmatch(r"[0-9]+", path.stem) and path.is_file() and not path.is_symlink():
            files.setdefault(int(path.stem), []).append(path.relative_to(root))
    return files


def difficulty_name(level):
    if not 1 <= level <= 30:
        return "레벨 없음" if level == 0 else str(level)
    tier, division = divmod(int(level) - 1, 5)
    return f"{TIERS[tier]} {DIVISIONS[division]}"


def markdown_text(value):
    value = escape(" ".join(value.split()), quote=False).replace("|", "&#124;")
    return re.sub(r"([\\\x60*_\[\]~$])", r"\\\1", value)


def code_link(path):
    label = markdown_text(path.name)
    language = LANGUAGE_ICONS.get(path.suffix.lower())
    if language is not None:
        name, icon = language
        source = f"{LANGUAGE_ICON_DIR}/{icon}-original.svg"
        description = escape(f"{name} ({path.name})")
        label = (
            f'<img src="{source}" alt="{description}" title="{description}" '
            'width="20" height="20">'
        )
    return f"[{label}]({quote(path.as_posix())})"


def problem_row(number, files, problem, judge):
    title, level = "조회 결과 없음", "—"
    if problem is None:
        query = urlencode({"q": boj_problem_query(number, judge)})
        problem_url = f"{SOLVED_URL}/problems?{query}"
    else:
        problem_id = quote(f"{problem['problemId']}{problem['subId']}", safe="")
        problem_url = f"{SOLVED_URL}/p/{problem_id}"
        titles = problem["titles"]
        first_title = titles[0]["title"] if titles else str(number)
        default_title = next((item["title"] for item in titles if item["isOriginal"]), first_title)
        title = next((item["title"] for item in titles if item["language"] == "ko"), default_title)
        value = problem["level"]
        level = difficulty_name(value)
        if value in range(31):
            source = f"{TIER_ICON_DIR}/p{int(value):02d}.svg"
            level = f'<img src="{source}" alt="{level}" title="{level}" height="20">'

    links = " ".join(code_link(path) for path in files)
    return f"| [{number}]({problem_url}) | {markdown_text(title)} | {level} | {links} |"


def replace_section(readme, section, content):
    start = f"<!-- solvedac:{section}:start -->"
    end = f"<!-- solvedac:{section}:end -->"
    before, _, rest = readme.partition(start)
    _, _, after = rest.partition(end)
    if readme.count(start) != 1 or readme.count(end) != 1 or end not in rest:
        raise ValueError(f"README.md에서 {section} 갱신 영역을 찾지 못했습니다.")
    return f"{before}{start}\n\n{content}\n\n{end}{after}"


def write_readme(path, content):
    mode = stat.S_IMODE(path.stat().st_mode)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as output:
        temporary = Path(output.name)
        try:
            output.write(content)
            output.close()
            temporary.chmod(mode)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def main():
    readme_path = ROOT / "README.md"
    try:
        readme = readme_path.read_text(encoding="utf-8")
        profile_link = re.search(
            r'\[(?:solved\.ac|<img\b[^>]*\salt="solved\.ac"[^>]*>)\]'
            r"\(https://solved\.ac/(?:profile/)?([a-zA-Z0-9_.-]+)/?\)",
            readme,
        )
        if profile_link is None:
            raise ValueError("README.md에서 solved.ac 프로필 링크를 찾지 못했습니다.")
        files = solution_files(ROOT)
        api = SolvedAc(load_credentials(ROOT / ".env"))
        profile = api.get(f"/users/{quote(profile_link[1], safe='')}")
        rows = ["| 번호 | 제목 | 레벨 | 코드 |", "|:---:|:---:|:---:|:---:|"]
        if files:
            judge = api.boj_judge()
            for number, paths in sorted(files.items()):
                problem = api.problem(number, judge)
                if problem is None:
                    print(f"BOJ {number}: solved.ac에서 문제 정보를 찾지 못했습니다.", file=sys.stderr)
                rows.append(problem_row(number, paths, problem, judge))

        updated_at = datetime.now(KST).strftime("%y.%m.%d. %H:%M:%S")
        stats = (
            f"rate: **{profile['rating']}** | solved: **{profile['solvedCount']}**"
            f" | class: **{profile['class']}**\n\n"
            f"저장된 문제 수: **{len(files)}**\n\n"
            f"업데이트: {updated_at} (KST)"
        )
        readme = replace_section(readme, "stats", stats)
        readme = replace_section(readme, "problems", "\n".join(rows))
        write_readme(readme_path, readme)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"README 갱신 실패: {error}", file=sys.stderr)
        return 1
    except (KeyError, TypeError):
        print("README 갱신 실패: solved.ac API 응답 형식이 예상과 다릅니다.", file=sys.stderr)
        return 1

    print(f"README.md를 갱신했습니다. 저장된 문제 {len(files)}개.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
