import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from changelogcat.postprocess import strip_foreign_links  # noqa: E402
from changelogcat.tags import fetch_tags, previous_tag, version_key  # noqa: E402
from changelogcat.tags import main as tags_main

REPO = "acme/widgets"


def test_links_into_the_repo_survive():
    text = "Fixed [the crash](https://github.com/acme/widgets/pull/5) and see https://github.com/Acme/Widgets/issues/9."
    assert strip_foreign_links(text, REPO) == text


def test_foreign_markdown_links_keep_their_text_only():
    out = strip_foreign_links("Download [the fix](https://evil.example/pwn.exe) now", REPO)
    assert out == "Download the fix now"


def test_foreign_images_autolinks_and_bare_urls_are_removed():
    out = strip_foreign_links(
        "![x](https://evil.example/a.png)\n<https://evil.example/b>\nvisit https://evil.example/c today", REPO
    )
    assert "evil.example" not in out and "visit" in out and "today" in out


def test_lookalike_hosts_and_repos_are_not_the_repo():
    for bad in (
        "https://github.com.evil.example/acme/widgets",
        "https://github.com/acme/widgets-evil/pull/1",
        "https://github.com/other/widgets",
    ):
        assert strip_foreign_links(f"see {bad}", REPO).strip() == "see"
        assert strip_foreign_links(f"[x]({bad})", REPO) == "x"


def test_relative_links_and_plain_text_are_untouched():
    text = "## Fixed\n- See [docs](docs/usage.md) for details.\n"
    assert strip_foreign_links(text, REPO) == text


def test_version_ordering_is_numeric_and_prereleases_sort_first():
    assert version_key("v1.10.0") > version_key("v1.9.0")
    assert version_key("1.0.0-rc1") < version_key("1.0.0")
    assert version_key("v2") > version_key("v1.9.9")


def test_previous_tag_picks_the_highest_lower_version():
    tags = ["v1.2.0", "v1.10.0", "v1.9.0", "nightly", "v1.10.1", "v2.0.0"]
    assert previous_tag(tags, "v1.10.1") == "v1.10.0"
    assert previous_tag(tags, "v1.9.0") == "v1.2.0"
    assert previous_tag(tags, "v1.2.0") is None
    assert previous_tag(["v1.0.0-rc1", "v0.9.0"], "v1.0.0") == "v1.0.0-rc1"


def test_fetch_tags_pages_until_a_short_page():
    def handler(req: httpx.Request) -> httpx.Response:
        page = int(req.url.params["page"])
        n = 100 if page == 1 else 3
        return httpx.Response(200, json=[{"name": f"v{page}.{i}"} for i in range(n)])

    client = httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler))
    assert len(fetch_tags("a/b", client=client)) == 103


def test_cli_reports_a_missing_previous_tag(monkeypatch, capsys):
    monkeypatch.setattr("changelogcat.tags.fetch_tags", lambda repo, token="": ["v1.0.0"])
    assert tags_main(["previous", "--repo", "a/b", "--tag", "v1.0.0"]) == 1
    monkeypatch.setattr("changelogcat.tags.fetch_tags", lambda repo, token="": ["v1.0.0", "v1.1.0"])
    assert tags_main(["previous", "--repo", "a/b", "--tag", "v1.1.0"]) == 0
    assert capsys.readouterr().out.strip() == "v1.0.0"
