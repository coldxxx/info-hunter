"""Small dependency contracts shared by HTTP route modules."""
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class RouteResult:
    body: Any
    code: int = 200


@dataclass(frozen=True)
class SourceServices:
    fetch: Callable
    parse_feed: Callable
    canonical: Callable


@dataclass(frozen=True)
class ArticleServices:
    put: Callable
    date: Callable
    canonical: Callable


@dataclass(frozen=True)
class CollectionServices:
    fetch: Callable
    parse_feed: Callable
    canonical: Callable
    put: Callable
