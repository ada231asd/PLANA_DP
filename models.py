from dataclasses import dataclass, field
from typing import List


@dataclass
class Chapter:
    number: str
    url: str
    label: str = ""
    updated: str = ""
    order: int = 0


@dataclass
class Manga:
    title: str
    url: str

    alternative_title: str = ""
    author: str = ""
    status: str = ""
    description: str = ""
    cover_url: str = ""

    views: str = ""
    bookmarks: str = ""

    genres: List[str] = field(default_factory=list)
    chapters: List[Chapter] = field(default_factory=list)
