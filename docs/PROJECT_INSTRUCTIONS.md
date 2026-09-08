You are working with Kamronbek on **GRAPHIX** (formerly ValleyMade) — a Django 6 / PostgreSQL online store for graphic t-shirts in Uzbekistan, being rebuilt from a working but dated site into a professional one. Repo: `D:\phyton\ValleyMade\`, Django package `vm/`. Production: valleymade.uz → graphix.uz.

## Read the plan first, every time

**`docs/PLAN.md` in the repo (also `claude/PLAN.md` in this project) is the single source of truth.** Read it before doing anything else in a chat, including answering questions about the project. It holds the phase breakdown, the locked technical decisions, the data model, the design system, the conventions, and the running progress.

Work is done across many chats. A chat may cover one phase, several, or part of one — that's practical. What must hold is that **every chat's output is consistent with every other chat's, as if one person built the whole thing.** The plan is what makes that possible; it is the shared memory between chats.

- Follow the **execution order in §13**, and pass a phase's Definition of Done before starting the next — even within a single chat.
- **Never change a locked decision (§3) or a convention (§4) on your own.** Raise it with Kamronbek, get agreement, record it in §17 (Decision log), then act.
- **Never re-litigate a settled question.** If §17 answers it, it's answered.
- A new idea mid-work goes into **§18 (Backlog)** — note it and keep going. Don't silently expand scope.

## Keep the plan current

Before a chat ends — and periodically during a long one — update:

- **§15 Progress tracker** — phase status, branch, dates
- **§16 Session log** — one line: what was done, what's next
- **§17 Decision log** — any decision that shapes future work
- **§19 Open questions** — mark resolved ones, add new ones

An out-of-date plan makes the next chat worse. This is part of the work, not overhead.

## Working style

Kamronbek is the developer; he reviews everything. He is direct and will push back when output doesn't match requirements — take the correction and fix it, don't over-apologise.

- **Analyse first, then change.** State the plan, get agreement, then execute. Especially for anything touching auth, payments or the cart.
- **Preserve existing behaviour.** Refactors are fine; behaviour changes are not, unless a phase explicitly calls for one. "Don't break anything" is the standing requirement.
- **Deliver complete drop-in file replacements**, not partial snippets, unless he asks otherwise.
- **Be concise.** Explain what changed and why it matters; skip the recap of what he just watched you do.
- Say when something is a bad idea, and why. He asked for review, not agreement.

## File operations — important

The cloud container **cannot see the `D:` drive**. All work on repo files goes through the filesystem MCP or the device shell (`desktop-commander`), never the container's own bash.

- Read before editing; batch with `read_multiple_files` for cross-file context.
- Prefer **full-file rewrites** (`write_file`) over `edit_file` for anything non-trivial — `edit_file` is fragile with Django template syntax and regex-special characters, and has produced silent corruption in this repo before.
- Split unrelated edits into separate calls; a batched edit can silently no-op if one `oldText` fails to match.
- Read back after writing to confirm.

## Code conventions

- **Docstrings on every module, class and function** — brief, simple, explaining *why*. Match the existing style; it's already good.
- **Zero new Python dependencies.** Everything needed is installed or standard library. This is a hard constraint.
- **CSS**: BEM. Every colour, space, radius, font size and duration comes from a token in `tokens.css` — no hardcoded design values, ever.
- **No hardcoded user-facing strings** after Phase 3 — everything through `{% trans %}`.
- **Every model change ships with its migration in the same commit.**
- **URL *names* never change.** Paths may (with a 301).
- **External calls never break a request.** Eskiz, Telegram, Yandex and Click all follow the pattern in `core/sms.py`: module logger, catch everything, log, return falsy. An outage degrades a feature; it never 500s a page.
- Commits: `<phase>: <imperative summary>`. One branch per phase.

## Never break these

1. **The Click webhook must resolve at exactly `/payment/click/update/`** — unprefixed, outside `i18n_patterns`. Breaking it means silent payment failures.
2. **`create_order_from_cart`'s `select_for_update` lock and its total computation.** Add to it; don't restructure it.
3. **The OTP flows, rate limiting, and phone normalisation in `User.save()`.** All correct as written.
4. **`_cancel_and_delete` must never delete a user who has an order or a claimed cart.**
5. **Never run a destructive database operation on production** without a fresh, verified `pg_dump`.
6. **No secret enters the repo.** Everything stays in `.env`.

## Language and copy

The site is Uzbek-first (Latin script, correct `oʻ`/`gʻ`), with Russian and English. Copy in all three is **written, not translated** — never bulk machine translation into `.po` files. Russian in natural commercial register; English for a fluent reader. Uzbek is the source of truth.

## Design bar

The point of this rebuild is that the site should not look templated, generic or AI-generated. Mobile at 390 px is the design surface. The product photograph is the largest, sharpest thing on screen. Restraint over decoration — no gradient meshes, no glassmorphism, no floating 3D shapes, no hero-plus-three-icons layout. Confidence comes from typography, spacing and photography.
