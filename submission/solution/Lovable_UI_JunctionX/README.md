# Welcome to your Lovable project

This project was built with [Lovable](https://lovable.dev).

## Build with Lovable

Open your project in the [Lovable editor](https://lovable.dev) and keep building.

- **Ship faster**: describe what you want to build and Lovable handles the code.
- **Stay in sync**: connect the project to GitHub and every change made in Lovable is committed straight to your repository.
- **Full ownership**: this code is yours. Push to your repository and your changes sync back into Lovable, ready for your next prompt.

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
npm i
npm run dev
```

## Backend Configuration

By default, the application runs in demo mode with mock data when `VITE_API_URL` is not set.

To connect to the real backend, create a `.env` file (see `.env.example`):

```sh
cp .env.example .env
```

```env
VITE_API_URL=http://127.0.0.1:8000
```

## Themes

The palette button in the header opens an **Appearance** panel with the mode
(light, dark or system) and six color themes: Indigo & Pink (the default),
Ocean, Forest, Sunset, Grape and Graphite. The choice applies at once and is
remembered in `localStorage` (`theme` for the mode, `palette` for the theme).

- The palettes are in `src/themes.css`; they only replace the brand tokens
  (`--brand`, `--brand-2`, `--glow`, `--ring`, `--accent`).
- The logic is in `src/lib/theme.ts` and the panel in
  `src/components/theme-picker.tsx`.
- To add a theme: copy a block in `src/themes.css`, add it to `THEMES` in
  `src/lib/theme.ts` and run `npx vitest run`. The contrast test fails if a
  color is too light or too dark.

See [REVIEW.md](../REVIEW.md) for how it works and how it was verified.

## Built with

- TanStack Start
- TypeScript
- React
- Tailwind CSS
