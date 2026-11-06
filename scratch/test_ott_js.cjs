function cleanTitleForSearch(title) {
  let raw = (title || '').trim();
  if (!raw) return '';

  // 1. Safely decode if already URL-encoded to prevent double-encoding
  try {
    if (raw.includes('%')) {
      raw = decodeURIComponent(raw);
    }
  } catch {}

  // 2. Replace colons and plus signs with clean spaces
  let t = raw.replace(/[+:]/g, ' ');

  // 3. Strip quotes and breaking exclamation/question/semicolon characters,
  // while PRESERVING apostrophes (e.g. Grey's Anatomy), hyphens (e.g. Spider-Man),
  // ampersands (e.g. Law & Order), dots/acronyms (e.g. K.G.F.), and all Unicode letters
  t = t.replace(/["?!;]/g, '');

  // 4. Collapse multiple whitespace into a single clean space
  t = t.replace(/\s+/g, ' ').trim();
  return t || raw;
}

function formatTitleForUrl(title) {
  const cleaned = cleanTitleForSearch(title);
  if (!cleaned) return '';
  return encodeURIComponent(cleaned);
}

const testTitles = [
  'Dhurandhar: The Revenge',
  'Dhurandhar+The+Revenge',
  'Dhurandhar%2BThe%2BRevenge',
  'Pirates of the Caribbean: The Curse of the Black Pearl',
  "Grey's Anatomy",
  "Schindler's List",
  'Spider-Man: No Way Home',
  'Law & Order: Special Victims Unit',
  'K.G.F: Chapter 1',
  'Baahubali 2: The Conclusion',
  'धुरंधर: द रिवेंज',
  'పుష్ప 2: ది రూల్',
  'பொன்னியின் செல்வன்: பாகம் 1',
  'മഞ്ഞുമ്മൽ ബോയ്സ്'
];

for (const title of testTitles) {
  const cleaned = cleanTitleForSearch(title);
  const formatted = formatTitleForUrl(title);

  // Assertions
  if (formatted.includes('+')) {
    console.error('FAIL: Found + in formatted URL title:', title, formatted);
    process.exit(1);
  }
  if (formatted.includes('%2B')) {
    console.error('FAIL: Found %2B in formatted URL title:', title, formatted);
    process.exit(1);
  }

  // Simulate what an OTT search box sees when decoding the query param:
  const decodedByOTT = decodeURIComponent(formatted);
  if (decodedByOTT.includes('+')) {
    console.error('FAIL: OTT search box would see +:', title, decodedByOTT);
    process.exit(1);
  }

  console.log(`OK: "${title}" -> Clean: "${cleaned}" -> URL param: "${formatted}" -> OTT Search Box sees: "${decodedByOTT}"`);
}

console.log('\nALL JAVASCRIPT OTT TITLE ENCODING TESTS PASSED!');

