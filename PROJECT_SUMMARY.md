# Project Summary: Expense Tracker Agent

This document provides a concise overview of the Expense Tracker Agent project, its structure, and architecture.

## Directory Structure

```
.
├── expense_tracker_agent/
│   ├── agent.py
│   └── tools.py
├── expense_tracker_agent.egg-info/
│   ├── dependency_links.txt
│   ├── PKG-INFO
│   ├── requires.txt
│   ├── SOURCES.txt
│   └── top_level.txt
├── .env
├── .gitignore
├── llms-full.txt
├── pyproject.toml
├── README.md
├── requirements.txt
└── test_agent.py
```

## File Descriptions

-   **`expense_tracker_agent/agent.py`**: Defines the main agent using `google-adk`. It configures the agent with a name, model (`gemini-2.5-flash`), instructions, and the tools it can use.
-   **`expense_tracker_agent/tools.py`**: Implements the core functionalities (tools) for the agent. This includes adding expenses, calculating totals, and listing expenses. It uses a simple in-memory list as a database, meaning expense data is not persisted between runs.
-   **`test_agent.py`**: A script to test the agent's functionalities. It simulates a user conversation by sending messages to the agent and printing the responses. **Note:** It attempts to import and use a `graph` object from `agent.py`, which is not present in the current implementation, indicating a potential version mismatch or an incomplete feature.
-   **`pyproject.toml`**: Project configuration file for modern Python packaging. It defines the project name, version, and core dependencies for installation with `pip`.
-   **`requirements.txt`**: A list of Python dependencies. It contains more packages than `pyproject.toml`, suggesting it might be for a more extensive or specific environment.
-   **`README.md`**: The project's README file, providing information for users and developers.
-   **`.env`**: A placeholder file for environment variables. It is intended to hold secrets like the `GEMINI_API_KEY`.
-   **`llms-full.txt`**: A large text file. Its purpose is not directly related to the application code but might contain documentation, context, or data for the language models.
-   **`expense_tracker_agent.egg-info/`**: A directory containing metadata for the `expense_tracker_agent` package. It's automatically generated when the package is installed (e.g., via `pip install -e .`) and helps Python's packaging tools manage the installation.

## Key Dependencies

-   **`google-adk`**: The Google Agent Development Kit, which provides the core framework for building the agent.
-   **`pydantic`**: Used for data validation and modeling. The `Expense` data model in `tools.py` is defined using Pydantic.
-   **`google-generativeai`**: The client library to interact with Google's Gemini family of models.
-   **`uvicorn`**: A fast ASGI server, likely intended for serving the agent as a web service (though this is not fully implemented).
-   **`langchain`, `langchain-core`, `langchain-community`, `langgraph`**: These dependencies, found in `requirements.txt`, are part of the LangChain ecosystem for building LLM applications. The use of `graph.ainvoke` in `test_agent.py` specifically points to an intended use of `langgraph` to structure the agent's execution flow.

## Overall Architecture

The project follows a simple **Agent-Tool architecture**:

-   A central **Agent** is defined in `agent.py` using the `google-adk`.
-   The Agent is empowered with a set of **Tools** defined in `tools.py`, which it can call upon to fulfill user requests.
-   It uses a Large Language Model (`gemini-2.5-flash`) to understand user intent and decide which tool to execute.
-   Data persistence is currently handled by a simple **in-memory list** in `tools.py`. This is not a persistent database; all data is lost when the application stops.
-   The project is structured as an installable Python package, as indicated by `pyproject.toml` and the `.egg-info` directory.
-   The presence of LangChain/LangGraph dependencies and the code in `test_agent.py` suggest the intended architecture is to wrap the ADK agent in a `langgraph` graph, which allows for more complex, stateful, and observable execution flows. However, this is not fully wired up in the current state of `agent.py`.
