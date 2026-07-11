// Config para GENERAR dashboard/vendor/tailwind.css una única vez (scripts/build-css.sh).
// No hay build step en runtime (F-15): el CSS generado se commitea como asset estático.
// Debe ser el espejo exacto del tailwind.config inline que usaba el CDN.
module.exports = {
  content: ['./index.html', './app.js', '../index.html'],
  theme: {
    extend: {
      colors: {
        amd: '#ED1C24',
        surface: { 900: '#0a0a0f', 800: '#111118', 700: '#1a1a24', 600: '#252530' },
      },
      fontFamily: { mono: ['JetBrains Mono', 'ui-monospace', 'monospace'] },
    },
  },
};
