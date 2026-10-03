/*
 * RISK MATRIX CONFIGURATION
 * =========================
 * Official HSE Risk Management criteria (section 6.1.4 "Manage the risk
 * within different levels"). This is the only file that defines how a
 * Severity+Likelihood code is evaluated - nothing else needs to change.
 *
 *   - Severity is a number from 1 (least severe) to 5 (most severe).
 *   - Likelihood is a letter from A (least likely) to E (most likely).
 *   - A risk item's code is Severity+Likelihood, e.g. "2A", "4C".
 *   - The Evaluation column uses the CONTROLLED analysis code.
 *
 *   Risk Level      Range                                   Area
 *   Low             1A, 1B, 2A                              Green
 *   Low Medium      1C, 1D, 2B, 2C, 3A, 3B, 4A              Blue
 *   High Medium     1E, 2D, 2E, 3C, 3D, 4B, 4C              Amber (except 5A/5B)
 *   High            3E, 4D, 4E, 5A, 5B, 5C, 5D, 5E          Red + 5A/5B Amber
 *
 * 5A and 5B are evaluated as High: they're managed as amber-category risks
 * AND the Bow-Tie methodology is applied, same as the red areas.
 */

// Severity/likelihood are plain codes only (e.g. "2C", "5A").
const SEVERITY_VALUES = [1, 2, 3, 4, 5];
const LIKELIHOOD_VALUES = ['A', 'B', 'C', 'D', 'E'];

// Risk level definitions: label (en/ar) + badge colors matching the matrix areas.
const RISK_LEVELS = {
  LOW: { en: 'Low', ar: 'منخفض', color: '#ffffff', bg: '#4caf50' },                       // green
  LOW_MEDIUM: { en: 'Low Medium', ar: 'منخفض إلى متوسط', color: '#000000', bg: '#8eb4e3' }, // blue
  HIGH_MEDIUM: { en: 'High Medium', ar: 'متوسط إلى عالي', color: '#000000', bg: '#ffff00' }, // amber/yellow
  HIGH: { en: 'High', ar: 'عالي', color: '#ffffff', bg: '#e00000' },                       // red
};

// Rows = severity 1..5, columns = likelihood A..E.
const RISK_GRID = {
  1: { A: 'LOW', B: 'LOW', C: 'LOW_MEDIUM', D: 'LOW_MEDIUM', E: 'HIGH_MEDIUM' },
  2: { A: 'LOW', B: 'LOW_MEDIUM', C: 'LOW_MEDIUM', D: 'HIGH_MEDIUM', E: 'HIGH_MEDIUM' },
  3: { A: 'LOW_MEDIUM', B: 'LOW_MEDIUM', C: 'HIGH_MEDIUM', D: 'HIGH_MEDIUM', E: 'HIGH' },
  4: { A: 'LOW_MEDIUM', B: 'HIGH_MEDIUM', C: 'HIGH_MEDIUM', D: 'HIGH', E: 'HIGH' },
  5: { A: 'HIGH', B: 'HIGH', C: 'HIGH', D: 'HIGH', E: 'HIGH' },
};

function evaluateRisk(severity, likelihood) {
  const row = RISK_GRID[severity];
  if (!row) return null;
  const key = row[likelihood];
  if (!key) return null;
  return { key, code: `${severity}${likelihood}`, ...RISK_LEVELS[key] };
}