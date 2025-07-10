# 🛠️ TerraFormancer

<p align="center">
  <img alt="Python Version" src="https://img.shields.io/badge/python-3.9+-blue.svg">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-green.svg">
  <img alt="PRs Welcome" src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg">
</p>

<h3 align="center">
  The revolutionary tool that transforms natural language into deployable AWS infrastructure.
</h3>

---

TerraFormancer is a complete re-architecture of the original concept, built as a modern client-server application. It leverages the power of Large Language Models to understand your requests and generates Terraform HCL code, architecture diagrams, and deployment plans in real-time through a sleek, intuitive web interface.

<br>

<p align="center">
  <a href="https://github.com/UnityNimit/TerraFormancer">
    <img src="https://raw.githubusercontent.com/UnityNimit/TerraFormancer/main/demo.gif?raw=true" alt="TerraFormancer Demo GIF" width="85%">
  </a>
</p>

## ✨ Core Features

- **🤖 AI-Powered Generation:** Describe your infrastructure in plain English (or use your voice!), and let the AI architect the solution.
- **🎨 Instant Visualization:** Automatically generates a cloud architecture diagram for any valid Terraform code, giving you immediate visual feedback.
- ** ciclo completo de implementación:** Go from an idea to a live deployment. The app handles `plan` and `apply` commands through a safe, user-approved workflow.
- **💬 Interactive Chat UI:** A beautiful, animated, Telegram-style interface makes interacting with the AI a seamless experience.
- **🎙️ Voice Commands:** Speak your vision into existence with integrated browser-based voice recognition.
- **⚙️ Robust Backend:** Built with FastAPI and LangGraph for a powerful, scalable, and stateful agentic workflow.

## 🛠️ The Tech Stack

| Category        | Technology             | Role                       |
| --------------- | ---------------------- | -------------------------- |
| **Backend**     | **Python**             | Core Language              |
|                 | FastAPI                | Web Server & API           |
|                 | LangGraph              | AI Agent & State Machine   |
|                 | Google Generative AI   | LLM for Code Generation    |
|                 | Diagrams               | Architecture Visualization |
| **Frontend**    | **HTML5**              | Structure                  |
|                 | Tailwind CSS           | Styling & UI               |
|                 | Vanilla JavaScript     | Interactivity & API Calls  |
| **Tooling**     | **Terraform**          | Infrastructure as Code     |
|                 | AWS                    | Target Cloud Provider      |

## 🚀 Getting Started

<details>
<summary><strong>▶ Click to expand the step-by-step setup guide</strong></summary>

### Prerequisites

Make sure you have the following tools installed and configured on your system:

