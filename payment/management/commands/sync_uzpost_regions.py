"""Load Uzpost's regions and districts into the checkout's lists.

From Phase 22 a customer chooses from Uzpost's fourteen regions and its
districts, because a shipment is addressed by Uzpost's id for the district and
a district Uzpost does not know cannot be sent to (§17 #377, #378). The lists
are kept in ``data/uzpost-regions.csv`` and never read from Uzpost while a
customer waits.

Two jobs, one command::

    python manage.py sync_uzpost_regions              # load the file
    python manage.py sync_uzpost_regions --dry-run    # check it, write nothing
    python manage.py sync_uzpost_regions --fetch --file /tmp/uzpost-regions.csv

**Loading** keeps ``seed_regions``' discipline: the whole file is checked
before anything is written, and a row the file no longer lists is switched
off, never deleted, because an order points at its district through a PROTECT
key and its ``location_snapshot`` keeps what it said (§17 #14, #165).

* A region row names the official region it is (``soato``). That region takes
  Uzpost's id and keeps its own name and translations.
* A district row with a ``soato`` takes over that official district: it gets
  Uzpost's id and the file's name, and keeps its Russian and English. One
  without is created, with the code ``U`` and Uzpost's id and the Russian and
  English blank until somebody writes them in the panel; blank falls back to
  Uzbek (§17 #8).
* The file's names are Uzbek spellings: the official name where the district
  has an official row, and Uzbek in place of Uzpost's Russian-style spelling
  (``Chilonzor tumani``, not ``Chilanzar``) where it has none (§19 Q63).
* Every other district and region, the *Boshqa* escapes among them, is
  switched off.

**Fetching** asks Uzpost for both levels and writes the file. It needs the
owner's login, which only the server's ``.env`` holds, so on the server it is
given a ``--file`` outside the checkout and the result is copied back into the
repository. What a person wrote in the file survives a fetch: the name, the
``soato`` and the ``note`` of a known district, and the centre of any row with
a note, which is how a centre is corrected by hand (§17 #381). A new district
gets a ``soato`` proposed by name within its region and, with it, the official
name; one with no official row gets Uzpost's name, cleaned. The command lists
every proposal that was not an exact match and every district with no
official row, to be read, and written in Uzbek, before the file is
committed.
"""
import collections
import csv
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core import uzpost
from payment.models import District, Region


COLUMNS = ('level', 'uzpost_id', 'parent_id', 'name', 'kind',
           'lat', 'lng', 'soato', 'note')

DEFAULT_PATH = Path(settings.BASE_DIR) / 'data' / 'uzpost-regions.csv'
OFFICIAL_PATH = Path(settings.BASE_DIR) / 'data' / 'regions.csv'

#: Uzpost's id for each region, and the official one it is. Fourteen places
#: that do not change; used only when a fetch meets a region the file does
#: not have yet.
REGION_SOATO = {
    258: '1703', 259: '1706', 260: '1730', 261: '1708', 262: '1714',
    263: '1712', 264: '1710', 265: '1735', 266: '1718', 267: '1724',
    268: '1722', 269: '1727', 270: '1726', 271: '1733',
}

#: Latin letters Uzpost's names sometimes carry in Cyrillic (``Qоrashina``).
_CYRILLIC = str.maketrans({
    'а': 'a', 'е': 'e', 'о': 'o', 'р': 'r', 'с': 's', 'х': 'x', 'у': 'y',
    'к': 'k', 'м': 'm', 'т': 't', 'н': 'n', 'в': 'v', 'А': 'A', 'Е': 'E',
    'О': 'O', 'Р': 'R', 'С': 'S', 'Х': 'X', 'К': 'K', 'М': 'M', 'Т': 'T',
    'Н': 'N', 'В': 'B',
})

#: Every way Uzpost writes an apostrophe, the backtick of ``Mug`lon`` included.
_APOSTROPHES = "'‘’`ʻʼ´"

#: Words that say what a place is, not which one.
_GENERIC = {'tumani', 'tuman', 'shahri', 'shahar'}


def clean_name(name):
    """Uzpost's name with its typography put right, and nothing else changed.

    A Cyrillic letter in a Latin word becomes the Latin one, spaces are
    trimmed and collapsed, an apostrophe after o or g is U+02BB and any other
    is the tutuq belgisi, U+02BC (§4.3), and Tumani, Shahri and Shahar are
    written in lower case, as Uzbek writes them after a name.
    """
    text = ' '.join(str(name).translate(_CYRILLIC).split())
    out = []
    for i, ch in enumerate(text):
        if ch in _APOSTROPHES:
            out.append('ʻ' if i and text[i - 1].lower() in 'og' else 'ʼ')
        else:
            out.append(ch)
    text = ''.join(out)
    return re.sub(r'\b(Tumani|Shahri|Shahar)\b', lambda m: m.group(1).lower(), text)


