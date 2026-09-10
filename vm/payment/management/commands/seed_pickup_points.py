"""Load or refresh the Uzpost pickup-point dataset from a CSV.

Our own table rather than a live API: the branch list changes rarely, and a
seeded table keeps checkout working when the network doesn't.

The command is idempotent and safe to re-run. It upserts on ``code`` (the postal
index) and **deactivates** branches that have disappeared from the CSV rather
than deleting them — an order may point at one through a PROTECT foreign key,
and its ``pickup_snapshot`` should stay explainable.

The whole file is validated before anything is written, so a typo in row 400
can't leave the table half-updated.

Usage::

    python manage.py seed_pickup_points                  # data/pickup_points.csv
    python manage.py seed_pickup_points --file other.csv
    python manage.py seed_pickup_points --dry-run
"""
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from payment.models import PickupPoint


# Column order is documented in data/pickup_points.csv; only REQUIRED must be present.
REQUIRED = ('code', 'name', 'region', 'district', 'address', 'latitude', 'longitude')
OPTIONAL = ('name_ru', 'name_en', 'address_ru', 'address_en',
            'working_hours', 'phone', 'sort_order')

DEFAULT_PATH = Path(settings.BASE_DIR) / 'data' / 'pickup_points.csv'


class Command(BaseCommand):
    help = 'Load or refresh PickupPoint rows from a CSV (idempotent).'

    def add_arguments(self, parser):
        parser.add_argument('--file', default=str(DEFAULT_PATH),
                            help='CSV to read. Defaults to data/pickup_points.csv.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Validate and report, but write nothing.')

    def handle(self, *args, **options):
        path = Path(options['file'])
        if not path.exists():
            raise CommandError(f"No such file: {path}")

        rows, errors = self._parse(path)
        if errors:
            for line_no, problem in errors:
                self.stderr.write(f"  line {line_no}: {problem}")
            raise CommandError(f"{len(errors)} invalid row(s); nothing was written.")

        if not rows:
            self.stdout.write(self.style.WARNING(
                f"{path} has no data rows — nothing to do. "
                "The real branch dataset still has to be supplied."
            ))
            return

        if options['dry_run']:
            self.stdout.write(f"{len(rows)} valid row(s). Dry run: nothing written.")
            return

        created, updated, deactivated = self._write(rows)
        self.stdout.write(self.style.SUCCESS(
            f"Pickup points: {created} created, {updated} updated, {deactivated} deactivated."
        ))

    def _parse(self, path):
        """Read and validate the whole file. Returns (rows, errors)."""
        rows, errors, seen = [], [], set()
        # utf-8-sig: a CSV exported from Excel starts with a BOM.
        with path.open(newline='', encoding='utf-8-sig') as fh:
            reader = csv.DictReader(fh)
            missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
            if missing:
                return [], [(1, f"missing column(s): {', '.join(missing)}")]

            for raw in reader:
                line_no = reader.line_num
                row = {k: (raw.get(k) or '').strip() for k in REQUIRED + OPTIONAL}

                blank = [c for c in REQUIRED if not row[c]]
                if blank:
                    errors.append((line_no, f"empty required column(s): {', '.join(blank)}"))
                    continue
                if row['code'] in seen:
                    errors.append((line_no, f"duplicate code {row['code']}"))
                    continue
                seen.add(row['code'])

                try:
                    row['latitude'] = Decimal(row['latitude'])
                    row['longitude'] = Decimal(row['longitude'])
                except InvalidOperation:
                    errors.append((line_no, "latitude/longitude must be decimal numbers"))
                    continue
                # Uzbekistan's bounding box, roughly. Catches swapped lat/lng,
                # which would otherwise send parcels to the wrong place.
                if not (37 <= row['latitude'] <= 46 and 55 <= row['longitude'] <= 74):
                    errors.append((line_no,
                                   f"coordinates {row['latitude']},{row['longitude']} "
                                   "are outside Uzbekistan — are they swapped?"))
                    continue

                row['sort_order'] = int(row['sort_order']) if row['sort_order'] else 0
                rows.append(row)

        return rows, errors

    @transaction.atomic
    def _write(self, rows):
        """Upsert every row, then deactivate any branch the CSV no longer lists."""
        created = updated = 0
        for row in rows:
            code = row.pop('code')
            row['is_active'] = True
            _, was_created = PickupPoint.objects.update_or_create(code=code, defaults=row)
            created += was_created
            updated += not was_created
            row['code'] = code          # keep the dict usable for the caller

        deactivated = (PickupPoint.objects
                       .exclude(code__in=[r['code'] for r in rows])
                       .filter(is_active=True)
                       .update(is_active=False))
        return created, updated, deactivated
