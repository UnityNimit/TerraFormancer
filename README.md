# 🛠️ TerraFormancer

<p align="center">
  <img alt="Python Version" src="https://img.shields.io/badge/python-3.9+-blue.svg">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-green.svg">
  <img alt="PRs Welcome" src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg">
</p>

<p align="center">
  The revolutionary tool that transforms natural language into deployable AWS infrastructure.
</p>

---

TerraFormancer V2 is a complete re-architecture of the original concept, built as a modern client-server application. It leverages the power of Large Language Models to understand your requests and generates Terraform HCL code, architecture diagrams, and deployment plans in real-time through a sleek, intuitive web interface.

<br>

<p align="center">
  <!-- **IMPORTANT**: Replace this with the actual path to your GIF once created -->
  <img src="https://raw.githubusercontent.com/UnityNimit/TerraFormancer/main/demo.gif?raw=true" alt="TerraFormancer Demo GIF" width="80%">
</p>

## ✨ Key Features

- **AI-Powered Generation:** Describe your infrastructure in plain English (or use your voice!), and let the AI architect the solution.
- **Instant Visualization:** Automatically generates a cloud architecture diagram for any valid Terraform code, giving you immediate visual feedback.
- **Full Deployment Cycle:** Go from an idea to a live deployment. The app handles `plan` and `apply` commands through a safe, user-approved workflow.
- **Interactive Chat UI:** A beautiful, animated, Telegram-style interface makes interacting with the AI a seamless experience.
- **Voice Commands:** Speak your vision into existence with integrated browser-based voice recognition.
- **Robust Backend:** Built with FastAPI and LangGraph for a powerful, scalable, and stateful agentic workflow.

## 🚀 Built With

| Technology      | Role                       |
| --------------- | -------------------------- |
| **Backend**     |                            |
| Python          | Core Language              |
| FastAPI         | Web Server & API           |
| LangGraph       | AI Agent & State Machine   |
- **Google Generative AI** | LLM for Code Generation    |
- **Diagrams** | Architecture Visualization |
| **Frontend** | |
- **HTML5** | Structure |
- **Tailwind CSS** | Styling & UI |
- **Vanilla JavaScript** | Interactivity & API Calls |
| **Tooling** | |
- **Terraform** | Infrastructure as Code |
- **AWS** | Target Cloud Provider |

## 🏁 Getting Started

Follow these steps to get a local copy up and running.

### Prerequisites

- [Python 3.9+](https://www.python.org/downloads/)
- [Terraform CLI](https://learn.hashicorp.com/tutorials/terraform/install-cli) installed and configured in your system's PATH.
- [AWS CLI](https://aws.amazon.com/cli/) installed and configured with your credentials.

### Installation

**1. Clone the Repository**
```sh
git clone https://github.com/UnityNimit/TerraFormancer.git
cd TerraFormancer
```

**2. Set Up the Backend**

First, create a `requirements.txt` file inside the `/backend` directory to streamline package installation.

i. Create a new file named `requirements.txt` inside the `/backend` folder.

ii. Copy and paste the following lines into it:
```txt
# backend/requirements.txt

fastapi[all]
uvicorn[standard]
python-dotenv
langgraph
langchain-core
langchain-google-genai
google-generativeai
speechrecognition
diagrams
python-hcl2
```

iii. Now, run the setup commands from your terminal:
```sh
# Navigate to the backend directory
cd backend

# Create and activate a virtual environment
python -m venv venv

# On Windows:
.\venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install all required packages from your new file
pip install -r requirements.txt
```

**3. Configure Environment Variables**

i. In the `/backend` directory, create a file named `.env`.

ii. Add your secret keys to this file. **This file should not be committed to Git.**
```env
# backend/.env

GOOGLE_API_KEY="your_google_api_key_here"
AWS_ACCESS_KEY_ID="your_aws_access_key_id"
AWS_SECRET_ACCESS_KEY="your_aws_secret_access_key"
AWS_DEFAULT_REGION="us-east-1"
```

## 🖥️ Usage

You need to run two separate processes in two different terminals.

**1. Start the Backend Server**

- Open a terminal, navigate to the `/backend` directory, and make sure your virtual environment is activated.
```sh
# (venv) ...
python -m uvicorn app:app --reload --port 8000
```
The backend API is now running on `http://127.0.0.1:8000`.

**2. Launch the Frontend**

- Open the `/frontend` directory in your file explorer.
- **Double-click on `index.html`** to open it in your default web browser.
- That's it! The application is ready to use.

> **Pro Tip:** For a slightly better development experience, you can use a live server. If you use VS Code, the "Live Server" extension is an excellent choice.

## 📂 Project Structure

```
TerraFormancer/
├── backend/
│   ├── .env                # Your secret keys and configuration
│   ├── agent_logic.py      # Core LangGraph and tool logic
│   ├── app.py              # FastAPI server
│   ├── diagram_generator.py # Diagram creation script
│   └── requirements.txt    # Backend Python dependencies
│
└── frontend/
    └── index.html          # The all-in-one frontend file (HTML, CSS, JS)
```

## 🤝 Contributing

Contributions are what make the open-source community such an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**.

1.  Fork the Project
2.  Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3.  Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4.  Push to the Branch (`git push origin feature/AmazingFeature`)
5.  Open a Pull Request

---
```mermaid
---
config:
  layout: dagre
  theme: redux-dark
  look: classic
---
flowchart TD
 subgraph User_Environment["User's Environment"]
        User(["User"])
        Browser(["Web Browser"])
  end
 subgraph Application_Stack["Application Stack"]
        Frontend(["Frontend UI"])
        Backend(["Backend Server - FastAPI on localhost:8000"])
  end
 subgraph AI_Engine["Core AI Logic"]
        LangGraph(["LangGraph Engine"])
  end
 subgraph External_Services["External Tools & Services"]
        GenAI(["Google Generative AI API"])
        TerraformCLI(["Terraform CLI - Subprocess"])
        AWS(["AWS Cloud"])
  end
    User --> Browser
    Frontend -- HTTP API --> Backend
    Backend -- Orchestrates --> LangGraph
    LangGraph -- API Call --> GenAI
    Backend -- Subprocess Call --> TerraformCLI
    TerraformCLI -- Infra Provisioning --> AWS
    Browser --> Frontend
  ```