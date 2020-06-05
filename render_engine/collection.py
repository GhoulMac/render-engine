import more_itertools
import itertools
import operator
import logging
import typing
from pathlib import Path

from .page import Page
from .feeds import RSSFeed


class Collection:
    """Collection objects serve as a way to quickly process pages that have a
    LARGE portion of content that is similar or file driven.

    The most common form of collection would be a Blog, but can also be
    static pages that have their content stored in a dedicated file.

    Currently, collections must come from a content_path and all be the same
    content type.


    Example
    -------
    from render_engine import Collection

    @site.register_collection()
    class BasicCollection(Collection):
        pass


    Attributes
    ----------
    engine: str, optional
        The engine that the collection will pass to each page. Site's default
        engine
    template: str
        The template that each page will use to render
    routes: List[str]
        all routes that the file should be created at. default []
    content_path: List[PathString], optional
        the filepath to load content from.
    includes: List[str], optional
        the types of files in the content path that will be processed
        default ["*.md", "*.html"]
    has_archive: Bool
        if `True`, create an archive page with all of the processed pages saved
        as `pages`. default `False`
    _archive_template: str, optional
        template filename that will be used if `has_archive==True` default: archive.html"
    _archive_slug: str, optional
        slug for rendered page if `has_archive == True` default: all_posts
    _archive_content_type: Type[Page], optional
        content_type for the rendered archive page
    _archive_reverse: Bool, optional
        should the sorted `pages` be listed in reverse order. default: False

    """
    engine = ''
    page_content_type: Page = Page
    content_path: str = "content"
    content_items: typing.List = []
    template: str = "page.html"
    includes: typing.List[str] = ["*.md", "*.html"]
    routes: typing.List[str] = [""]
    subcollections: typing.List[str] = []
    has_archive: bool = False
    archive_template: str = "archive.html"
    archive_slug: str = "all_posts"
    archive_content_type: Page = Page
    archive_reverse: bool = False


    @staticmethod
    def archive_default_sort(cls):
        """attribute pulled from a rendered Page to sort `pages`"""
        return cls.slug

    @property
    def pages(self) -> typing.List[typing.Type[Page]]:
        """Iterate through set of pages and generate a `Page`-like object for each."""
        _pages = self.content_items

        if not Path(self.content_path).exists():
            return _pages # Do nothing if the path does not exist

        if Path(self.content_path).samefile('/'):
            logging.warning(f'{self.content_path=}! Accessing Root Directory is Dangerous...')

        for pattern in self.includes:

            for filepath in Path(self.content_path).glob(pattern):
                page = self.page_content_type(content_path=filepath)
                page.routes = self.routes
                page.template = self.template

                _pages.append(page)

        return _pages

    @property
    def archive(self):
        """Create a `Page` object for those items"""
        archive_page = self.archive_content_type(no_index=True)
        archive_page.template = self.archive_template
        archive_page.slug = self.archive_slug
        archive_page.engine = ""
        archive_page.title = self.__class__.__name__
        archive_page.pages = sorted(
            self.pages,
            key=lambda p: self.archive_default_sort(p),
            reverse=self.archive_reverse,
        )
        return archive_page

    @classmethod
    def from_subcollection(cls, collection, attr, attrval):
        sub_content_items = []

        for page in collection.pages:

            if attrval in getattr(page, attr, []):
                sub_content_items.append(page)

        print(sub_content_items)


        class SubCollection(Collection):
            title=attrval
            content_items=sub_content_items
            has_archive=True

        return SubCollection()
