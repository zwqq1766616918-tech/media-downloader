# -*- coding: utf-8 -*-

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Extractors for https://kagane.to/"""

from .common import ChapterExtractor, MangaExtractor
from .. import text

BASE_PATTERN = r"(?:https?://)?(?:www\.)?kagane\.(?:to|org)"


class KaganeBase():
    """Base class for kagane extractors"""
    category = "kagane"
    root = "https://kagane.to"
    root_api = "https://kagane.to"

    def _integrity(self):
        return self.request_json(
            f"{self.root}/api/integrity", method="POST")["token"]

    def _manga_info(self, sid):
        data = self.request_json(f"{self.root_api}/api/v2/series/{sid}")

        return {
            "manga_id": data["series_id"],
            "manga": data["title"],
            "manga_alt": [
                alt["title"]
                for alt in data["series_alternate_titles"]
            ],
            "type": data["format"],
            "content_rating": data["content_rating"],
            "status": data["publication_status"],
            "rating": data["average_rating"],
            "manga_date": self.parse_datetime_iso(data.get("created_at")),
            "genres": [g["genre_name"] for g in data.get("genres") or ()],
            "tags": [t["tag_name"] for t in data.get("tags") or ()],
            "lang": "en",
            "language": "English",
            "_chapters": data["series_books"],
        }


class KaganeChapterExtractor(KaganeBase, ChapterExtractor):
    """Extractor for kagane manga chapters"""
    pattern = BASE_PATTERN + r"(/series/([\w-]+)/reader/([\w-]+))"
    example = "https://kagane.to/series/MANGA_ID/reader/CHAPTER_ID"

    def metadata(self, page):
        chstr = text.unescape(text.extr(
            page, 'property="og:title" content="', '"'))

        match = text.re(
            r"\s+-\s+"
            r"(?:[Vv]olume\s*(\d+)\s*)?"
            r"[Cc]hapter\s*(\d+)([^\s]*)?"
            r"(?:\s+-\s+(?:[Cc]h(?:apter|\.) [^\s]+(?:\s+-)?\s*)?(.+))?$"
        ).search(chstr)
        volume, chapter, minor, title = match.groups()

        return {
            **self.cache(self._manga_info, self.groups[1]),
            "chapter_id": self.groups[2],
            "title": title or "",
            "volume": text.parse_int(volume),
            "chapter": text.parse_int(chapter),
            "chapter_minor": minor,
            "chapter_string": chstr,
        }

    def images(self, page):
        cid = self.groups[2]
        url = f"{self.root_api}/api/v2/books/{cid}"
        headers = {"x-integrity-token": self.cache(
            self._integrity, _key=None, _exp=300, _mem=False)}
        resp = self.request_json(url, method="POST", headers=headers)

        return [
            (f"{resp['cache_url']}/api/v2/books/page/{cid}/{data['page_id']}"
             f".{data['ext']}?token={resp['access_token']}", data)
            for data in resp["manifest"]["pages"]
        ]


class KaganeMangaExtractor(KaganeBase, MangaExtractor):
    """Extractor for kagane manga"""
    chapterclass = KaganeChapterExtractor
    reverse = False
    pattern = BASE_PATTERN + r"/series/([\w-]+)"
    example = "https://kagane.to/series/MANGA_ID"

    def chapters(self, page):
        mid = self.groups[0]
        manga = self.cache(self._manga_info, mid)
        base = f"{self.root}/series/{mid}/reader/"

        results = []
        for ch in manga["_chapters"]:
            chapter, sep, minor = ch["chapter_no"].partition(".")
            results.append((base + ch["book_id"], {
                **manga,
                **ch,
                "volume": text.parse_int(ch.get("volume_no")),
                "chapter": text.parse_int(chapter),
                "chapter_minor": sep + minor,
                "chapter_id": ch["book_id"],
                "views": text.parse_int(ch["views"]),
                "date": self.parse_datetime_iso(ch["created_at"]),
            }))
        return results
