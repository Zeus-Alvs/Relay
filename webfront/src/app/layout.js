import "./globals.css";

export const metadata = {
  title: "Relay — Servidor Compartilhado Entre Amigos",
  description:
    "Hospede servidores de jogo com seus amigos sem custos fixos. O Relay orquestra o revezamento automático — cada um joga na sua vez, o mundo nunca se perde.",
  keywords: ["relay", "minecraft", "servidor compartilhado", "p2p", "hosting gratuito", "mente coletiva"],
  openGraph: {
    title: "Relay — Servidor Compartilhado Entre Amigos",
    description:
      "Hospede servidores de jogo com seus amigos sem custos fixos. Revezamento automático, zero configuração manual.",
    type: "website",
    images: ["/relay_ico.png"],
  },
};

export default function RootLayout({ children }) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
