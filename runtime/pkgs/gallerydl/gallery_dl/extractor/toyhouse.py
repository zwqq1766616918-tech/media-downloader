# -*- coding: utf-8 -*-

# Copyright 2022-2026 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

"""Extractors for https://toyhou.se/"""

from .common import Extractor, Message
from .. import text, util

BASE_PATTERN = r"(?:https?://)?(?:www\.)?toyhou\.se"


class ToyhouseExtractor(Extractor):
    """Base class for toyhouse extractors"""
    category = "toyhouse"
    root = "https://toyhou.se"
    directory_fmt = ("{category}", "{user|artists!S}")
    archive_fmt = "{id}"

    def __init__(self, match):
        Extractor.__init__(self, match)
        self.user = match[1]
        self.offset = 0

    def items(self):
        metadata = self.metadata()

        for post in util.advance(self.posts(), self.offset):
            if metadata:
                post.update(metadata)
            text.nameext_from_url(post["url"], post)
            post["id"], _, post["hash"] = post["filename"].partition("_")
            yield Message.Directory, "", post
            yield Message.Url, post["url"], post

    def posts(self):
        return ()

    def metadata(self):
        return None

    def skip_files(self, num):
        self.offset += num
        return num

    def _parse_post(self, post, needle='<a href="'):
        extr = text.extract_from(post)
        data = {
            "url": extr(needle, '"'),
            "detail": "\n".join(text.split_html(extr(
                'class="image-detail', 'class="image-credit'))[2:-2]),
            "date": (v := extr('', "</div")) and
            self.parse_datetime(
                v[v.find('mb-1">')+6:], "%d %b %Y, %I:%M:%S %p"),
            "artists": text.split_html(extr(
                '<div class="artist-credit',
                '<div class="image-character'))[1:],
            "characters": text.split_html(
                extr('', 'class="image-') or
                extr('', 'id="footer"'))[2:-1],
        }

        url = data["url"]
        if "/watermarks/" in url:
            data["status"] = "watermark"
        elif "/thumbnails/" in url:
            data["status"] = "thumbnail"
        else:
            data["status"] = "original"

        return data

    def _pagination(self, path):
        url = self.root + path
        params = {"page": 1}

        while True:
            page = self.request(url, params=params).text

            cnt = 0
            for post in text.extract_iter(
                    page, '<li class="gallery-item">', '</li>'):
                cnt += 1
                yield self._parse_post(post)

            if not cnt and params["page"] == 1:
                if self._accept_content_warning(page):
                    continue
                return

            if cnt < 18:
                return
            params["page"] += 1

    def _accept_content_warning(self, page):
        pos = page.find(' name="_token"') + 1
        token, pos = text.extract(page, ' value="', '"', pos)
        user , pos = text.extract(page, ' value="', '"', pos)
        if not token or not user:
            return False

        data = {"_token": token, "user": user}
        self.request(self.root + "/~account/warnings/accept",
                     method="POST", data=data, allow_redirects=False)
        return True


class ToyhouseArtExtractor(ToyhouseExtractor):
    """Extractor for artworks of a toyhouse user"""
    subcategory = "art"
    pattern = BASE_PATTERN + r"/([^/?#]+)/art"
    example = "https://www.toyhou.se/USER/art"

    def posts(self):
        return self._pagination(f"/{self.user}/art")

    def metadata(self):
        return {"user": self.user}


class ToyhouseImageExtractor(ToyhouseExtractor):
    """Extractor for individual toyhouse images"""
    subcategory = "image"
    pattern = (r"(?:https?://)?(?:"
               r"(?:www\.)?toyhou\.se/~images|"
               r"f\d+\.toyhou\.se/file/[^/?#]+/(?:image|watermark|thumbnail)s"
               r")/(\d+)")
    example = "https://toyhou.se/~images/12345"

    def posts(self):
        url = f"{self.root}/~images/{self.user}"
        return (self._parse_post(
            self.request(url).text, '<img class="mw-100" src="'),)
