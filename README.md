# OneRise · Founder Matches

A founder matching platform that uses semantic embeddings to find compatible founders based on their needs and offerings.

## Features

- 🔍 **Semantic Search** - Find founders by name or industry
- 🎯 **Top-K Matching** - Discover the best matches based on needs/gives compatibility
- ✨ **AI Match Explanations** - Get OpenAI-powered explanations for why founders are good matches

## Setup

### Prerequisites

- Python 3.9+
- Node.js (optional, for alternative frontend serving)

### Backend Setup

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up OpenAI API Key** (required for AI explanations):
   
   Create a `.env` file in the `backend/` directory:
   ```bash
   cp .env.example .env  # or create manually
   ```
   
   Add your OpenAI API key:
   ```
   OPENAI_API_KEY=sk-your-api-key-here
   ```
   
   > 🔑 Get your API key from [platform.openai.com/api-keys](https://platform.openai.com/api-keys)

4. Start the backend server:
   ```bash
   uvicorn app:app --reload --port 8000
   ```

### Frontend Setup

1. From the project root, start a simple HTTP server:
   ```bash
   python3 -m http.server 5500
   ```

2. Open your browser to [http://127.0.0.1:5500](http://127.0.0.1:5500)

## Using AI Match Explanations

Once you have the OpenAI API key configured:

1. Select a founder from the list
2. Click **Find Matches** to get top matches
3. On each match card, click **✨ Explain Match** to get an AI-generated explanation of why the match is compatible

The AI analyzes the seeker's needs and the match's offerings to provide personalized insights about potential synergies.

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENAI_API_KEY` | Your OpenAI API key for generating match explanations | Yes (for AI features) |

## Deployment

For production deployment (e.g., Render):

1. Add `OPENAI_API_KEY` as an environment variable in your hosting dashboard
2. The app will automatically use the environment variable

## Project Structure

```
nycOneRise/
├── app.js              # Frontend JavaScript
├── index.html          # Frontend HTML
├── styles.css          # Frontend styles
├── backend/
│   ├── app.py          # FastAPI backend
│   ├── requirements.txt
│   ├── .env            # Environment variables (not committed)
│   └── artifacts/      # Embeddings and metadata
└── .gitignore
```

## API Endpoints

- `GET /api/health` - Health check
- `GET /api/founders` - List/search founders
- `GET /api/topk` - Get top-K matches for a founder
- `POST /api/explain` - Generate AI explanation for a match
