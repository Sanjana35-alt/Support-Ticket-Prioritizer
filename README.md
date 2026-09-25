# Support Ticket Prioritizer

AI-powered customer support ticket triage prototype designed for high-velocity SaaS support teams.

## Overview

This application helps support managers and agents quickly triage incoming support tickets by:
- Classifying incoming tickets into categories
- Assigning priority levels (`P1 - Critical`, `P2 - High`, `P3 - Normal`)
- Extracting core customer issues and detecting missing information
- Routing tickets to recommended teams
- Flagging potential duplicate tickets

## Tech Stack

- **Python** (Core backend & triage logic)
- **Streamlit** (Interactive dashboard interface)
- **Pandas** (Ticket data structuring and reporting)

## Getting Started

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the Streamlit Application
```bash
streamlit run app.py
```

## 📁 Project Structure

```
support-ticket-prioritizer/
│
├── app.py                  # Main Streamlit dashboard application
├── data/
│   └── sample_tickets.txt  # 10 realistic support tickets for testing
├── requirements.txt        # Minimal Python dependencies
└── README.md               # Project documentation
```
