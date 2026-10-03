/* English -> Arabic auto-translation via the free MyMemory API. This is the
 * one feature in this app that needs internet access (a real translation
 * requires either that or a large bundled offline model) - everything else
 * stays fully local. Always review/edit the result; it's a starting point,
 * not a final translation. */

async function translateEnToAr(text) {
  const trimmed = String(text || '').trim();
  if (!trimmed) return '';
  const url = `https://api.mymemory.translated.net/get?q=${encodeURIComponent(trimmed)}&langpair=en|ar`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Translation service returned ${res.status}`);
  const data = await res.json();
  const translated = data?.responseData?.translatedText;
  if (!translated || data?.responseStatus !== 200) throw new Error('No translation returned');
  return translated;
}
