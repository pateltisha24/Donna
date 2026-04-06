import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        donna: {
          bg: "#0f0f11",
          surface: "#1a1a1f",
          border: "#2a2a33",
          accent: "#7c6af7",
          "accent-hover": "#9585ff",
          user: "#2d2d38",
          donna: "#1e1e28",
          text: "#e8e8f0",
          muted: "#8888a0",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
