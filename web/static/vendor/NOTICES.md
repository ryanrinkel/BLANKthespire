# Third-party assets under web/static/vendor/

Self-hosted (the CSP is `font-src 'self'`; no CDN is contacted at runtime). Each file was downloaded once from
the Fontsource npm package on jsDelivr (latin subset, woff2) and checked for the `wOF2` signature. The license
texts sit beside the fonts, copied from the google/fonts repository.

| file | family / weight | version | source | license |
|------|-----------------|---------|--------|---------|
| fonts/barlow-latin-400-normal.woff2 | Barlow 400 | @fontsource/barlow 5.3.0 | https://cdn.jsdelivr.net/npm/@fontsource/barlow@5.3.0/files/barlow-latin-400-normal.woff2 | SIL OFL 1.1, fonts/OFL-Barlow.txt |
| fonts/barlow-latin-600-normal.woff2 | Barlow 600 | @fontsource/barlow 5.3.0 | https://cdn.jsdelivr.net/npm/@fontsource/barlow@5.3.0/files/barlow-latin-600-normal.woff2 | SIL OFL 1.1, fonts/OFL-Barlow.txt |
| fonts/barlow-condensed-latin-600-normal.woff2 | Barlow Condensed 600 | @fontsource/barlow-condensed 5.3.0 | https://cdn.jsdelivr.net/npm/@fontsource/barlow-condensed@5.3.0/files/barlow-condensed-latin-600-normal.woff2 | SIL OFL 1.1, fonts/OFL-Barlow.txt |
| fonts/barlow-condensed-latin-700-normal.woff2 | Barlow Condensed 700 | @fontsource/barlow-condensed 5.3.0 | https://cdn.jsdelivr.net/npm/@fontsource/barlow-condensed@5.3.0/files/barlow-condensed-latin-700-normal.woff2 | SIL OFL 1.1, fonts/OFL-Barlow.txt |
| fonts/b612-mono-latin-400-normal.woff2 | B612 Mono 400 | @fontsource/b612-mono 5.3.0 | https://cdn.jsdelivr.net/npm/@fontsource/b612-mono@5.3.0/files/b612-mono-latin-400-normal.woff2 | SIL OFL 1.1, fonts/OFL-B612.txt |
| fonts/b612-mono-latin-700-normal.woff2 | B612 Mono 700 | @fontsource/b612-mono 5.3.0 | https://cdn.jsdelivr.net/npm/@fontsource/b612-mono@5.3.0/files/b612-mono-latin-700-normal.woff2 | SIL OFL 1.1, fonts/OFL-B612.txt |

License sources (verified 2026-11-10):

- Barlow and Barlow Condensed: https://github.com/google/fonts/blob/main/ofl/barlow/OFL.txt (identical to
  ofl/barlowcondensed/OFL.txt). "Copyright 2017 The Barlow Project Authors (https://github.com/jpt/barlow)".
- B612 Mono: https://github.com/google/fonts/blob/main/ofl/b612mono/OFL.txt.
  "Copyright 2012 The B612 Project Authors (https://github.com/polarsys/b612)".

Used only by web/static/board.css (the "departure board" look).
