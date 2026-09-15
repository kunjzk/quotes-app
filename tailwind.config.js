/** Tailwind is compiled at image build time (see Dockerfile) rather than in the browser. */
module.exports = {
  content: ["./quotesapp/**/*.{html,js,py}"],
  theme: {
    extend: {
      fontFamily: {
        serif: ['"Newsreader"', "Georgia", '"Times New Roman"', "serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
