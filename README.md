# ThesisMate

Ein intelligentes System zur Unterstützung beim Schreiben wissenschaftlicher Arbeiten mit mehreren spezialisierten AI-Agents.

## 🚀 Quickstart

### Voraussetzungen

- Python 3.12
- `uv` package manager

### Installation

1. **Repository klonen:**
   ```bash
   git clone <repository-url>
   cd ThesisMate
   ```

2. **Virtual Environment erstellen und Dependencies installieren:**
   ```bash
   uv venv
   
   source .venv/bin/activate  # macOS/Linux
   .venv\Scripts\activate     # Windows
   
   uv pip install -e .
   ```

3. **Environment Variables einrichten:**
   ```bash
   cp .env.example .env
   ```
   
   Dann die `.env` Datei bearbeiten und OpenRouter API Key hinzufügen:
   ```
   OPENROUTER_API_KEY=your_api_key_here
   ```

### Anwendung starten

```bash
chainlit run src/ui/app.py
```

Dies öffnet die ThesisMate Benutzeroberfläche im Browser.

## 🏗️ Architektur

### AI-Agents

- **Topic Scout**: Hilft bei der Themenfindung und -bewertung
- **Research Agent**: Sucht und analysiert wissenschaftliche Paper
- **Structure Agent**: Erstellt Thesis-Gliederungen
- **Writing Agent**: Verfasst akademische Texte mit Zitationen
- **Reviewer Agent**: Überprüft und verbessert Texte

### Datenstruktur

```
data/
├── conversation.json          # Topic Scout Chat-Verlauf
└── thesis/
    ├── research/             # Research Agent Papers
    │   └── papers_*.json
    ├── outline/              # Structure Agent Gliederungen
    │   ├── *.json
    │   └── *.md
    ├── chapter/              # Writing Agent Kapitel
    │   └── 01_*/
    ├── config/               # Schreibstil & Einstellungen
    │   ├── writing_style.json
    │   └── guardrails.json
    ├── guardrails/           # Upload-Dateien & Richtlinien
    └── bib/                  # Bibliographie-Dateien
```

## 🔧 Entwicklung

### Branch-Struktur

- `main`: Stable Release
- `feature/*`: Neue Features
- `fix/*`: Bugfixes

### Wichtige Dateien

- `src/agents/`: AI-Agent Implementierungen
- `src/utils/storage.py`: Datei-Management
- `src/models/models.py`: Datenmodelle
- `src/ui/app.py`: Chainlit UI

## 📝 Verwendung

1. **Thema finden**: Topic Scout hilft bei der Themenfindung
2. **Research**: Research Agent sammelt relevante Paper
3. **Gliederung**: Structure Agent erstellt Thesis-Struktur
4. **Schreiben**: Writing Agent verfasst Kapitel mit Zitationen
5. **Review**: Reviewer Agent überprüft und verbessert

## 🛠️ Konfiguration

### Schreibstil anpassen

```bash
# Im Chat verwenden:
style set citation=APA
style set guide: Formal, präzise, wissenschaftlich
```

### Guardrails hochladen

Lade PDF/DOCX Dateien hoch, um Schreibrichtlinien zu definieren.

## 📚 Weitere Dokumentation

- `specs/`: Detaillierte Spezifikationen
- `cline-docs/`: Implementierungspläne