-   [Python 3.9+](https://www.python.org/downloads/)
-   [Terraform CLI](https://learn.hashicorp.com/tutorials/terraform/install-cli) (in your system's PATH)
-   [AWS CLI](https://aws.amazon.com/cli/) (configured with your credentials)

### ⚙️ Installation & Configuration

**1. Clone the Repository**
```sh
git clone https://github.com/UnityNimit/TerraFormancer.git
cd TerraFormancer
```

**2. Set Up the Backend Environment**

This involves creating a `requirements.txt` file, setting up a virtual environment, and installing dependencies.

i. **Create `requirements.txt`:** Inside the `/backend` folder, create a new file named `requirements.txt` and add the following content:
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

ii. **Install Dependencies:** Now, run these commands from the root of the project:
```sh
# Navigate to the backend directory
cd backend

# Create and activate a virtual environment
python -m venv venv

# On Windows:
.\venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install all required packages
pip install -r requirements.txt
```

**3. Configure Environment Variables**

i. In the `/backend` directory, create a file named `.env`.

ii. Add your secret keys to this file. This file is ignored by Git and should never be made public.
```env
# backend/.env
GOOGLE_API_KEY="your_google_api_key_here"
AWS_ACCESS_KEY_ID="your_aws_access_key_id"
AWS_SECRET_ACCESS_KEY="your_aws_secret_access_key"
AWS_DEFAULT_REGION="us-east-1"
```
</details>

## 🖥️ Usage

You need to run the backend and frontend in two separate terminals.

| Backend Server (Terminal 1)                                                              | Frontend Application (Terminal 2)                                                                                             |
| ---------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| 1. Navigate to the `/backend` directory. <br> 2. Ensure your virtual environment is active. | 1. Navigate to the `/frontend` directory. <br> 2. Open `index.html` in your browser.                                          |
| ```sh # (venv) ... python -m uvicorn app:app --reload --port 8000 ```                     | That's it! Your browser will open the UI, which is now connected to the local backend server.                                 |
| The API is now running at `http://127.0.0.1:8000`.                                       | > **Pro Tip:** For a better dev experience, use a live server extension in your code editor (like "Live Server" for VS Code). |

## 📂 Project Structure

```
TerraFormancer/
├── backend/
│   ├── .env                # Secret keys and configuration (you create this)
│   ├── agent_logic.py      # Core LangGraph and tool logic
│   ├── app.py              # FastAPI server
│   ├── diagram_generator.py # Diagram creation script
│   └── requirements.txt    # Backend Python dependencies (you create this)
│
└── frontend/
    └── index.html          # The all-in-one frontend file (HTML, CSS, JS)
```

## 📈 System Architecture & Workflows

Here's a look at how the different parts of TerraFormancer interact.

<table>
  <tr>
    <td>
      <strong>High-Level System Architecture</strong>
      <br><br>
      <pre><code class="language-mermaid">
```mermaid
---
config:
  theme: redux-dark
  look: classic
---
flowchart TD
 subgraph User_Environment["User's Environment"]
    User(["👤 User"])
    Browser(["🌐 Web Browser"])
  end
 subgraph App_Stack["Application Stack"]
    Frontend(["🎨 Frontend UI"])
    Backend(["⚙️ Backend Server"])
  end
 subgraph AI_Engine["AI Engine"]
    LangGraph(["🧠 LangGraph"])
  end
 subgraph External["External Tools & Services"]
    GenAI(["Google AI API"])
    TerraformCLI(["Terraform CLI"])
    AWS(["AWS Cloud"])
  end
    User --> Browser
    Browser --> Frontend
    Frontend -- HTTP API --> Backend
    Backend -- Orchestrates --> LangGraph
    LangGraph -- API Call --> GenAI
    Backend -- Subprocess --> TerraformCLI
    TerraformCLI -- Provisions --> AWS
```

---
config:
  theme: dark
---
sequenceDiagram
    participant User
    participant Frontend
    participant Backend
    participant Agent (LangGraph)
    participant GoogleAI

    User->>Frontend: Types prompt & sends
    Frontend->>Backend: POST /api/chat
    Backend->>Agent: Invoke with prompt
    Agent->>GoogleAI: Generate HCL
    GoogleAI-->>Agent: Return HCL code
    Agent->>Backend: Run diagram script
    Backend-->>Agent: Return diagram path
    Agent-->>Backend: Final state (HCL, path)
    Backend-->>Frontend: 200 OK (JSON response)
    Frontend->>User: Update UI with code & diagram
      </code></pre>
    </td>
  </tr>
  <tr>
    <td>
      <strong>Two-Phase Deployment Workflow</strong>
      <br><br>
      <pre><code class="language-mermaid">
---
config:
  theme: dark
---
flowchart TD
    A[Code in UI] --> B{Click 'Prepare'}
    B --> C[POST /api/plan]
    C --> D[Backend runs `terraform plan`]
    D --> E[Plan output sent to UI]
    E --> F{Approve Plan?}
    F -- No --> G[Stop]
    F -- Yes --> H{Click 'Apply'}
    H --> I[POST /api/apply]
    I --> J[Backend runs `terraform apply`]
    J --> K[Infra provisioned on AWS]
    K --> L[Logs sent to UI]
    L --> M[Display success]
      </code></pre>
    </td>
    <td>
      <strong>Tutorial Modal User Flow</strong>
      <br><br>
      <pre><code class="language-mermaid">
---
config:
  theme: dark
---
graph TD
    A["User on main page"]
    A --> B["Clicks 'How to Use'"]
    B --> C["Tutorial Modal Appears"]
    subgraph "Modal Interaction"
      C --> D1["Clicks 'X' button"]
      C --> D2["Presses 'Escape' key"]
    end
    D1 --> E["Modal Hides"]
    D2 --> E
    E --> F["Returns to main page"]
      </code></pre>
    </td>
  </tr>
</table>

## 🤝 Contributing

Contributions are what make the open-source community such an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**.

1.  Fork the Project
2.  Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3.  Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4.  Push to the Branch (`git push origin feature/AmazingFeature`)
5.  Open a Pull Request