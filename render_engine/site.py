from copy import copy
from progress.bar import Bar
import hashlib
import itertools
import inspect
import more_itertools
import os
import shutil
import typing
import pendulum
from pathlib import Path
from slugify import slugify

from .collection import Collection
from .engine import Engine
from .feeds import RSSFeedEngine
from .links import Link
from .page import Page


def hash_content(route: Page):
    m = hashlib.sha1()
    m.update(getattr(route, 'base_content', '').encode('utf-8'))
    return m.hexdigest()+'\n'

class Site:
    """The site stores your pages and collections to be rendered.

    Pages are stored in `routes` and created with `site.render()`.
    Collections and subcollections are stored to be used for future use.

    Sites also contain global variables that can be applied in templates.

    Attributes:
        routes (list):
            storage of registered_routes
        collections (dict):
            storage of registered collections
        output_path (str or pathlib.Path):
            the path to directory which all rendered html pages will be stored.
            default `./output`
        static_path (str or pathlib.Path):
            the path to directory for static content. This will be copied over
            into the `output_path`
        SITE_TITLE (str):
            configuration variable title of the site. This is only used in your
            environment template variables. While Optional you will be warned
            if you do not supply a new variable. default: 'Untitled Site'
        SITE_URL (str):
            configuration variable url of the of the site. While Optional you will be
            warned if you do not supply a new variable. default: 'Untitled Site'
            default 'https://example.com'

    Todo:
        - remove SITE_LINK
        - make SITE_URL accesible as a Page variable and allow for switch for
            Relative and Absolute URLS
    """

    routes: typing.List[Page] = []
    output_path: Path = Path("output")
    static_path: Path = Path("static")
    SITE_TITLE: str = "Untitled Site"
    SITE_URL: str = "https://example.com"
    strict: bool = False
    default_engine: typing.Type[Engine] = Engine()
    rss_engine: typing.Type[Engine] = RSSFeedEngine()
    timezone: str = ""
    cache_file: Path = Path(".routes_cache")

    def __init__(self):
        """Clean Directory and Prepare Output Directory"""

        self.collections = {}
        self.subcollections = {}
        self.output_path = Path(self.output_path)

        if self.cache_file.exists():
            self.hashes = set(self.cache_file.read_text().splitlines(True))
        else:
            self.hashes = set()

        # sets the timezone environment variable to the local timezone if not present
        os.environ["render_engine_timezone"] = (
            self.timezone or pendulum.local_timezone().name
        )

    def register_collection(self, collection_cls: typing.Type[Collection]) -> None:
        """
        Add a class to your ``self.collections``
        iterate through a classes ``content_path`` and create a classes
        ``Page``-like objects, adding each one to ``routes``.

        Use a decorator for your defined classes.

        Examples::
            @register_collection
            class Foo(Collection):
                pass
        """

        collection = collection_cls()
        self.collections.update({collection.title: collection})

        for page in collection.pages:
            self.routes.append(page)

        if collection.has_archive:

            for archive in collection.archive:
                self.routes.append(archive)

        if collection.feeds:

            for feed in collection.feeds:
                self.register_feed(feed=feed, collection=collection)

    def _is_unique(self, filepath: Path, page: Page) -> bool:
        """returns if the content matches the existing path"""
        if page.always_refresh:
            return True

        if not filepath.exists():
            return True

        return hash_content(page) not in self.hashes

    def register_feed(self, feed: RSSFeedEngine, collection: Collection) -> None:
        """Create a Page object that is an RSS feed and add it to self.routes"""

        extension = self.rss_engine.extension
        _feed = feed
        _feed.slug = collection.slug
        _feed.title = f"{self.SITE_TITLE} - {_feed.title}"
        _feed.link = f"{self.SITE_URL}/{_feed.slug}{extension}"
        self.routes.append(_feed)

    def register_route(self, cls: Page) -> None:
        """Create a Page object and add it to self.routes"""
        route = cls()
        self.routes.append(route)

    def _render_output(self, page: Page) -> None:
        """Writes page markup to file"""
        engine = page.engine if getattr(page, 'engine', None) else self.default_engine
        route = self.output_path.joinpath(page.routes[0].strip("/"))
        route.mkdir(exist_ok=True)
        filename = Path(page.slug).with_suffix(engine.extension)
        filepath = route.joinpath(filename)
        unique_file = self._is_unique(filepath, page)

        if unique_file:
            template_attrs = self.get_public_attributes(page)
            content = engine.render(page, **template_attrs)

            if not page.always_refresh:
                self.hashes.add(hash_content(page))
            filepath.write_text(content)

            if len(page.routes) > 1:
                for new_route in page.routes[1:]:
                    new_route = self.output_path.joinpath(new_route.strip("/"))
                    new_route.mkdir(exist_ok=True)
                    new_filepath = new_route.joinpath(filename)
                    shutil.copy(filepath, new_filepath)
            return f"{filename} written"

        else:
            return f"{filename} skipped"

    def _render_subcollections(self):
        """Generate subcollection pages to be added to routes"""
        for _, collection in self.collections.items():

            if collection.subcollections:

                for subcollection_group in collection.get_subcollections():
                    _subcollection_group = collection.get_subcollections()[
                        subcollection_group
                    ]
                    sorted_group = sorted(
                        _subcollection_group,
                        key=lambda x: (len(x.pages), x.title),
                        reverse=True,
                    )

                    for subcollection in sorted_group:

                        self.subcollections[subcollection_group] = sorted_group

                        for archive in subcollection.archive:
                            self.routes.append(archive)

    def render(self, verbose: bool = False, dry_run: bool = False, strict: bool = False) -> None:
        if dry_run:
            strict = False
            verbose = True

        # removes the output path is strict is set
        if self.strict or strict:

            if self.output_path.exists():
                shutil.rmtree(self.output_path)
            self.hashes = set()

        # create an output_path if it doesn't exist
        self.output_path.mkdir(exist_ok=True)

        # copy a defined static path into output path
        if Path(self.static_path).is_dir():
            shutil.copytree(
                self.static_path,
                self.output_path.joinpath(self.static_path),
                dirs_exist_ok=True,
            )

        # render registered subcollections
        self._render_subcollections()

        if verbose:
            page_count = len(self.routes)
            with Bar(
                f"Rendering {page_count} Pages",
                max=page_count,
                suffix="%(percent).1f%% - %(elapsed_td)s",
            ) as bar:

                for page in self.routes:
                    suffix = "%(percent).1f%% - %(elapsed_td)s "
                    msg = self._render_output(page)
                    bar.suffix = suffix + msg
                    bar.next()
        else:
            for page in self.routes:
                self._render_output(page)

        with open(self.cache_file, 'w') as f:
            f.write(''.join([x for x in self.hashes]))

    def get_public_attributes(self, cls):
        site_filtered_attrs = itertools.filterfalse(
            lambda x: x[0].startswith("__"), inspect.getmembers(self)
        )
        site_dict = {x: y for x, y in site_filtered_attrs}

        cls_filtered_attrs = itertools.filterfalse(
            lambda x: x[0].startswith("__"), inspect.getmembers(cls)
        )

        cls_dict = {x: y for x, y in cls_filtered_attrs}

        return {**site_dict, **cls_dict}
