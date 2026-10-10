# Contributing

These are the rules the codebase is already written to. Most of them exist
because something went wrong once; the comment next to the code usually says
what.

---

## Hard rules

**No new Python dependencies.** Everything needed is installed or in the
standard library. There is exactly one exception, `redis`, taken deliberately
and recorded as §17 #240. Adding a second one is a conversation, not a commit.

**No secret in the repository.** Everything lives in `.env`, which is ignored.
`.env.example` documents every key with a blank or an obviously fake value.

**Every model change ships with its migration, in the same commit.** A commit
that changes a model and not the migration is a broken deploy waiting for
whoever pulls it.

**URL names never change.** Paths may, with a 301. Templates, tests and the
sitemap all resolve by name.

**No hardcoded user-facing string.** Everything goes through `{% trans %}` or
`gettext`. This includes `messages.success(...)` and form errors — there is a
test that walks the source and fails on a literal.

**No hardcoded design value.** Every colour, space, radius, font size and
duration comes from a token in `static/css/tokens.css`. CSS class names are
BEM.

**An outside service never breaks a request.** Eskiz, Telegram, Google Maps
and Click all follow the pattern in `core/sms.py`: module logger, catch
everything, log it, return something falsy. An outage turns a feature off; it
does not produce a 500.

---

## Things that are correct as written

Change these only with a reason you can defend, and never as a side effect of
something else:

- the `select_for_update` lock and total computation in
  `payment.services.create_order_from_cart` — add to it, do not restructure it
- the OTP flows, their rate limits, and phone normalisation in `User.save()`
- `_cancel_and_delete`, which must never delete a user who has an order or a
  claimed cart
- the Click webhook path, `/payment/click/update/` exactly — unprefixed and
  outside `i18n_patterns`. Breaking it means payments that fail silently

---

## Style

Docstrings on every module, class and function. Brief, and about **why** —
what the code does is visible; why it does it that way is not. Match the
existing voice, which explains the trap it is avoiding rather than restating
the signature.

Commits: `<phase>: <imperative summary>`, one branch per phase. The body is
worth writing — several of the decisions in the plan were reconstructed from
commit messages.

---

## Language and copy

The site is **Uzbek-first**, in Latin script, with the correct `oʻ` and `gʻ`
(U+02BB, not an apostrophe). Russian is written in a natural commercial
register; English for a fluent reader. All three are **written**, never bulk
machine translation into a `.po` file.

Uzbek is the source language, so a msgid *is* an Uzbek string. That has a
consequence worth internalising: **changing an Uzbek string by one character
orphans its Russian and English translations.** The msgid stops matching, both
fall back to Uzbek, and nothing fails. Run `makemessages` after touching
translatable copy and read the diff — a `#, fuzzy` entry or a new `#~` is that
bug, caught.

```bash
python manage.py makemessages -l uz -l ru -l en \
    --ignore docs --ignore deploy --ignore pictures \
    --ignore staticfiles --ignore media --ignore "Claude outputs"
python manage.py compilemessages --ignore .venv
```

The `--ignore` flags are not optional. The apps sit at the repository root, so
without them `makemessages` extracts strings out of `docs/` and
`compilemessages` walks into `.venv` and recompiles every catalogue Django
ships.

---

## Design bar

The point of this rebuild is that the site should not look templated, generic
or machine-made. **Mobile at 390 px is the design surface.** The product
photograph is the largest, sharpest thing on screen.

Restraint over decoration: no gradient meshes, no glassmorphism, no floating
3D shapes, no hero-plus-three-icons layout. Confidence comes from typography,
spacing and photography.

### The font file

All type is one face, Inter, served from `static/fonts/inter-var.woff2`. The
file is Inter 4.1's `InterVariable.ttf` (github.com/rsms/inter, SIL Open Font
License) cut down to the characters the site draws. It keeps the weight and
optical-size axes, so one file covers every weight and headings get the
display cut. To cut it again, with `fonttools` and `brotli` installed outside
the project:

```bash
pyftsubset InterVariable.ttf \
  --unicodes="U+0000,U+0020-007E,U+00A0-00AC,U+00AE-0148,U+014A-017F,U+0181,U+0186-018A,U+018E-0194,U+0196-0199,U+019D,U+01A0-01A1,U+01A4-01A5,U+01AC-01AD,U+01AF-01B0,U+01B2-01B4,U+01B7,U+01CD-01DD,U+01E4-01E9,U+01EE-01F0,U+01F4-01F5,U+01F8-01FF,U+0218-021B,U+021E-021F,U+0237,U+0244-0245,U+024C-024D,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0300-0304,U+0308,U+0400-045F,U+0490-0491,U+2010,U+2013-2014,U+2018-2019,U+201C-201E,U+2020-2022,U+2026,U+2030,U+2039-203A,U+2044,U+20AC,U+20BD,U+2116,U+2190-2193,U+2212,U+221E,U+2248,U+2260,U+2264-2265,U+2713" \
  --layout-features=kern,mark,mkmk,ccmp,locl,calt,case,tnum \
  --flavor=woff2 --no-hinting --output-file=static/fonts/inter-var.woff2
```

Subsetting can drop `ʻ` (U+02BB) and `ʼ` (U+02BC) without anything else
failing, so `core/test_phase17.py` reads the file that ships and checks for
them, for Cyrillic and for the weight range. A face is usable here only if it
has those letters; most display faces do not.

---

## Before you open a pull request

```bash
python manage.py check
python manage.py test --parallel 4
```

CI runs both against a real PostgreSQL, plus `check --deploy` with `DEBUG`
off, which is the only run where the production security settings are checked
at all.

Measure rather than assert. Phase 9's accessibility work reached 100 on
Lighthouse only because it was run against a production-shaped server; two of
the defects it found had passed every test and every manual sweep.
