# Axiom AI (Tutor AI) 🚀

> **Note:** This project is currently **under active development**. Features and architecture are subject to change.

Axiom AI (also known as Tutor AI) is a multi-tenant, agentic SaaS platform designed specifically to revolutionize the **Sri Lankan private tuition / shadow education sector**. 

Currently, tutors manage thousands of students through chaotic WhatsApp and Telegram groups, requiring immense manual effort to answer repetitive questions, grade papers, and track monthly payments. Axiom AI replaces this manual bottleneck with an intelligent, multi-agent conversational AI that integrates seamlessly with the messaging apps students already use.

## 🌟 Vision
To provide a 24/7, personalized AI assistant for every student while completely automating the administrative, financial, and support burdens for educators and tuition agencies.

## ✨ Key Features & Workflows
Driven by a **LangGraph** orchestrator, the platform routes student intents to specialized AI agents:

- **Admissions Agent:** Automates student registration (capturing name, school, district) and handles PDPA consent via chat.
- **Resource Agent:** Connects to Google Drive to retrieve specific past papers, notes, or lecture links based on conversational queries.
- **Academic Assistant Agent (RAG):** Acts as a 24/7 study buddy, answering doubts step-by-step using the tutor’s specific teaching methodology and tone.
- **Finance & Ledger Agent:** Verifies payments by reading uploaded photos of bank transfer slips using OCR (Vision models), cross-checks amounts/dates, and issues digital receipts or dynamic QR code tickets.
- **Ticketing & Admin Routing:** Flags duplicated/fraudulent bank slips and intelligently routes angry or highly complex queries to a human "Escalation Inbox" in the CRM.

## 💻 Tech Stack
Our architecture is built for high concurrency, low latency (Meta's 3-second webhook rules), and robust agentic memory:

- **Ingestion & API:** FastAPI, Webhooks (Meta WhatsApp / Telegram), Redis Message Queue.
- **Orchestration:** LangGraph (Supervisor & multi-agent routing).
- **Memory & CRM:** Supabase (PostgreSQL) for long-term relational data, Qdrant / pgvector for semantic caching and RAG.
- **LLM Engine:** Google Gemini (optimized for multimodal/vision OCR) and OpenRouter (Claude/OpenAI).
- **Tooling Integrations:** Model Context Protocol (MCP) for secure isolation of Google Drive, Supabase, and Payment APIs.
- **Frontend / Staff Portal:** Next.js Admin CRM Dashboard.

---
*Built to empower Sri Lankan educators with the next generation of Agentic AI.*
