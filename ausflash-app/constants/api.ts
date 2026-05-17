// ── API ───────────────────────────────────────────────────
// Base URL for the FastAPI backend deployed on Render.
// Change this to http://localhost:8000 for local API testing.
export const API_URL = 'https://ausflash.onrender.com';

// ── Sections ──────────────────────────────────────────────
// 'All' is a client-side concept (no section filter sent to API).
// The rest match the 'section' values stored in Supabase.
export const SECTIONS = [
  'All', 'Crime', 'Tech', 'Politics', 'Business',
  'Science', 'Sport', 'Entertainment', 'Lifestyle', 'World',
];

// ── Section accent colours ─────────────────────────────────
// Each section has a unique colour used for badges, labels, dividers, and tab pills.
export const SECTION_COLORS: Record<string, string> = {
  All:           '#1D9E75', // brand green (default / fallback)
  Crime:         '#7C3AED', // purple
  Tech:          '#4F46E5', // indigo
  Politics:      '#DC2626', // red
  Business:      '#D97706', // amber
  Science:       '#059669', // emerald
  Sport:         '#2563EB', // blue
  Entertainment: '#EC4899', // pink
  Lifestyle:     '#F59E0B', // yellow
  World:         '#1D9E75', // same as All
};