def name_kind(name):
    """``city`` or ``district`` as the name says it, or None when it does not."""
    words = set(clean_name(name).lower().split())
    if words & {'shahri', 'shahar'}:
        return District.Kind.CITY
    if words & {'tumani', 'tuman'}:
        return District.Kind.DISTRICT
    return None


def name_key(name, region_word=''):
    """What two spellings of one place share: letters only, no generic word.

    A name that ends with its region's own name (``Paxtaobod Andijon``) loses
    it, since an official name never carries it.
    """
    words = [w for w in clean_name(name).lower().split() if w not in _GENERIC]
    if len(words) > 1 and region_word and re.sub(r'[^a-z]', '', words[-1]) == region_word:
        words = words[:-1]
    return re.sub(r'[^a-z]', '', ' '.join(words))


def _distance(a, b):
    """How many letters apart two keys are (Levenshtein)."""
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1,
                               previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def propose_matches(districts, official, region_soato, region_words, taken=()):
    """Propose the official district each Uzpost district is, by name.

    ``districts`` are Uzpost's rows (``id``, ``parent_id``, ``name``);
    ``official`` the district rows of ``regions.csv``. A match stays inside
    the region. An exact pass comes first, then a spelling one letter apart
    (two for a name of seven letters or more) - Uzpost writes ``Chilanzar``
    and ``Yunusabad`` for Chilonzor and Yunusobod. A name that says city or
    district only matches that kind, and names that say neither are tried
    last. A tie is left unmatched unless one candidate is a district.

    Returns ``{uzpost_id: (code, exact)}``.
    """
    by_region = collections.defaultdict(list)
    for row in official:
        if row['kind'] != District.Kind.OTHER:
            by_region[row['region_code']].append(row)
    used = set(taken)
    result = {}
    ordered = sorted(districts, key=lambda d: (name_kind(d['name']) is None,
                                               d['parent_id'], d['name']))
    for exact in (True, False):
        for row in ordered:
            if row['id'] in result:
                continue
            soato = region_soato.get(row['parent_id'])
            word = region_words.get(row['parent_id'], '')
            key, kind = name_key(row['name'], word), name_kind(row['name'])
            pool = [o for o in by_region.get(soato, ())
                    if o['code'] not in used and (kind is None or o['kind'] == kind)]
            if exact:
                found = [o for o in pool if name_key(o['name']) == key]
            else:
                scored = sorted(((_distance(key, name_key(o['name'])), o) for o in pool),
                                key=lambda pair: pair[0])
                limit = 1 if len(key) < 7 else 2
                found = [o for d, o in scored if d <= limit]
                if len(found) > 1:
                    found = [o for d, o in scored if d == scored[0][0]]
            if len(found) > 1:
                districts_only = [o for o in found if o['kind'] == District.Kind.DISTRICT]
                found = districts_only if len(districts_only) == 1 else []
            if len(found) == 1:
                used.add(found[0]['code'])
                result[row['id']] = (found[0]['code'], exact)
    return result


def _point(value):
    """A coordinate from the file or from Uzpost, to six places, or None."""
    try:
        number = Decimal(str(value).strip())
        if not number.is_finite():
            return None
        return number.quantize(Decimal('0.000001'))
    except (InvalidOperation, ValueError):
        return None


