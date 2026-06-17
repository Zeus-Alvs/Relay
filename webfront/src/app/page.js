"use client";

import { useState, useEffect } from "react";

// ============================================
// CHEVRON SVG
// ============================================
function ChevronDown({ className }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}

// ============================================
// NAVBAR
// ============================================
function Navbar() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const handleNavClick = () => setMobileOpen(false);

  return (
    <nav className="navbar" style={scrolled ? { boxShadow: "0 4px 30px rgba(0,0,0,0.3)" } : {}}>
      <div className="navbar-inner">
        <a href="#home" className="navbar-logo">
          <img src="/relay_ico.png" alt="Relay" />
          <span>Relay</span>
        </a>

        <button
          className="navbar-hamburger"
          onClick={() => setMobileOpen(!mobileOpen)}
          aria-label="Menu"
        >
          <span></span>
          <span></span>
          <span></span>
        </button>

        <ul className={`navbar-links ${mobileOpen ? "open" : ""}`}>
          <li><a href="#home" onClick={handleNavClick}>Home</a></li>
          <li><a href="#como-funciona" onClick={handleNavClick}>Como Funciona</a></li>
          <li><a href="#download" onClick={handleNavClick}>Download</a></li>
          <li><a href="#tutorial" onClick={handleNavClick}>Tutorial</a></li>
        </ul>
      </div>
    </nav>
  );
}

// ============================================
// HERO
// ============================================
function Hero() {
  return (
    <section className="hero" id="home">
      <div className="hero-bg">
        <div className="hero-grid"></div>
        <div className="hero-particles">
          <div className="particle"></div>
          <div className="particle"></div>
          <div className="particle"></div>
          <div className="particle"></div>
          <div className="particle"></div>
          <div className="particle"></div>
        </div>
      </div>

      <div className="hero-content reveal">
        <div className="hero-badge">
          <span className="dot"></span>
          Open Source &middot; Gratuito
        </div>

        <h1>
          Um servidor de Minecraft{" "}
          <br />
          <span className="highlight">que ninguém paga.</span>
        </h1>

        <p className="hero-description">
          O Relay deixa você e seus amigos se revezarem como host.
          Quando um sai, o próximo assume — e o mundo continua de onde parou.
        </p>

        <div className="hero-actions">
          <a href="#download" className="btn btn-primary">
            ⬇ Baixar
          </a>
          <a href="#como-funciona" className="btn btn-secondary">
            Como funciona? →
          </a>
        </div>
      </div>
    </section>
  );
}

