import { createFileRoute } from "@tanstack/react-router";
import { ReviewWorkspace } from "@/components/review-workspace";

export const Route = createFileRoute("/")({
  head: () => ({ meta: [
    { title: "Revisão de anonimização — Véu" },
    { name: "description", content: "Reveja o texto anonimizado, aprove ou rejeite versões e consulte o histórico de revisão." },
    { property: "og:title", content: "Revisão de anonimização — Véu" },
    { property: "og:description", content: "Aprovação manual e histórico de versões de documentos anonimizados." },
    { property: "og:type", content: "website" },
    { name: "twitter:card", content: "summary_large_image" },
  ] }),
  component: ReviewWorkspace,
});
