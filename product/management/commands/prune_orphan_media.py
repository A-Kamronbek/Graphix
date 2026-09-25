"""Delete files under ``media/`` that no database row points at.

Two things leave orphans behind. Test runs used to save through real storage
into the developer's own ``media/`` (fixed in ``core/runner.py``, but a
thousand files were already there), and replacing a picture in the Django
admin writes the new file and leaves the old one, because the delete receiver
fires on a deleted *row* and the row survives a replacement.

It refuses to guess. A file is an orphan only if no row in any model with a
file field names it, so a picture belonging to a product is safe whether or
not the storefront currently shows it.

Dry by default: nothing is deleted without ``--delete``.
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from product.signals import FILE_COLUMNS


class Command(BaseCommand):
    help = 'List (or delete) files in media/ that no row references.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--delete', action='store_true',
            help='Actually remove them. Without this the command only counts.')

    def referenced(self):
        """Every path any row currently points at, relative to MEDIA_ROOT.

        Read from ``product.signals.FILE_COLUMNS``, which is the list the
        delete receivers already use, so a model added to one is covered by
        the other without anybody remembering to update two lists.
        """
        names = set()
        for model, column in FILE_COLUMNS:
            for value in model.objects.exclude(**{column: ''}).values_list(
                    column, flat=True):
                if value:
                    names.add(str(value).replace('\\', '/'))
        return names

    def derived(self):
        """Every rendition the site can actually serve, as its row records it.

        Read from each row's ``renditions`` column, never derived from the
        original's name - because the name is not derivable. Renditions sit in
        a ``w/`` subfolder (``images.RENDITION_DIR``) and their widths come
        from the source, which is never upscaled: a 360 px picture has one
        rendition at 360, not three at 400, 800 and 1600.

        Guessing it cost every rendition on a developer's machine. The guessed
        names matched nothing, so ``--delete`` counted all 36 as orphans and
        removed them; no page broke, because the fallback script swaps in the
        placeholder when an image 404s - which is a layout shift, and is how
        the CLS measurement found this a day later (§17 #276).

        A row whose file was replaced records renditions of a file it no
        longer holds. ``sources()`` returns nothing for it, so those really
        are orphans and are meant to go.
        """
        names = set()
        for model, _column in FILE_COLUMNS:
            for row in model.objects.all():
                names.update(name for _width, name in row.sources())
        return names

    def handle(self, *args, **options):
        root = Path(settings.MEDIA_ROOT)
        if not root.is_dir():
            self.stdout.write('no media folder at %s' % root)
            return

        keep = self.referenced()
        keep |= self.derived()

        orphans, kept, freed = [], 0, 0
        for path in sorted(root.rglob('*')):
            if not path.is_file():
                continue
            name = path.relative_to(root).as_posix()
            if name in keep:
                kept += 1
            else:
                orphans.append(path)
                freed += path.stat().st_size

        self.stdout.write('%d referenced, %d orphaned (%.1f MB)'
                          % (kept, len(orphans), freed / 1024 / 1024))
        if not options['delete']:
            for path in orphans[:10]:
                self.stdout.write('  would remove %s'
                                  % path.relative_to(root).as_posix())
            if len(orphans) > 10:
                self.stdout.write('  ... and %d more' % (len(orphans) - 10))
            self.stdout.write('nothing removed; pass --delete to remove them')
            return

        for path in orphans:
            path.unlink()
        self.stdout.write(self.style.SUCCESS(
            'removed %d files, %.1f MB' % (len(orphans), freed / 1024 / 1024)))
