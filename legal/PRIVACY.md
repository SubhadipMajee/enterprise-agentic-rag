# Privacy policy

This assistant answers questions using documents your organization has indexed. Do not paste secrets, passwords, or personal data that is not required to ask your question.

## What is processed

- **Questions you type** are sent to the application API and used to retrieve relevant document chunks and generate an answer.
- **Retrieved document snippets** are sent to the language-model provider so an answer can be written.
- **Conversation memory** is stored against your signed-in user id so follow-up questions can use prior turns.

## Third-party processors

Depending on configuration, query text, retrieved snippets, and traces may be processed by:

- The LLM gateway and model hosts (for example Portkey and Groq)
- The embedding provider (for example Google Gemini)
- The vector database (Qdrant)
- Optional observability products (Pydantic Logfire, LangSmith)

Your operator should have a data processing agreement with each vendor you enable, and should disable tracing (`LANGSMITH_TRACING=false`, empty `LOGFIRE_TOKEN`) when user content must not leave your environment.

## Retention

Retention of chats, traces, and indexed documents is controlled by the operator (application database or Redis checkpointer, Qdrant collection, and vendor dashboards). Ask your administrator how long data is kept and how to request deletion.

## Contact

For access, deletion, or privacy questions, contact the team that deployed this assistant.
