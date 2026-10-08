# The 30-Day Focus Blueprint — Complete eBook + Landing Page Package

A ready-to-sell productivity ebook (focus, discipline, deep work, procrastination) with a
high-converting, SEO-optimized landing page. Designed in a premium "Canva-style" system:
midnight navy + gold, Space Grotesk / Inter / Playfair Display typography.

## 📦 What's in this folder

| Path | What it is |
|---|---|
| `The-30-Day-Focus-Blueprint.pdf` | **The finished 42-page ebook** — sell this. |
| `landing/index.html` | **The landing page** — single file, no dependencies. |
| `landing/assets/` | Cover image, OG/social-share image, self-hosted fonts. |
| `build/` | Source code that generates the PDF (edit content → rebuild). |
| `build/assets/cover-art.png` | AI-generated cover artwork (no text, text is typeset in code). |
| `build/assets/og-image.png` | 1200×630 social share image (also copied to landing). |
| `build/ebook.py` | The design system + page templates (fpdf2). |
| `build/content.py` | All book text: 9 chapters, 30-day plan, toolkit. |
| `build/build.py` | Orchestrator: cover crop, OG image, two-pass TOC, PDF output. |

## 🚀 Sell it in 3 steps

1. **Set your checkout link.** In `landing/index.html`, search for
   `YOUR-CHECKOUT-LINK` and replace it with your Gumroad / Stripe Payment Link /
   Paystack / Shopify / Whop URL (one place, marked with a comment banner).
2. **Deploy the landing page.** It's a single static folder — drop `landing/` onto
   Netlify, Vercel, GitHub Pages, Cloudflare Pages, or any host. No build step.
3. **Upload the PDF** to your checkout provider as the delivered file.

## 🔍 SEO already built in

- Keyword-rich `<title>`, meta description, keywords: *how to focus better, stop
  procrastinating, build discipline, productivity ebook, deep work, time management,
  habit tracker, digital minimalism, ADHD productivity, 30-day challenge…*
- Open Graph + Twitter card tags with a custom 1200×630 share image.
- **Product** JSON-LD schema (price, availability) for Google rich results.
- **FAQPage** JSON-LD schema (6 objection-handling FAQs) — eligible for FAQ rich snippets.
- Semantic headings, canonical URL placeholder (`https://focusblueprint.press/` — change
  to your real domain), mobile-first responsive design, fast single-file load.

## 🛠 Rebuild the PDF after editing content

```bash
pip install fpdf2 pillow fonttools brotli
cd build && python3 build.py
```

- Edit chapter text in `build/content.py` (supports `**bold**` markdown in blocks).
- Design system, colors and templates live in `build/ebook.py`.
- The build regenerates the cover crop, OG image, and a two-pass table of contents
  with real page numbers automatically.

## 💡 Suggested pricing

Launch at **$9** (anchored against $19), raise to $14–$19 after launch week.
The landing page copy, price badges, and schema price (`product:price:amount` +
JSON-LD `"price"`) are the 3 places to update if you change it.

## ⚖️ Notes

- Author persona "A. J. Mercer" is a placeholder — replace with your own name in
  `build/content.py` (copyright page), the cover, and the landing page.
- Stats cited (23-min refocus cost, 47% mind-wandering, 2h24m social media) reflect
  published research/reports; keep them as-is or update with your own sources.
- The book includes a responsible-health disclaimer (ADHD/anxiety → seek professional
  support) — keep it when you edit.
