export function abbreviateId(id: string, head = 8, tail = 6): string {
  if (id.length <= head + tail + 1) {
    return id;
  }
  return `${id.slice(0, head)}...${id.slice(-tail)}`;
}

export function formatNowTime(): string {
  return new Date().toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function createLocalId(prefix = "msg"): string {
  const random = Math.random().toString(36).slice(2, 8);
  return `${prefix}-${Date.now()}-${random}`;
}
