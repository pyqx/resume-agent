import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: "#eff6ff",
          500: "#3b82f6",
          600: "#2563eb",
          700: "#1d4ed8",
        },
        success: { 500: "#22c55e" },
        warning: { 500: "#f59e0b" },
        danger: { 500: "#ef4444" },
      },
    },
  },
  plugins: [],
};

export default config;
