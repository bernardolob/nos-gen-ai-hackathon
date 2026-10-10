/** Regista um erro da UI na consola. Não envia nada para fora do navegador. */
export function reportLovableError(
  error: unknown,
  context: Record<string, unknown> = {},
): void {
  console.error("Erro na UI", context, error);
}