class Command(BaseCommand):
    help = "Load Uzpost's regions and districts from data/uzpost-regions.csv, or fetch them."

    def add_arguments(self, parser):
        parser.add_argument('--file', default=str(DEFAULT_PATH),
                            help='The CSV to read or, with --fetch, to write.')
        parser.add_argument('--fetch', action='store_true',
                            help="Ask Uzpost for both levels and write the file.")
        parser.add_argument('--dry-run', action='store_true',
                            help='Check the file and report, but write nothing.')

    def handle(self, *args, **options):
        path = Path(options['file'])
        if options['fetch']:
            return self._fetch(path)

        if not path.exists():
            raise CommandError(f"No such file: {path}")
        regions, districts, errors = self._parse(path)
        if not errors:
            plan, errors = self._plan(regions, districts)
        if errors:
            for line_no, problem in errors:
                self.stderr.write(f"  line {line_no}: {problem}" if line_no else f"  {problem}")
            raise CommandError(f"{len(errors)} problem(s); nothing was written.")

        if options['dry_run']:
            self.stdout.write(f"{len(regions)} region(s), {len(districts)} district(s). "
                              "Dry run: nothing written.")
            return
        counts = self._write(plan)
        self.stdout.write(self.style.SUCCESS(
            "Regions: {r_linked} linked, {r_off} switched off. "
            "Districts: {d_created} created, {d_updated} updated, {d_off} switched off."
            .format(**counts)))

    # ------------------------------------------------------------ reading the file

    def _read(self, path):
        """The file's rows as dicts with their line numbers, or a missing-column error."""
        with path.open(newline='', encoding='utf-8-sig') as fh:
            reader = csv.DictReader(fh)
            missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
            if missing:
                raise CommandError(f"{path}: missing column(s): {', '.join(missing)}")
            return [(reader.line_num, {k: (raw.get(k) or '').strip() for k in COLUMNS})
                    for raw in reader]

    def _parse(self, path):
        """Check every row on its own. Returns (regions, districts, errors)."""
        regions, districts, errors = [], [], []
        seen = set()
        for line_no, row in self._read(path):
            if not row['uzpost_id'].isdigit() or int(row['uzpost_id']) == 0:
                errors.append((line_no, f"uzpost_id {row['uzpost_id']!r} is not a number"))
                continue
            row['uzpost_id'] = int(row['uzpost_id'])
            if (row['level'], row['uzpost_id']) in seen:
                errors.append((line_no, f"uzpost_id {row['uzpost_id']} is listed twice"))
                continue
            seen.add((row['level'], row['uzpost_id']))
            if not row['name'] or len(row['name']) > 80:
                errors.append((line_no, 'a name of 1 to 80 characters is required'))
                continue
            row['line'] = line_no
            if row['level'] == 'region':
                if not row['soato']:
                    errors.append((line_no, 'a region needs the soato of its official region'))
                    continue
                regions.append(row)
            elif row['level'] == 'district':
                if row['kind'] not in (District.Kind.DISTRICT, District.Kind.CITY):
                    errors.append((line_no, f"kind {row['kind']!r} is not district or city"))
                    continue
                lat, lng = _point(row['lat']), _point(row['lng'])
                if lat is None or lng is None or not (-90 <= lat <= 90 and -180 <= lng <= 180):
                    errors.append((line_no, 'lat and lng must be a point'))
                    continue
                row['lat'], row['lng'] = lat, lng
                if not row['parent_id'].isdigit():
                    errors.append((line_no, 'a district needs the parent_id of its region'))
                    continue
                row['parent_id'] = int(row['parent_id'])
                districts.append(row)
            else:
                errors.append((line_no, f"level {row['level']!r} is not region or district"))

        known = {r['uzpost_id'] for r in regions}
        for row in districts:
            if row['parent_id'] not in known:
                errors.append((row['line'], f"parent_id {row['parent_id']} is not a region "
                                            "in the file"))
        if not regions and not errors:
            errors.append((0, f"{path} has no region rows"))
        return regions, districts, errors

    def _plan(self, regions, districts):
        """Decide which row each line becomes, against the database. Returns (plan, errors).

        Everything that could stop the load is found here, before a write:
        a soato the database does not have or that sits in another region,
        two lines wanting one row, and two districts of one region ending up
        with one name.

        The file is the authority: a line's ``soato`` names the row it takes
        over, whatever row Uzpost's id was on before, so a match corrected by
        hand takes effect. A line with no ``soato`` keeps the row its id is
        on, or the ``U`` row made for it before, or gets a new one.
        """
        errors = []
        region_rows = {r.code: r for r in Region.objects.all()}
        region_by_uzpost = {r.uzpost_id: r for r in region_rows.values() if r.uzpost_id}
        plan = {'regions': [], 'districts': []}
        region_for = {}
        claimed = set()
        for row in regions:
            obj = region_rows.get(row['soato']) or region_by_uzpost.get(row['uzpost_id'])
            if obj is None:
                errors.append((row['line'], f"no region {row['soato']} in the database; "
                                            "run seed_regions first"))
                continue
            if obj.pk in claimed:
                errors.append((row['line'], f"region {obj.code} is claimed twice"))
                continue
            claimed.add(obj.pk)
            region_for[row['uzpost_id']] = obj
            plan['regions'].append((obj, row))

        district_rows = {d.code: d for d in District.objects.all()}
        district_by_uzpost = {d.uzpost_id: d for d in district_rows.values() if d.uzpost_id}
        claimed = set()
        for row in districts:
            region = region_for.get(row['parent_id'])
            if region is None:
                continue
            if row['soato']:
                obj = district_rows.get(row['soato'])
                if obj is None:
                    errors.append((row['line'], f"no district {row['soato']} in the database; "
                                                "run seed_regions first"))
                    continue
                if not obj.code.startswith('U') and obj.region_id != region.pk:
                    errors.append((row['line'], f"district {row['soato']} is not in region "
                                                f"{region.code}"))
                    continue
            else:
                obj = (district_by_uzpost.get(row['uzpost_id'])
                       or district_rows.get(f"U{row['uzpost_id']}"))
            if obj is not None:
                if obj.pk in claimed:
                    errors.append((row['line'], f"district {obj.code} is claimed twice"))
                    continue
                claimed.add(obj.pk)
            plan['districts'].append((obj, region, row))

        # unique_together (region, name) holds over the whole table, rows
        # switched off included, so the names are checked as they will stand.
        # A ``U`` row a corrected match leaves behind gives up its name: it
        # is switched off, and it was the loader's own row, not an official
        # one, so it takes its code beside the name.
        final = {d.pk: (d.region_id, d.name) for d in district_rows.values()}
        new_names = []
        taken = set()
        for obj, region, row in plan['districts']:
            if obj is None:
                new_names.append((region.pk, row['name'], row['line']))
                taken.add((region.pk, row['name']))
            else:
                final[obj.pk] = (region.pk, row['name'])
                taken.add((region.pk, row['name']))
        kept = {obj.pk for obj, _region, _row in plan['districts'] if obj is not None}
        plan['renamed'] = {}
        for district in district_rows.values():
            if (district.pk not in kept and district.code.startswith('U')
                    and (district.region_id, district.name) in taken):
                renamed = f"{district.name} ({district.code})"[:80]
                plan['renamed'][district.pk] = renamed
                final[district.pk] = (district.region_id, renamed)
        seen = collections.Counter(final.values())
        seen.update((r, n) for r, n, _line in new_names)
        for (region_pk, name), count in seen.items():
            if count > 1:
                errors.append((0, f"two districts of one region would be called {name!r}"))
        return plan, errors

    # ------------------------------------------------------------ writing

    @transaction.atomic
    def _write(self, plan):
        """Apply the plan, then switch off whatever it does not name."""
        counts = dict(r_linked=0, r_off=0, d_created=0, d_updated=0, d_off=0)

        linked = []
        planned = {obj.pk: row['uzpost_id'] for obj, row in plan['regions']}
        # An id moving from one row to another must leave the first before
        # it can arrive: the column is unique.
        for region in Region.objects.filter(uzpost_id__isnull=False):
            if planned.get(region.pk) != region.uzpost_id:
                Region.objects.filter(pk=region.pk).update(uzpost_id=None)
        for obj, row in plan['regions']:
            Region.objects.filter(pk=obj.pk).update(uzpost_id=row['uzpost_id'], is_active=True)
            linked.append(obj.pk)
            counts['r_linked'] += 1

        for pk, name in plan.get('renamed', {}).items():
            District.objects.filter(pk=pk).update(name=name, is_active=False)
        planned = {obj.pk: row['uzpost_id'] for obj, _region, row in plan['districts'] if obj}
        for district in District.objects.filter(uzpost_id__isnull=False):
            if planned.get(district.pk) != district.uzpost_id:
                District.objects.filter(pk=district.pk).update(uzpost_id=None)

        kept = []
        for obj, region, row in plan['districts']:
            values = {
                'region': region, 'name': row['name'], 'kind': row['kind'],
                'latitude': row['lat'], 'longitude': row['lng'],
                'uzpost_id': row['uzpost_id'], 'is_active': True, 'sort_order': 0,
            }
            if obj is None:
                obj = District.objects.create(code=f"U{row['uzpost_id']}", **values)
                counts['d_created'] += 1
            else:
                for field, value in values.items():
                    setattr(obj, field, value)
                obj.save()
                counts['d_updated'] += 1
            kept.append(obj.pk)

        counts['d_off'] = (District.objects.exclude(pk__in=kept)
                           .filter(is_active=True).update(is_active=False))
        counts['r_off'] = (Region.objects.exclude(pk__in=linked)
                           .filter(is_active=True).update(is_active=False))
        return counts

    # ------------------------------------------------------------ fetching

    def _fetch(self, path):
        """Ask Uzpost for both levels and write ``path``, keeping what a person wrote."""
        if not uzpost.configured():
            raise CommandError('UZPOST_LOGIN and UZPOST_PASSWORD are blank; nothing to ask with.')
        level2 = uzpost.jurisdictions(2)
        level3 = uzpost.jurisdictions(3)
        for answer in (level2, level3):
            if not answer.ok:
                raise CommandError(f"Uzpost did not answer: {answer.error}")
        previous = self._read(path) if path.exists() else []
        rows, report = build_rows(level2.data, level3.data,
                                  [row for _line, row in previous], self._official())
        write_rows(path, rows)
        for line in report:
            self.stdout.write(line)
        self.stdout.write(self.style.SUCCESS(f"Wrote {len(rows)} row(s) to {path}."))

    def _official(self):
        """The official district rows from ``regions.csv``, for proposing matches."""
        with OFFICIAL_PATH.open(newline='', encoding='utf-8-sig') as fh:
            return [row for row in csv.DictReader(fh) if row['level'] == 'district']


