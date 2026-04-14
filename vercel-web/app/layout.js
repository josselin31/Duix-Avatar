import "./globals.css";

export const metadata = {
  title: "Glyce Video Studio",
  description: "Text to short video in a simple iPhone-first UI."
};

export default function RootLayout({ children }) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
