// Deterministic pastel placeholder images (inline SVG data URIs).
// Mock phase only — every "generated image" in the GUI renders one of these.

const PALETTES: [string, string][] = [
  ['#b8a7ee', '#8fe6c0'],
  ['#ffc29e', '#b8a7ee'],
  ['#9ecbff', '#b8a7ee'],
  ['#8fe6c0', '#9ecbff'],
  ['#ffb3c7', '#ffc29e'],
  ['#b8a7ee', '#ffb3c7'],
  ['#8fe6c0', '#ffc29e'],
  ['#9ecbff', '#8fe6c0'],
]

function hashString(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0
  return Math.abs(h)
}

function escapeXml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;')
}

export function placeholderImage(label: string, index = 0, w = 640, h = 640): string {
  const [c1, c2] = PALETTES[(hashString(label) + index) % PALETTES.length]
  const cx = 20 + ((hashString(label) + index * 7) % 55)
  const cy = 16 + ((hashString(label + 'y') + index * 11) % 42)
  const short = escapeXml(label.length > 34 ? label.slice(0, 33) + '...' : label)
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
<defs>
<linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="${c1}"/><stop offset="1" stop-color="${c2}"/>
</linearGradient>
<filter id="b"><feGaussianBlur stdDeviation="46"/></filter>
</defs>
<rect width="${w}" height="${h}" fill="url(#g)"/>
<circle cx="${((cx / 100) * w).toFixed(0)}" cy="${((cy / 100) * h).toFixed(0)}" r="${(w * 0.34).toFixed(0)}" fill="rgba(255,255,255,0.38)" filter="url(#b)"/>
<circle cx="${(w * 0.82).toFixed(0)}" cy="${(h * 0.8).toFixed(0)}" r="${(w * 0.22).toFixed(0)}" fill="rgba(20,18,35,0.12)" filter="url(#b)"/>
<rect x="${(w * 0.055).toFixed(0)}" y="${(h - 58).toFixed(0)}" width="${Math.min(w * 0.89, Math.max(140, short.length * Math.max(10, w * 0.028))).toFixed(0)}" height="40" rx="12" fill="rgba(255,255,255,0.30)"/>
<text x="${(w * 0.075).toFixed(0)}" y="${(h - 31).toFixed(0)}" font-family="Segoe UI, sans-serif" font-size="${Math.max(15, w * 0.038).toFixed(0)}" fill="rgba(24,21,40,0.66)" font-weight="600">${short}</text>
</svg>`
  return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg)
}
