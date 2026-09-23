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

    def renditions_of(self, names):
        """The WebP renditions built beside each referenced picture.

        ``build_renditions`` writes ``name-400.webp`` and friends next to the
        original. They belong to a live row even though no column names them,
        so they are not orphans.
        """
        extra = set()
        for name in names:
            stem = name.rsplit('.', 1)[0]
            extra.update('%s-%d.webp' % (stem, width)
                         for width in (400, 800, 1600))
        return extra

    def handle(self, *args, **options):
        root = Path(settings.MEDIA_ROOT)
        if not root.is_dir():
            self.stdout.write('no media folder at %s' % root)
            return

        keep = self.referenced()
        keep |= self.renditions_of(keep)

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
