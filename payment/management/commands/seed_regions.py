"""Load or refresh the region / district reference tables from a CSV.

These two small tables replace the Uzpost branch table (§17 #84). They are the
half of the address we *can* own: the administrative divisions are published,
while no branch list is. The customer supplies the rest — their own postal
index — and the region's ``postal_prefix`` is what makes that typed index safe.

The command keeps ``seed_pickup_points``' discipline, which was the good part of
the thing it replaces:

* the whole file is validated before anything is written, so a typo in row 200
  cannot leave the tables half-updated;
* rows are upserted on the SOATO ``code``, so a re-run never duplicates;
* a row that has disappeared from the CSV is **deactivated, not deleted** — an
  order points at a district through a PROTECT foreign key, and its
  ``location_snapshot`` should stay explainable.

Usage::

    python manage.py seed_regions                  # data/regions.csv
    python manage.py seed_regions --file other.csv
    python manage.py seed_regions --dry-run
"""
import csv
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from payment.models import District, Region


COLUMNS = ('level', 'code', 'region_code', 'name', 'name_ru', 'name_en',
           'kind', 'postal_prefix', 'sort_order')

DEFAULT_PATH = Path(settings.BASE_DIR) / 'data' / 'regions.csv'


class Command(BaseCommand):
    help = 'Load or refresh Region and District rows from a CSV (idempotent).'

    def add_arguments(self, parser):
        parser.add_argument('--file', default=str(DEFAULT_PATH),
                            help='CSV to read. Defaults to data/regions.csv.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Validate and report, but write nothing.')

    def handle(self, *args, **options):
        path = Path(options['file'])
        if not path.exists():
            raise CommandError(f"No such file: {path}")

        regions, districts, errors = self._parse(path)
        if errors:
            for line_no, problem in errors:
                self.stderr.write(f"  line {line_no}: {problem}")
            raise CommandError(f"{len(errors)} invalid row(s); nothing was written.")

        if not regions:
            raise CommandError(f"{path} has no region rows.")

        if options['dry_run']:
            self.stdout.write(f"{len(regions)} region(s), {len(districts)} "
                              f"district(s)/city(ies). Dry run: nothing written.")
            return

        counts = self._write(regions, districts)
        self.stdout.write(self.style.SUCCESS(
            "Regions: {r_created} created, {r_updated} updated, {r_off} deactivated. "
            "Districts: {d_created} created, {d_updated} updated, {d_off} deactivated."
            .format(**counts)
        ))

    # ------------------------------------------------------------ parsing

    def _parse(self, path):
        """Read and validate the whole file. Returns (regions, districts, errors)."""
        regions, districts, errors = [], [], []
        seen_codes, prefixes = set(), {}

        # utf-8-sig: a CSV exported from Excel starts with a BOM.
        with path.open(newline='', encoding='utf-8-sig') as fh:
            reader = csv.DictReader(fh)
            missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
            if missing:
                return [], [], [(1, f"missing column(s): {', '.join(missing)}")]

            for raw in reader:
                line_no = reader.line_num
                row = {k: (raw.get(k) or '').strip() for k in COLUMNS}

                if not row['code'] or not row['name']:
                    errors.append((line_no, 'code and name are required'))
                    continue
                if row['code'] in seen_codes:
                    errors.append((line_no, f"duplicate code {row['code']}"))
                    continue
                seen_codes.add(row['code'])
                row['sort_order'] = int(row['sort_order']) if row['sort_order'].isdigit() else 0

                if row['level'] == 'region':
                    prefix = row['postal_prefix']
                    # An empty prefix is the escape and is allowed. A prefix that
                    # is not 2-3 digits is a typo, and a typo here silently
                    # rejects every valid index for that region — a lost sale
                    # nobody hears about.
                    if prefix and not re.fullmatch(r'\d{2,3}', prefix):
                        errors.append((line_no, f"postal_prefix {prefix!r} is not 2-3 digits"))
                        continue
                    if prefix and prefix in prefixes:
                        errors.append((line_no, f"postal_prefix {prefix} already used by "
                                                f"{prefixes[prefix]}"))
                        continue
                    if prefix:
                        prefixes[prefix] = row['code']
                    regions.append(row)
                elif row['level'] == 'district':
                    if not row['region_code']:
                        errors.append((line_no, 'a district needs a region_code'))
                        continue
                    if row['kind'] not in District.Kind.values:
                        errors.append((line_no, f"kind {row['kind']!r} is not one of "
                                                f"{', '.join(District.Kind.values)}"))
                        continue
                    districts.append(row)
                else:
                    errors.append((line_no, f"level {row['level']!r} is not "
                                            "'region' or 'district'"))

        # One prefix being the start of another would make the startswith check
        # ambiguous, and the wrong region would accept an index.
        for a in prefixes:
            for b in prefixes:
                if a != b and b.startswith(a):
                    errors.append((0, f"postal prefix {a} is a prefix of {b} — "
                                      "the region check would be ambiguous"))

        known = {r['code'] for r in regions}
        for row in districts:
            if row['region_code'] not in known:
                errors.append((0, f"{row['code']}: unknown region_code {row['region_code']}"))

        return regions, districts, errors

    # ------------------------------------------------------------ writing

    @transaction.atomic
    def _write(self, regions, districts):
        """Upsert everything, then deactivate whatever the CSV no longer lists."""
        counts = dict(r_created=0, r_updated=0, r_off=0,
                      d_created=0, d_updated=0, d_off=0)

        by_code = {}
        for row in regions:
            obj, created = Region.objects.update_or_create(
                code=row['code'],
                defaults={
                    'name': row['name'], 'name_ru': row['name_ru'],
                    'name_en': row['name_en'], 'postal_prefix': row['postal_prefix'],
                    'sort_order': row['sort_order'], 'is_active': True,
                },
            )
            by_code[row['code']] = obj
            counts['r_created' if created else 'r_updated'] += 1

        for row in districts:
            _obj, created = District.objects.update_or_create(
                code=row['code'],
                defaults={
                    'region': by_code[row['region_code']],
                    'name': row['name'], 'name_ru': row['name_ru'],
                    'name_en': row['name_en'], 'kind': row['kind'],
                    'sort_order': row['sort_order'], 'is_active': True,
                },
            )
            counts['d_created' if created else 'd_updated'] += 1

        counts['d_off'] = (District.objects
                           .exclude(code__in=[r['code'] for r in districts])
                           .filter(is_active=True).update(is_active=False))
        counts['r_off'] = (Region.objects
                           .exclude(code__in=[r['code'] for r in regions])
                           .filter(is_active=True).update(is_active=False))
        return counts
