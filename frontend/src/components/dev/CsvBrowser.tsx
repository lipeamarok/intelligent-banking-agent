import { useCallback, useEffect, useRef, useState } from "react";
import { FiAlertTriangle, FiDatabase, FiRefreshCw, FiRotateCcw } from "react-icons/fi";
import { fetchCsvTable, resetCsvData } from "../../api/adminApi";
import type { CsvTableName, CsvTableResponse } from "../../api/types";

const TABLES: { id: CsvTableName; label: string }[] = [
  { id: "clientes", label: "clientes" },
  { id: "score_limite", label: "score_limite" },
  { id: "solicitacoes", label: "solicitações" },
];

export default function CsvBrowser() {
  const [activeTable, setActiveTable] = useState<CsvTableName>("clientes");
  const [data, setData] = useState<CsvTableResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resetting, setResetting] = useState(false);
  const [resetConfirm, setResetConfirm] = useState(false);
  const confirmTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async (table: CsvTableName) => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchCsvTable(table);
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao carregar tabela.");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(activeTable);
  }, [activeTable, load]);

  const handleReset = async () => {
    if (!resetConfirm) {
      setResetConfirm(true);
      confirmTimerRef.current = setTimeout(() => setResetConfirm(false), 4000);
      return;
    }
    if (confirmTimerRef.current) clearTimeout(confirmTimerRef.current);
    setResetConfirm(false);
    setResetting(true);
    try {
      await resetCsvData();
      await load(activeTable);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro ao resetar dados.");
    } finally {
      setResetting(false);
    }
  };

  return (
    <aside className="flex flex-col gap-3 rounded-2xl border border-border bg-panel/75 p-4 min-h-0">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold tracking-wide text-text inline-flex items-center gap-1.5">
          <FiDatabase /> CSV Browser
        </h2>
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => load(activeTable)}
            disabled={loading}
            title="Recarregar"
            className="rounded p-1 text-muted hover:text-text disabled:opacity-40 transition-colors"
          >
            <FiRefreshCw className={loading ? "animate-spin" : ""} size={13} />
          </button>
          <button
            onClick={handleReset}
            disabled={resetting}
            title={resetConfirm ? "Clique novamente para confirmar" : "Resetar para padrão"}
            className={`rounded px-2 py-0.5 text-xs font-medium transition-colors disabled:opacity-40 ${
              resetConfirm
                ? "bg-error/20 text-error border border-error/40"
                : "bg-warning/10 text-warning border border-warning/20 hover:bg-warning/20"
            }`}
          >
            {resetting ? "…" : resetConfirm ? "⚠ Confirmar reset" : <span className="inline-flex items-center gap-1"><FiRotateCcw size={10} />Reset</span>}
          </button>
        </div>
      </div>

      {/* Table selector */}
      <div className="flex gap-1">
        {TABLES.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => setActiveTable(id)}
            className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${
              activeTable === id
                ? "bg-primary/20 text-primary border border-primary/30"
                : "text-muted hover:text-text border border-transparent hover:border-border"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-start gap-1.5 rounded-lg border border-error/30 bg-error/10 px-3 py-2 text-xs text-error">
          <FiAlertTriangle className="mt-0.5 shrink-0" size={12} />
          <span>{error}</span>
        </div>
      )}

      {/* Table */}
      {data && !error && (
        <div className="overflow-auto rounded-lg border border-border text-xs min-h-0 max-h-[420px]">
          <table className="w-full border-collapse">
            <thead className="sticky top-0 bg-panel">
              <tr>
                {data.columns.map((col) => (
                  <th
                    key={col}
                    className="border-b border-border px-2 py-1.5 text-left font-semibold text-text whitespace-nowrap"
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.rows.length === 0 ? (
                <tr>
                  <td
                    colSpan={data.columns.length}
                    className="px-2 py-3 text-center text-muted italic"
                  >
                    Nenhum registro
                  </td>
                </tr>
              ) : (
                data.rows.map((row, i) => (
                  <tr key={i} className="hover:bg-card/40 transition-colors">
                    {data.columns.map((col) => (
                      <td
                        key={col}
                        className="border-b border-border/50 px-2 py-1 text-muted max-w-[140px] truncate"
                        title={row[col] ?? ""}
                      >
                        {row[col] ?? "—"}
                      </td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {!data && !error && !loading && (
        <p className="text-center text-xs text-muted italic py-4">Selecione uma tabela</p>
      )}

      <p className="text-[10px] text-subtle">
        Dados do ambiente de execução atual.
      </p>
    </aside>
  );
}