def build_rows(level2, level3, previous, official):
    """The file's rows from Uzpost's two levels. Returns (rows, report lines).

    ``previous`` is what the file held, so a person's name, ``soato`` and
    ``note`` and a corrected centre survive. Only Uzbekistan's regions are
    taken.
    """
    before = {(row['level'], str(row['uzpost_id'])): row for row in previous}
    report = []
    rows = []
    region_soato, region_words = {}, {}
    for item in sorted(level2, key=lambda r: r['id']):
        old = before.get(('region', str(item['id'])), {})
        soato = old.get('soato') or REGION_SOATO.get(item['id'], '')
        if not soato:
            report.append(f"  region {item['id']} {item['name']!r}: no soato, write one")
        region_soato[item['id']] = soato
        words = clean_name(item['name']).lower().split()
        region_words[item['id']] = re.sub(r'[^a-z]', '', words[0]) if words else ''
        rows.append({'level': 'region', 'uzpost_id': item['id'], 'parent_id': '',
                     'name': clean_name(item['name']), 'kind': '', 'lat': '', 'lng': '',
                     'soato': soato, 'note': old.get('note', '')})

    known = [d for d in level3 if d.get('parent_id') in region_soato]
    taken = {before[('district', str(d['id']))]['soato'] for d in known
             if before.get(('district', str(d['id'])), {}).get('soato')}
    fresh = [d for d in known if ('district', str(d['id'])) not in before]
    proposals = propose_matches(fresh, official, region_soato, region_words, taken)
    kinds = {row['code']: row['kind'] for row in official}
    names = {row['code']: row['name'] for row in official}
    kept = 0

    for item in sorted(known, key=lambda r: (r['parent_id'], clean_name(r['name']))):
        old = before.get(('district', str(item['id'])))
        name = clean_name(item['name'])
        if old is not None:
            soato, note = old['soato'], old['note']
            if old['name'] != name:
                kept += 1
            name = old['name'] or name
        else:
            soato, exact = proposals.get(item['id'], ('', True))
            note = ''
            if soato and not exact:
                report.append(f"  check: {name!r} proposed as {names[soato]!r} ({soato})")
            elif not soato:
                report.append(f"  new: {name!r} has no official district; "
                              "write its Uzbek spelling")
            if soato:
                name = clean_name(names[soato])
        kind = kinds.get(soato) or name_kind(name) or District.Kind.DISTRICT
        lat, lng = _point(item.get('lat')), _point(item.get('lng'))
        if old is not None and note:
            lat, lng = old['lat'], old['lng']
        rows.append({'level': 'district', 'uzpost_id': item['id'],
                     'parent_id': item['parent_id'], 'name': name, 'kind': kind,
                     'lat': lat, 'lng': lng, 'soato': soato, 'note': note})

    if kept:
        report.append(f"  {kept} name(s) kept from the file where Uzpost writes otherwise")
    gone = {key for key in before} - {(row['level'], str(row['uzpost_id'])) for row in rows}
    for level, uzpost_id in sorted(gone):
        report.append(f"  gone: {level} {uzpost_id} {before[(level, uzpost_id)]['name']!r} "
                      "is no longer at Uzpost and will be switched off")
    return rows, report


def write_rows(path, rows):
    """Write the file as the loader reads it."""
    with Path(path).open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator='\n')
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
