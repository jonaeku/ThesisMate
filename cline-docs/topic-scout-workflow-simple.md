# Topic Scout Rückdelegation - Einfacher Workflow

**Datum**: 2025-09-23  
**Zweck**: Team-Präsentation - Wie Topic Scout mit Orchestrator zusammenarbeitet

## Grundprinzip

**Topic Scout arbeitet NICHT direkt mit User**
- Orchestrator nimmt User-Anfragen entgegen
- Topic Scout prüft: "Habe ich genug Informationen?"
- Wenn NEIN → Topic Scout sagt Orchestrator: "Frag den User nach X"
- Wenn JA → Topic Scout nutzt Research Agent und gibt Ergebnis zurück

## Konkretes Beispiel - Schritt für Schritt

### Schritt 1: User fragt nach Hilfe
```
User: "Hilf mir bei der Themenfindung"

Orchestrator → Topic Scout: "User will Themenhilfe"
Topic Scout prüft: Kenne ich das Studienfeld? NEIN
Topic Scout → Orchestrator: "Frag nach dem Studienbereich"
Orchestrator → User: "Was studierst du?"
```

### Schritt 2: User nennt Studienbereich
```
User: "Informatik"

Orchestrator → Topic Scout: "User studiert Informatik"
Topic Scout prüft: Kenne ich spezifische Interessen? NEIN
Topic Scout → Orchestrator: "Frag nach Interessen in Informatik"
Orchestrator → User: "Was interessiert dich in der Informatik?"
```

### Schritt 3: User nennt Interessen
```
User: "KI und Machine Learning"

Orchestrator → Topic Scout: "User interessiert sich für KI und ML"
Topic Scout prüft: Habe ich genug Info? JA!

Topic Scout arbeitet:
1. Generiert Topic-Ideen für "Informatik + KI + ML"
2. Nutzt Research Agent als Tool:
   - "Validiere Topic: Machine Learning für Medizin"
   - "Validiere Topic: KI-basierte Cybersecurity"
   - "Validiere Topic: NLP für Chatbots"
3. Research Agent prüft Papers und gibt Bewertungen zurück
4. Topic Scout filtert die besten Topics

Topic Scout → Orchestrator: "Hier sind 3 validierte Topics"
Orchestrator → User: Präsentiert die Topics schön formatiert
```

## Warum diese Architektur?

### Vorteile
- **Einfach**: Jeder Agent hat klare Aufgabe
- **Testbar**: Topic Scout kann isoliert getestet werden
- **Flexibel**: Orchestrator entscheidet, wie er fragt
- **Sauber**: Keine direkte User-Interaktion in Agents

### Topic Scout Verantwortlichkeiten
- ✅ Prüfen ob genug Informationen vorhanden
- ✅ Topics generieren wenn möglich
- ✅ Research Agent als Tool nutzen für Validierung
- ✅ Orchestrator sagen was fehlt

### Topic Scout macht NICHT
- ❌ Direkt mit User sprechen
- ❌ Fragen formulieren (das macht Orchestrator)
- ❌ Conversation State verwalten
- ❌ UI/UX Entscheidungen

## Rückgabe-Typen

**Wenn Informationen fehlen:**
```
{
  "success": false,
  "needs_info": "field",  // oder "interests", "background"
  "message": "Studienbereich fehlt"
}
```

**Wenn erfolgreich:**
```
{
  "success": true,
  "topics": [
    {"title": "ML für Medizin", "feasibility": 0.8, "papers": 45},
    {"title": "KI Cybersecurity", "feasibility": 0.7, "papers": 32}
  ]
}
```

## Erweiterbarkeit

**Andere Agents können dasselbe Pattern nutzen:**
- Writing Agent: "Frag nach dem Text-Draft"
- Structure Agent: "Frag nach dem gewählten Topic"
- Review Agent: "Frag nach dem zu reviewenden Dokument"

**Orchestrator wird zur zentralen Informations-Sammelstelle**

## Nächste Schritte

1. Models für Rückgabe-Typen definieren
2. Topic Scout mit Research Agent Tool implementieren
3. Orchestrator für Rückdelegation erweitern
4. Testen mit verschiedenen Szenarien

**Einfach, sauber, erweiterbar!**
