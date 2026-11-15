// Colour by day of detection, as FIRMS colours "time since detection": pale for the earliest days of the
// month, deep red for the latest. Shared by the globe and its legend (kept apart so the globe stays lazy).
export const DAY_COLORS = ['255,236,170', '255,200,90', '255,150,50', '245,90,35', '215,30,30']
export const DAY_RANGES = ['1–6', '7–12', '13–18', '19–24', '25–31']

/** Day-of-month class of a detection date (YYYY-MM-DD): 0 = days 1-6 ... 4 = days 25-31. */
export function dayClass(date: string): number {
  const day = Number(date.slice(8, 10))
  return Number.isFinite(day) && day > 0 ? Math.min(4, Math.floor((day - 1) / 6)) : 4
}
