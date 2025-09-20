# Quickstart

This quickstart guide will walk you through the basic setup and usage of the ThesisMate system.

## Prerequisites

- Python 3.12
- `uv` package manager

## Installation

1.  Clone the repository:
    ```bash
    git clone <repository-url>
    cd ThesisMate
    ```

2.  Create a virtual environment and install dependencies:
    ```bash
    uv venv

    source .venv/bin/activate  # On macOS/Linux
    .venv\Scripts\activate     # On Windows

    uv pip install -e .
    ```

3.  Set up your environment variables by copying the `.env.example` file to `.env` and filling in the required values:
    ```bash
    cp .env.example .env
    ```
    
    Then edit the `.env` file and add your OpenRouter API key:
    ```
    OPENROUTER_API_KEY=your_api_key_here
    ```

## Running the Application

To start the Chainlit UI, run the following command:

```bash
chainlit run src/ui/app.py
```

This will open a new browser tab with the ThesisMate interface.
