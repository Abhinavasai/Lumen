import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#fafafa",
        surface: "#ffffff",
        "surface-hover": "#f1f5f9",
        border: "#e2e8f0",
        "border-hover": "rgba(99,102,241,0.4)",
        ring: "rgba(99,102,241,0.2)",
        primary: {
          DEFAULT: "#6366f1",
          light: "#4f46e5",
          dark: "#4338ca",
        },
        accent: "#8b5cf6",
        success: { DEFAULT: "#10b981", light: "#059669" },
        warning: { DEFAULT: "#f59e0b", light: "#d97706" },
        danger: { DEFAULT: "#ef4444", light: "#dc2626" },
        text: {
          primary: "#0f172a",
          secondary: "#475569",
          muted: "#94a3b8",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "sans-serif"],
      },
      borderRadius: {
        xl: "14px",
        "2xl": "18px",
      },
      animation: {
        "fade-in": "fadeIn 0.4s ease-out",
        "slide-up": "slideUp 0.4s ease-out",
        pulse: "pulse 2s ease-in-out infinite",
      },
      keyframes: {
        fadeIn: {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        slideUp: {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
