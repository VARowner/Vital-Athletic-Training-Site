# vitalathletic.com

The Vital Athletic website, hosted on GitHub Pages. It replaces the old Weebly site.

## How it works
- `site/` is the website. GitHub Pages serves exactly what is in it.
- Every push to `main` republishes the site (`.github/workflows/site.yml`).
- `site/` started as an exact copy of the Weebly site, made by `scripts/mirror.py`. It keeps every old page
  address (`/about.html`, `/contact.html`, …) so existing links and search results still work, and it
  has its own copies of all images, styles and scripts so nothing depends on Weebly.
- Changes from the original copy: the blog is removed (`/blog.html` now goes to the home page), and the
  template vendor's credit link is removed.

## Re-copying from Weebly
Only while `vitalathletic.com` still points at Weebly: Actions → **Site** → **Run workflow** → tick
**refresh**. This overwrites `site/`.

## DNS (managed at Wix — email runs on Google Workspace, don't touch MX/TXT)
- `@` A records → `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`
- `www` CNAME → `varowner.github.io`
- Custom domain is set in repo Settings → Pages (plus a `site/CNAME` file containing `vitalathletic.com`).

## Forms
The contact and free-offer forms are sent by `static/assets/forms.js` to **Formspree**, which emails each
submission and keeps a copy. Set `FORM_ENDPOINT` in that file to the Formspree form's URL. While it is
blank, submitting opens a pre-filled email to mpitts@vitalathletic.com instead, so nothing is lost.
The contact page map is a plain Google Maps embed.

Edit anything in `static/`, then run `python3 scripts/mirror.py --finalize-only` (or just push — the copy
step re-applies it on the next refresh).