// ============================================
// STEPS (Como Funciona)
// ============================================
function Steps() {
  const steps = [
    {
      icon: "📥",
      title: "Instale",
      description: "Baixa o instalador e roda. Ele já traz tudo junto — VPN, sincronização, motor de jogo.",
    },
    {
      icon: "🔗",
      title: "Conecte",
      description: "Cria um servidor ou entra num que já existe com um código de 6 dígitos que seu amigo te manda.",
    },
    {
      icon: "🎮",
      title: "Jogue",
      description: "Quando é a sua vez, o Relay baixa o mundo, liga tudo e inicia o servidor pra você. Fechou o jogo? Ele salva na nuvem pro próximo.",
    },
  ];

  return (
    <section className="steps" id="como-funciona">
      <div className="container">
        <div className="steps-header reveal">
          <h2 className="section-title">Como funciona?</h2>
          <p className="section-subtitle" style={{ margin: "0 auto" }}>
            Três passos. Sem terminal, sem configuração manual.
          </p>
        </div>

        <div className="steps-grid">
          {steps.map((step, i) => (
            <div key={i} className={`step-card reveal reveal-delay-${i + 1}`}>
              <span className="step-icon">{step.icon}</span>
              <div className="step-number">{i + 1}</div>
              <h3>{step.title}</h3>
              <p>{step.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ============================================
// FEATURES
// ============================================
function Features() {
  const features = [
    {
      icon: "🔒",
      title: "VPN entre amigos",
      description: "Todo mundo se conecta por uma rede privada (Tailscale). Sem abrir portas, sem dor de cabeça.",
    },
    {
      icon: "☁️",
      title: "Mundo na nuvem",
      description: "O mapa do servidor fica salvo no Google Drive. Se seu PC pegar fogo, o mundo sobrevive.",
    },
    {
      icon: "🔄",
      title: "Fila automática",
      description: "Tem gente jogando? Você entra na fila. Quando o host sair, o próximo assume sozinho.",
    },
    {
      icon: "🌐",
      title: "Endereço fixo",
      description: "DNS dinâmico via DuckDNS. Seus amigos conectam sempre no mesmo endereço, não importa quem está hostando.",
    },
    {
      icon: "💰",
      title: "Custo: zero",
      description: "Roda no PC de quem está jogando. Sem mensalidade, sem servidor alugado.",
    },
    {
      icon: "🖥️",
      title: "Tudo visual",
      description: "Criar servidor, entrar na fila, gerenciar membros — tudo pela interface. Nada de terminal.",
    },
  ];

  return (
    <section id="features">
      <div className="container">
        <div className="features-header reveal">
          <h2 className="section-title">O que vem junto</h2>
          <p className="section-subtitle" style={{ margin: "0 auto" }}>
            O instalador já traz tudo que precisa pra funcionar.
          </p>
        </div>

        <div className="features-grid">
          {features.map((f, i) => (
            <div key={i} className={`feature-card reveal reveal-delay-${i + 1}`}>
              <span className="feature-icon">{f.icon}</span>
              <h3>{f.title}</h3>
              <p>{f.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ============================================
// DOWNLOAD
// ============================================
function Download() {
  return (
    <section className="download" id="download">
      <div className="container">
        <div className="download-wrapper">
          <div className="download-glow"></div>

          <div className="reveal">
            <h2 className="section-title">Download</h2>
            <p className="section-subtitle" style={{ margin: "0 auto" }}>
              Baixa, instala, e em poucos minutos já dá pra jogar.
            </p>
          </div>

          <div className="download-card reveal reveal-delay-2">
            <span className="download-version">● v1.0</span>
            <h3>Relay Installer</h3>
            <p className="download-desc">Windows • ~700 MB (inclui 3 motores de servidor)</p>

            <a
              href="https://github.com/Zeus-Alvs/Relay/releases/download/installer/Relay_Installer.exe"
              className="btn btn-download"
            >
              ⬇ Baixar para Windows
            </a>

            <div className="download-reqs">
              <span className="download-req">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 12l2 2 4-4" /><circle cx="12" cy="12" r="10" /></svg>
                Windows 10+
              </span>
              <span className="download-req">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 12l2 2 4-4" /><circle cx="12" cy="12" r="10" /></svg>
                4 GB RAM
              </span>
              <span className="download-req">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 12l2 2 4-4" /><circle cx="12" cy="12" r="10" /></svg>
                Internet
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}


// ============================================
// TUTORIAL
// ============================================
function Tutorial() {
  const [openIndex, setOpenIndex] = useState(null);

  const toggle = (index) => {
    setOpenIndex(openIndex === index ? null : index);
  };

  const sections = [
    {
      icon: "🚀",
      title: "Início Rápido",
      content: (
        <>
          <p>
            Depois de instalar, abre o Relay e cria tua conta. Daí você pode
            criar um servidor novo ou entrar num existente usando um código de
            6 dígitos que alguém te passe.
          </p>
          <p>
            Pra jogar, é só clicar em <strong>"Entrar no Relay"</strong> no
            dashboard do servidor. Se ninguém tiver jogando, você vira host
            na hora. Se alguém já estiver, você entra na fila e espera a vez.
          </p>
          <div className="placeholder-note">
            📝 Tutorial detalhado com capturas de tela será adicionado aqui.
          </div>
        </>
      ),
    },
    {
      icon: "🏗️",
      title: "Criando um Servidor",
      content: (
        <>
          <p>
            Criar um servidor precisa de algumas coisas extras. Parece chato,
            mas cada uma leva poucos minutos:
          </p>
          <p>
            <strong>1. Tailscale Auth Key</strong> — A VPN que conecta todo mundo.<br />
            <strong>2. DuckDNS</strong> — Pra ter um endereço fixo (opcional, mas recomendado).<br />
            <strong>3. Token do Google Drive</strong> — Pra salvar o mundo na nuvem.<br />
            <strong>4. Preparando o Servidor</strong> — O arquivo <code>server.jar</code> do seu modpack ou versão do Minecraft.
          </p>
          <div className="placeholder-note">
            📝 Passo-a-passo com links e screenshots será adicionado aqui.
            Vai cobrir como criar cada chave/token e preparar o server.jar.
          </div>
        </>
      ),
    },
    {
      icon: "🎯",
      title: "Entrando num Servidor",
      content: (
        <>
          <p>
            Alguém te mandou um código de 6 dígitos? Vai em{" "}
            <strong>"Entrar com Código"</strong> no hub, cola o código e confirma.
            O servidor aparece na tua lista na hora.
          </p>
          <p>
            Depois é só clicar no servidor e apertar{" "}
            <strong>"Entrar no Relay"</strong> pra jogar ou entrar na fila.
          </p>
          <div className="placeholder-note">
            📝 Guia visual com capturas de tela será adicionado aqui.
          </div>
        </>
      ),
    },
    {
      icon: "⚙️",
      title: "Configurações Avançadas",
      content: (
        <>
          <p>Se você for admin do servidor, tem umas opções extras:</p>
          <p>
            • <strong>Upload de Mods/Plugins</strong> — Manda mods pro servidor
              e todo mundo recebe automaticamente.<br />
            • <strong>server.properties</strong> — Edita as configs do servidor
              pela interface.<br />
            • <strong>Gestão de Membros</strong> — Promove admin, expulsa gente,
              etc.<br />
            • <strong>Forçar Destravamento</strong> — Se travou na nuvem, reseta
              o estado.
          </p>
          <div className="placeholder-note">
            📝 Documentação com exemplos será adicionada aqui.
          </div>
        </>
      ),
    },
  ];

  return (
    <section id="tutorial">
      <div className="container">
        <div className="tutorial-header reveal">
          <h2 className="section-title">Tutorial</h2>
          <p className="section-subtitle" style={{ margin: "0 auto" }}>
            Do download ao primeiro jogo — tudo que você precisa saber.
          </p>
        </div>

        <div className="accordion reveal">
          {sections.map((section, i) => (
            <div
              key={i}
              className={`accordion-item ${openIndex === i ? "open" : ""}`}
            >
              <button className="accordion-trigger" onClick={() => toggle(i)}>
                <span className="accordion-trigger-left">
                  <span className="accordion-trigger-icon">{section.icon}</span>
                  {section.title}
                </span>
                <ChevronDown className="accordion-chevron" />
              </button>
              <div className="accordion-content">
                <div className="accordion-body"><div className="accordion-body-inner">{section.content}</div></div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ============================================
// FOOTER
// ============================================
function Footer() {
  const year = new Date().getFullYear();

  return (
    <footer className="footer">
      <div className="container">
        <div className="footer-inner">
          <div className="footer-brand">
            <img src="/relay_ico.png" alt="" />
            Relay
          </div>

          <p className="footer-copy">© {year} Relay</p>

          <ul className="footer-links">
            <li><a href="#home">Home</a></li>
            <li><a href="#download">Download</a></li>
            <li><a href="#tutorial">Tutorial</a></li>
          </ul>
        </div>
      </div>
    </footer>
  );
}

// ============================================
// PAGE
// ============================================
export default function Home() {
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("visible");
          }
        });
      },
      { threshold: 0.1, rootMargin: "0px 0px -40px 0px" }
    );

    document.querySelectorAll(".reveal").forEach((el) => observer.observe(el));

    return () => observer.disconnect();
  }, []);

  return (
    <>
      <Navbar />
      <main>
        <Hero />
        <Steps />
        <Features />
        <Download />
        <Tutorial />
      </main>
      <Footer />
    </>
  );
}
