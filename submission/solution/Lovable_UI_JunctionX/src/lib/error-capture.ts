/** Guarda o último erro não tratado do servidor, para o `server.ts` o registar. */
let lastCapturedError: unknown;

function capture(error: unknown): void {
  lastCapturedError = error;
}

if (typeof process !== "undefined" && typeof process.on === "function") {
  process.on("uncaughtException", capture);
  process.on("unhandledRejection", capture);
}

export function consumeLastCapturedError(): unknown {
  const error = lastCapturedError;
  lastCapturedError = undefined;
  return error;
}
