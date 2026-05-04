/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0B1020",
        panel: "#12182B",
        card: "#18213A",
        border: "#26314D",
        text: "#E8EEF9",
        muted: "#A8B3C7",
        subtle: "#7B879C",
        primary: "#4F7CFF",
        accent: "#22C7F2",
        success: "#22C55E",
        warning: "#F59E0B",
        danger: "#EF4444"
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"]
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(79, 124, 255, 0.35), 0 12px 30px rgba(34, 199, 242, 0.08)"
      },
      backgroundImage: {
        "hero-gradient": "radial-gradient(1200px 500px at 20% -10%, rgba(79, 124, 255, 0.25), transparent 55%), radial-gradient(1000px 500px at 100% 0%, rgba(34, 199, 242, 0.12), transparent 50%)"
      }
    },
  },
  plugins: [],
};
