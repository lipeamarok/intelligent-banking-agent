import { API_BASE_URL } from "./client";
import type { CsvTableName, CsvTableResponse } from "./types";

export async function fetchCsvTable(table: CsvTableName): Promise<CsvTableResponse> {
  const resp = await fetch(`${API_BASE_URL}/admin/csv/${table}`);
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body?.error ?? `Failed to fetch table '${table}' (${resp.status})`);
  }
  return resp.json();
}

export async function resetCsvData(): Promise<{ reset: boolean; tables: string[] }> {
  const resp = await fetch(`${API_BASE_URL}/admin/csv/reset`, { method: "POST" });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body?.error ?? `Reset failed (${resp.status})`);
  }
  return resp.json();
}
