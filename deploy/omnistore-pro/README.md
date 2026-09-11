# Deploying OmniStore-Pro (Vercel / Netlify)

Everything needed to publish the **OmniStore** web catalogue is here, because this
agent has **read-only access to `iamsmmh/OmniStore-Pro`** (GitHub returns 403 on
push), so the changes ship as a patch instead of a pull request.

## Why a patch is needed at all

The deploy buttons for Vercel and Netlify both build whatever is on the repo's
default branch. Today that build fails twice over:

1. `npm ci` aborts — `eslint@^10` is outside the peer range `eslint-config-next@15`
   declares (`ERESOLVE`).
2. Even with `--legacy-peer-deps`, the build dies compiling CSS — `tailwindcss@^4`
   is pinned while `postcss.config.mjs`, `globals.css` and `tailwind.config.ts` are
   all Tailwind v3 style:

   ```
   Error: It looks like you're trying to use `tailwindcss` directly as a PostCSS plugin.
   ```

So `main` cannot be deployed to any Node host until these two lines are fixed.

## Apply (≈2 minutes)

```bash
git clone https://github.com/iamsmmh/OmniStore-Pro.git
cd OmniStore-Pro
git checkout main
git checkout -b fix/deps-and-deploy
git am /path/to/omnistore-pro-deploy.patch     # applies both commits
git push -u origin fix/deps-and-deploy         # open a PR, merge it
```

No `git` available? Add the two config files by hand — `files/vercel.json` and
`files/netlify.toml` (drag-and-drop into the GitHub web UI), then make the two
edits in `package.json`: `"eslint": "^9.39.5"` and `"tailwindcss": "^3.4.19"`.
Note that skipping the lockfile regeneration makes `npm ci` fail; hosts fall back
to `npm install`, which still works.

## Then click Deploy

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2Fiamsmmh%2FOmniStore-Pro)
[![Deploy to Netlify](https://www.netlify.com/img/deploy/button.svg)](https://app.netlify.com/start/deploy?repository=https://github.com/iamsmmh/OmniStore-Pro)

Both work with **no environment variables** — the app ships a validated feed at
`data/omnisource-feed.json` (110 apps, 653 releases) and needs no backend. Once a
live OmniSource deployment exists, `NEXT_PUBLIC_OMNISOURCE_API_URL` switches the
catalogue over to it without any code change.

## What the patch changes

| Commit | Change |
| --- | --- |
| `fix(deps)` | `eslint ^10.10.0 → ^9.39.5`, `tailwindcss ^4.3.3 → ^3.4.19`, lockfile regenerated |
| `feat(deploy)` | `vercel.json`, `netlify.toml`, README Deploy buttons, site-URL resolution + 6 tests |

`vercel.json` pins `npm ci` and `npm run build`. `netlify.toml` selects the
Next.js runtime (`@netlify/plugin-nextjs`) — required, since search, feeds,
sitemap, reporting and caching are server-rendered by design; a static publish
cannot work.

The site URL (canonical tags, Open Graph, `sitemap.xml`, `robots.txt`) now
resolves in this order, so a first deploy is correct with zero configuration:

| Order | Source | Host |
| --- | --- | --- |
| 1 | `NEXT_PUBLIC_SITE_URL` | any (custom domains) |
| 2 | `VERCEL_URL` | Vercel (set during builds) |
| 3 | `DEPLOY_PRIME_URL`, then `URL` | Netlify (set during builds) |
| 4 | `http://localhost:3000` | local development |

`resolveSiteUrl` also adds the missing scheme to Vercel's scheme-less host and
keeps the empty string meaningful for `NEXT_PUBLIC_OMNISOURCE_API_URL`
(empty = use the bundled feed).

## Verification (on the patched tree)

```
npm ci                            -> added 481 packages, no ERESOLVE
npm run lint -- --max-warnings=0  -> No ESLint warnings or errors
npm run typecheck                 -> clean
npm run test:unit                 -> 24 files, 245 tests passed
npm run build                     -> compiled successfully
npm run test:integration          -> 3 files, 84 tests passed
feed contract (zod)               -> feed ok: 110 apps
```

Deploy-URL behaviour, checked against a real server built with `VERCEL_URL` set:

```
sitemap.xml  -> <loc>https://omnistore-pro.vercel.app/alternatives</loc>
canonical    -> <link rel="canonical" href="https://omnistore-pro.vercel.app">
og:url       -> https://omnistore-pro.vercel.app
```

and the same build served with `DEPLOY_PRIME_URL` instead:

```
sitemap.xml  -> <loc>https://deploy-preview-7--omnistore.netlify.app/alternatives</loc>
canonical    -> https://deploy-preview-7--omnistore.netlify.app
```

Not run: `npm run e2e` (needs `npx playwright install --with-deps chromium`).

## Files

| Path | Purpose |
| --- | --- |
| `omnistore-pro-deploy.patch` | both commits as one mbox — `git am` |
| `files/vercel.json` | drop-in copy for manual application |
| `files/netlify.toml` | drop-in copy for manual application |
| `files/site-url.patch` | just the `src/config/site.ts` change, if you prefer to hand-pick |

## Faster option

Give the Arena GitHub app write access to `iamsmmh/OmniStore-Pro` and ask for a
pull request — the same two commits will be pushed to a branch for review instead
of living as a patch file.
