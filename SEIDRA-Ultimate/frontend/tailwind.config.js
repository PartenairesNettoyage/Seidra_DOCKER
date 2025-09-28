/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: [
    './pages/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './app/**/*.{ts,tsx}',
    './src/**/*.{ts,tsx}',
  ],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      colors: {
        // Palette optimisée pour un contraste AA
        gold: {
          DEFAULT: '#F4C95D',
          50: '#FFF8E6',
          100: '#FFE8B3',
          200: '#FFD16B',
          300: '#F4C95D',
          400: '#C89B38',
          500: '#9C7426',
          600: '#6F5118',
          700: '#4C380F',
          800: '#312309',
          900: '#1A1305',
        },
        purple: {
          DEFAULT: '#2A176B',
          50: '#F3F0FF',
          100: '#E5DDFF',
          200: '#C7B8FF',
          300: '#A290FF',
          400: '#7D69F5',
          500: '#5948D6',
          600: '#4132AB',
          700: '#2E237C',
          800: '#20175A',
          900: '#140E3A',
        },
        midnight: {
          50: '#F6F7FF',
          100: '#E7E9FF',
          200: '#C9CCF1',
          300: '#A5A7DD',
          400: '#7F82C4',
          500: '#5B5DA7',
          600: '#3B3D80',
          700: '#26265D',
          800: '#18183F',
          900: '#0D0C28',
        },
        mystical: {
          dark: '#0E0A24',
          darker: '#070417',
          light: '#181134',
          glow: '#F4C95D',
          accent: '#7D69F5',
        },
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      keyframes: {
        "accordion-down": {
          from: { height: 0 },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: 0 },
        },
        "mystical-glow": {
          "0%, 100%": { 
            boxShadow: "0 0 20px rgba(255, 215, 0, 0.3), 0 0 40px rgba(255, 215, 0, 0.1)" 
          },
          "50%": { 
            boxShadow: "0 0 30px rgba(255, 215, 0, 0.5), 0 0 60px rgba(255, 215, 0, 0.2)" 
          },
        },
        "mystical-pulse": {
          "0%, 100%": { 
            opacity: 1,
            transform: "scale(1)" 
          },
          "50%": { 
            opacity: 0.8,
            transform: "scale(1.05)" 
          },
        },
        "mystical-float": {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-10px)" },
        },
        "mystical-shimmer": {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        "gradient-shift": {
          "0%, 100%": { 
            backgroundPosition: "0% 50%" 
          },
          "50%": { 
            backgroundPosition: "100% 50%" 
          },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        "mystical-glow": "mystical-glow 3s ease-in-out infinite",
        "mystical-pulse": "mystical-pulse 2s ease-in-out infinite",
        "mystical-float": "mystical-float 4s ease-in-out infinite",
        "mystical-shimmer": "mystical-shimmer 2s linear infinite",
        "gradient-shift": "gradient-shift 3s ease infinite",
      },
      backgroundImage: {
        'mystical-gradient': 'linear-gradient(135deg, #2D1B69 0%, #0F0A1E 50%, #0A0614 100%)',
        'gold-gradient': 'linear-gradient(135deg, #FFD700 0%, #E6C200 50%, #CCAD00 100%)',
        'mystical-shimmer': 'linear-gradient(90deg, transparent, rgba(255, 215, 0, 0.2), transparent)',
      },
      fontFamily: {
        'mystical': ['Inter', 'system-ui', 'sans-serif'],
      },
      backdropBlur: {
        'mystical': '12px',
      },
    },
  },
  plugins: [
    require("@tailwindcss/forms"),
    require("@tailwindcss/typography"),
    function({ addUtilities }) {
      const newUtilities = {
        '.seidra-glass': {
          background: 'rgba(45, 27, 105, 0.1)',
          backdropFilter: 'blur(12px)',
          border: '1px solid rgba(255, 215, 0, 0.1)',
        },
        '.seidra-gradient': {
          background: 'linear-gradient(135deg, #FFD700 0%, #E6C200 50%, #CCAD00 100%)',
        },
        '.seidra-text-glow': {
          textShadow: '0 0 10px rgba(255, 215, 0, 0.5), 0 0 20px rgba(255, 215, 0, 0.3)',
        },
        '.seidra-animate-pulse-gold': {
          animation: 'mystical-pulse 2s ease-in-out infinite',
          color: '#F4C95D',
        },
        '.seidra-mystical-bg': {
          background: 'linear-gradient(135deg, #20175A 0%, #0D0C28 50%, #070417 100%)',
        },
        '.seidra-card': {
          background: 'rgba(32, 23, 90, 0.2)',
          backdropFilter: 'blur(12px)',
          border: '1px solid rgba(244, 201, 93, 0.25)',
          borderRadius: '12px',
        },
        '.seidra-button': {
          background: 'linear-gradient(135deg, #F4C95D 0%, #C89B38 100%)',
          color: '#140E3A',
          fontWeight: '600',
          transition: 'all 0.3s ease',
          '&:hover': {
            transform: 'translateY(-2px)',
            boxShadow: '0 10px 25px rgba(244, 201, 93, 0.35)',
          },
        },
      }
      addUtilities(newUtilities)
    },
  ],
}