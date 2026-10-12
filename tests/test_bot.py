import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bot  # noqa: E402


def test_redact_hides_token(monkeypatch):
    monkeypatch.setattr(bot, "BOT_TOKEN", "123:SECRET")
    err = "HTTPSConnectionPool: url: /bot123:SECRET/getUpdates"
    assert "SECRET" not in bot.redact(err)
    assert "<token>" in bot.redact(err)


def test_redact_without_token(monkeypatch):
    monkeypatch.setattr(bot, "BOT_TOKEN", "")
    assert bot.redact("abc") == "abc"


def test_esc_escapes_html():
    assert bot.esc("<b>&</b>") == "&lt;b&gt;&amp;&lt;/b&gt;"


def test_norm():
    assert bot.norm("  📊 Дайджест!! ") == "дайджест"


def test_wind_dir_name():
    assert bot.wind_dir_name(0) == "С"
    assert bot.wind_dir_name(90) == "В"
    assert bot.wind_dir_name(180) == "Ю"
    assert bot.wind_dir_name(270) == "З"
    assert bot.wind_dir_name(None) == "—"


RSS = """<rss><channel>
<item><title><![CDATA[Курс доллара вырос]]></title>
<link>https://example.com/a?x=1&amp;y=2</link>
<description>Подробности про курс доллара и рубль</description></item>
<item><title>Новости</title><link>https://example.com/b</link></item>
<item><title>Запуск нового смартфона</title><link>https://example.com/c</link>
<description>Запуск нового смартфона</description></item>
</channel></rss>"""


def test_parse_rss_items_skips_generic_titles_and_dedups_description():
    items = bot._parse_rss_items(RSS, "TEST")
    titles = [t for _, t, _, _ in items]
    assert "Новости" not in titles
    assert "Курс доллара вырос" in titles
    phone = next(i for i in items if i[1] == "Запуск нового смартфона")
    assert phone[2] == ""  # описание совпадает с заголовком — убрано


def test_parse_rss_items_category_filter():
    items = bot._parse_rss_items(RSS, "TEST", category="econ")
    assert [t for _, t, _, _ in items] == ["Курс доллара вырос"]


def test_block_news_escapes_ampersand_in_links(monkeypatch):
    monkeypatch.setattr(bot, "fetch_news", lambda limit, cat: [("TEST", "Заголовок", "", "https://e.com/?a=1&b=2")])
    monkeypatch.setattr(bot, "load_prefs", lambda: {"news_cat": "all"})
    text = bot.block_news(5)
    assert 'href="https://e.com/?a=1&amp;b=2"' in text


def test_load_events_from_file(tmp_path, monkeypatch):
    f = tmp_path / "events.json"
    f.write_text(json.dumps([["2030-01-01", "Тест"]]), encoding="utf-8")
    monkeypatch.setattr(bot, "EVENTS_FILE", f)
    assert bot.load_events() == [("2030-01-01", "Тест")]


def test_load_events_falls_back_to_builtin(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "EVENTS_FILE", tmp_path / "missing.json")
    assert bot.load_events() == bot.EVENTS_2026


def test_load_events_ignores_broken_file(tmp_path, monkeypatch):
    f = tmp_path / "events.json"
    f.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(bot, "EVENTS_FILE", f)
    assert bot.load_events() == bot.EVENTS_2026


class _Resp:
    def json(self):
        return {"ok": True}


def test_send_splits_long_text_and_keyboard_only_on_last(monkeypatch):
    sent = []

    def fake_post(url, payload):
        sent.append(payload)
        return _Resp()

    monkeypatch.setattr(bot, "post_json", fake_post)
    text = "\n".join(["строка " * 10] * 200)  # заметно длиннее 3900
    assert bot.send(1, text) is True
    assert len(sent) > 1
    assert all(len(p["text"]) <= 3900 for p in sent)
    assert "reply_markup" not in sent[0]
    assert sent[-1]["reply_markup"] == bot.KEYBOARD


def test_prefs_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "PREFS_FILE", tmp_path / "prefs.json")
    p = bot.load_prefs()
    assert p["tickers"][0] == "SBER"
    p["prefer_short"] = True
    bot.save_prefs(p)
    assert bot.load_prefs()["prefer_short"] is True


def test_geo_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "GEO_FILE", tmp_path / "geo.json")
    bot.save_geo(55.0, 37.0, "Тест")
    assert bot.load_geo() == (55.0, 37.0, "Тест")
