<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.
<!-- LOVABLE:END -->

- Use shared semantic CSS tokens and the shared Button component across the anonymizer workflow so visual changes remain consistent across all steps.
- Review session state is the backend snapshot (src/lib/review); the UI never derives versions locally, so it stays in sync with /api/current. The mock in src/lib/review/mock.ts must follow the same snapshot contract.
